# app/services/intake/campaign_watcher.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import hashlib
import json
import os

import yaml
import httpx

SEEN_PATH = Path("tmp/state/campaign_seen.txt")
INBOX_PATH = Path("tmp/state/campaign_inbox.json")
ALLOWLIST_PATH = Path(os.getenv("ALLOWLIST_PATH", "config/allowlist.yaml"))
SOURCES_PATH = Path("config/campaign_sources.yaml")

# ---------- Models ----------

@dataclass
class Campaign:
    creator_handle: str
    platform: str            # youtube | twitch | kick
    source_url: str
    terms: Dict[str, Any]    # license_type, payout_model, etc.
    posting: Dict[str, Any]  # post_channel_id, max_daily, shorts_only
    raw: Dict[str, Any]      # original for traceability

    def key(self) -> str:
        base = f"{self.platform}|{self.creator_handle}|{self.source_url}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()


# ---------- Providers ----------

def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def _append_seen(key: str) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SEEN_PATH.open("a", encoding="utf-8") as f:
        f.write(key + "\n")

def _already_seen(key: str) -> bool:
    if not SEEN_PATH.exists():
        return False
    return key in SEEN_PATH.read_text(encoding="utf-8").splitlines()

def _validate_campaign(d: Dict[str, Any]) -> Optional[str]:
    required = ["creator_handle", "platform", "source_url"]
    for r in required:
        if r not in d or not d[r]:
            return f"missing required field: {r}"
    return None

def _norm_campaign(d: Dict[str, Any]) -> Campaign:
    terms = d.get("terms", {})
    posting = d.get("posting", {})
    return Campaign(
        creator_handle=d["creator_handle"],
        platform=d["platform"],
        source_url=d["source_url"],
        terms=terms,
        posting=posting,
        raw=d,
    )

def from_static_yaml(path: Path) -> List[Campaign]:
    data = _load_yaml(path)
    out: List[Campaign] = []
    for c in data.get("campaigns", []):
        err = _validate_campaign(c)
        if err: 
            print(f"[campaign_watcher] skip invalid static campaign: {err}")
            continue
        out.append(_norm_campaign(c))
    return out

def from_json_feed(url: str, timeout: float = 15.0) -> List[Campaign]:
    out: List[Campaign] = []
    try:
        r = httpx.get(url, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[campaign_watcher] json_feed error for {url}: {e}")
        return out
    items = data.get("campaigns", data)  # accept either {campaigns:[...]} or [...]
    if not isinstance(items, list):
        return out
    for c in items:
        err = _validate_campaign(c)
        if err:
            print(f"[campaign_watcher] skip invalid feed campaign: {err}")
            continue
        out.append(_norm_campaign(c))
    return out

# (Optional) minimal RSS handler — many feeds aren’t structured; skip by default.
# You can add feedparser later if needed.


# ---------- Aggregation & Inbox ----------

def discover_campaigns(sources_path: Path = SOURCES_PATH) -> List[Campaign]:
    """Read providers from config/campaign_sources.yaml and aggregate campaigns."""
    cfg = _load_yaml(sources_path)
    providers = cfg.get("providers", [])
    found: List[Campaign] = []

    for p in providers:
        ptype = p.get("type")
        if ptype == "static":
            path = Path(p.get("path", "config/campaigns_static.yaml"))
            found += from_static_yaml(path)
        elif ptype == "json_feed":
            url = p.get("url")
            if url:
                found += from_json_feed(url)
        else:
            print(f"[campaign_watcher] unknown provider type: {ptype}")

    # Deduplicate by key
    unique: Dict[str, Campaign] = {}
    for c in found:
        unique[c.key()] = c
    return list(unique.values())

def _load_allowlist(path: Path = ALLOWLIST_PATH) -> Dict[str, Any]:
    return _load_yaml(path)

def _save_allowlist(obj: Dict[str, Any], path: Path = ALLOWLIST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")

def _save_inbox(proposals: List[Dict[str, Any]]) -> None:
    INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INBOX_PATH.write_text(json.dumps(proposals, indent=2), encoding="utf-8")

def propose_allowlist_updates(auto_merge: bool = False) -> Dict[str, Any]:
    """
    - Finds new campaigns from configured providers.
    - Skips ones we've seen before (SEEN file).
    - Produces allowlist entries (not enabled by default).
    - Writes proposals to tmp/state/campaign_inbox.json for human review.
    - If auto_merge=True, append into config/allowlist.yaml (still disabled).
    """
    campaigns = discover_campaigns()
    proposals: List[Dict[str, Any]] = []

    for c in campaigns:
        key = c.key()
        if _already_seen(key):
            continue

        # Build a proposed allowlist entry (disabled by default)
        entry = {
            "handle": c.creator_handle,
            "platform": c.platform,
            "source_url": c.source_url,
            "license_type": c.terms.get("license_type", "campaign"),
            "post_channel_id": c.posting.get("post_channel_id", ""),
            "brand_preset": c.terms.get("brand_preset", "default"),
            "max_daily": c.posting.get("max_daily", 4),
            "shorts_only": c.posting.get("shorts_only", True),
            "enabled": False,  # require manual flip to True
            "_discovered_via": c.raw,  # keep raw for context/audit
        }
        proposals.append(entry)
        _append_seen(key)

    # Save proposals for review
    _save_inbox(proposals)

    merged = False
    if auto_merge and proposals:
        allow = _load_allowlist()
        allow.setdefault("creators", [])
        allow["creators"].extend(proposals)
        _save_allowlist(allow)
        merged = True

    return {
        "discovered": len(campaigns),
        "proposed": len(proposals),
        "auto_merged": merged,
        "inbox_path": str(INBOX_PATH),
        "allowlist_path": str(ALLOWLIST_PATH),
    }
