# app/services/clipper/candidate_maker.py
from __future__ import annotations
import json
import math
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

try:
    from pydub import AudioSegment
    HAVE_PYDUB = True
except Exception:
    HAVE_PYDUB = False


@dataclass
class CandidateConfig:
    # desired clip length window (you can override per creator)
    min_len_s: int = 18
    max_len_s: int = 60
    # transcript hotspot detection
    hotspot_keywords: Tuple[str, ...] = (
        r"\b(wtf|no way|omg|bro|dude|holy|let'?s go+|insane|crazy|what|yo+)\b",
    )
    hotspot_min_gap_s: int = 20  # don’t create hotspots too close to each other
    # sliding-window around hotspots (fallback if scene cuts are coarse)
    hotspot_window_pad_s: int = 8
    # audio peak detection (optional)
    audio_win_ms: int = 500
    audio_topk: int = 12  # how many loudest seconds to seed
    audio_pad_s: int = 10
    # final dedupe & limits
    iou_dedupe_threshold: float = 0.5
    max_candidates: int = 60


def _load_transcript_segments(transcript_json_path: str) -> List[Dict]:
    with open(transcript_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("segments", [])


def _slice_text(segments: List[Dict], start_s: int, end_s: int) -> str:
    out = []
    for seg in segments:
        st = float(seg.get("start", 0))
        en = float(seg.get("end", st))
        if en < start_s:
            continue
        if st > end_s:
            break
        out.append(seg.get("text", "").strip())
    text = " ".join(out).strip()
    return (text[:180] + "…") if len(text) > 180 else text


def _clamp_window(start_s: int, end_s: int, cfg: CandidateConfig) -> Tuple[int, int]:
    dur = end_s - start_s
    if dur < cfg.min_len_s:
        end_s = start_s + cfg.min_len_s
    elif dur > cfg.max_len_s:
        end_s = start_s + cfg.max_len_s
    return max(0, int(start_s)), max(0, int(end_s))


def _from_scene_cuts(scene_segments: List[Dict], cfg: CandidateConfig) -> List[Dict]:
    out = []
    for seg in scene_segments:
        s, e = int(seg["start"]), int(seg["end"])
        s, e = _clamp_window(s, e, cfg)
        if e > s:
            out.append({"start": s, "end": e, "source": "scene"})
    return out


def _from_transcript_hotspots(segments: List[Dict], cfg: CandidateConfig) -> List[Dict]:
    """Find moments with exclamations or keywords; create a padded window."""
    text_events: List[int] = []
    for seg in segments:
        t = (seg.get("text") or "").lower()
        st = int(seg.get("start", 0))
        has_mark = t.count("!") >= 1
        has_kw = any(re.search(p, t) for p in cfg.hotspot_keywords)
        if has_mark or has_kw:
            # Avoid events too close to each other
            if not text_events or (st - text_events[-1] >= cfg.hotspot_min_gap_s):
                text_events.append(st)

    out = []
    for ts in text_events:
        s = max(0, ts - cfg.hotspot_window_pad_s)
        e = ts + cfg.hotspot_window_pad_s + cfg.min_len_s // 2
        s, e = _clamp_window(s, e, cfg)
        out.append({"start": s, "end": e, "source": "transcript"})
    return out


def _audio_energy_series(media_path: str, win_ms: int) -> List[Tuple[int, float]]:
    audio = AudioSegment.from_file(media_path).set_channels(1)
    out: List[Tuple[int, float]] = []
    for i in range(0, len(audio), win_ms):
        frame = audio[i:i + win_ms]
        sec = i // 1000
        out.append((int(sec), frame.rms if frame.rms > 0 else 1))
    # convert to pseudo-dB for stability
    return [(t, 20 * math.log10(v)) for (t, v) in out]


def _from_audio_peaks(media_path: str, cfg: CandidateConfig) -> List[Dict]:
    if not HAVE_PYDUB or not os.path.exists(media_path):
        return []
    series = _audio_energy_series(media_path, cfg.audio_win_ms)
    if not series:
        return []
    # pick top-K loud seconds
    top = sorted(series, key=lambda x: x[1], reverse=True)[: cfg.audio_topk]
    out = []
    for sec, _db in top:
        s = max(0, sec - cfg.audio_pad_s)
        e = sec + cfg.audio_pad_s
        s, e = _clamp_window(s, e, cfg)
        out.append({"start": s, "end": e, "source": "audio"})
    return out


def _iou(a: Dict, b: Dict) -> float:
    inter = max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))
    union = (a["end"] - a["start"]) + (b["end"] - b["start"]) - inter
    return 0.0 if union <= 0 else inter / union


def _dedupe_merge(cands: List[Dict], cfg: CandidateConfig) -> List[Dict]:
    cands = sorted(cands, key=lambda x: (x["start"], x["end"]))
    out: List[Dict] = []
    for c in cands:
        if not out:
            out.append(c)
            continue
        last = out[-1]
        if _iou(last, c) >= cfg.iou_dedupe_threshold:
            # merge by expanding to cover both (keep earlier start & later end)
            merged = {"start": min(last["start"], c["start"]),
                      "end": max(last["end"], c["end"]),
                      "source": f"{last['source']}+{c['source']}"}
            out[-1] = merged
        else:
            out.append(c)
    return out


def make_candidates(
    media_path: str,
    transcript_json_path: str,
    scene_segments: List[Dict],
    *,
    cfg: Optional[CandidateConfig] = None,
) -> List[Dict]:
    """
    Combine scene cuts + transcript hotspots + (optional) audio peaks
    into a single deduped list of candidate windows with text previews.
    """
    cfg = cfg or CandidateConfig()
    segs = _load_transcript_segments(transcript_json_path)

    scene_cands = _from_scene_cuts(scene_segments, cfg)
    text_cands = _from_transcript_hotspots(segs, cfg)
    audio_cands = _from_audio_peaks(media_path, cfg)

    fused = scene_cands + text_cands + audio_cands
    fused = _dedupe_merge(fused, cfg)

    # add text previews
    for c in fused:
        c["text_preview"] = _slice_text(segs, c["start"], c["end"])

    # cap total to keep scoring/LLM prompt small
    return fused[: cfg.max_candidates]
