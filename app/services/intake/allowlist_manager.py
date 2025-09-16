from __future__ import annotations
from typing import List, Dict, Any, Iterator
import yaml
import os


def load_allowlist(path: str = "config/allowlist.yaml") -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("creators", [])


def get_enabled_creators(path: str = "config/allowlist.yaml") -> List[Dict[str, Any]]:
    creators = load_allowlist(path)
    return [c for c in creators if c.get("enabled", True)]


def iter_enabled_creators(path: str = "config/allowlist.yaml") -> Iterator[Dict[str, Any]]:
    for c in get_enabled_creators(path):
        yield c
