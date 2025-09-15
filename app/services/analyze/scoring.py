# app/services/analyze/scoring.py
from __future__ import annotations
import json
import math
import os
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

try:
    # Optional: better audio energy. If missing, we degrade gracefully.
    from pydub import AudioSegment
    HAVE_PYDUB = True
except Exception:
    HAVE_PYDUB = False


# ------------ Public API ------------

@dataclass
class ScoreConfig:
    # target clip duration for Shorts; tweak per creator via preset
    min_len_s: int = 18
    max_len_s: int = 60
    # audio energy window for RMS
    energy_win_ms: int = 500
    # keyword weights
    w_exclaim: float = 0.6
    w_question: float = 0.3
    w_keywords: float = 1.2
    w_laughter: float = 1.0
    w_sentiment: float = 0.8
    w_energy: float = 1.0
    w_pace: float = 0.4
    w_cohesion: float = 0.6
    w_len_fit: float = 0.7
    # penalties
    penalty_overlap: float = 0.5
    penalty_nsfw: float = 2.5
    penalty_banword: float = 2.0

    # lexicons (can be overridden per creator via your presets)
    excite_keywords: Tuple[str, ...] = (
        r"\b(wtf|no way|omg|bro|dude|holy|let'?s go+|insane|crazy|what\b|yo+)\b",
    )
    laughter_tokens: Tuple[str, ...] = (r"\b(lmao|lmfao|lol+|hahaha+|haha|rofl)\b",)
    positive_words: Tuple[str, ...] = (
        r"\b(awesome|amazing|win|victory|clutch|perfect)\b",
    )
    negative_words: Tuple[str, ...] = (
        r"\b(fail|lost|lose|trash|rage|mad|angry)\b",
    )
    # ban lists / NSFW-ish – keep generic; you can extend in brand presets
    ban_words: Tuple[str, ...] = (
        r"\b(kys|suicide)\b",
    )
    nsfw_words: Tuple[str, ...] = (
        r"\b(nsfw|porn)\b",
    )


@dataclass
class Segment:
    start: float
    end: float
    text: str


def score_candidates(
    media_path: str,
    transcript_json_path: str,
    candidates: List[Dict[str, int]],
    *,
    cfg: Optional[ScoreConfig] = None,
) -> List[Dict]:
    """
    Given a media file, transcript json, and candidate [start,end] windows,
    return a list of dicts with component scores, flags, and a final score.

    Output shape per candidate:
    {
      "start": int, "end": int, "dur": float,
      "scores": { "energy": ..., "keywords": ..., "sentiment": ..., "pace": ..., "cohesion": ..., "len_fit": ... },
      "flags": { "nsfw": bool, "banword": bool },
      "total": float
    }
    """
    cfg = cfg or ScoreConfig()

    segments = _load_transcript_segments(transcript_json_path)
    # Precompute simple per-second text features
    per_s_text = _index_text_features(segments)

    # Optional audio energy (RMS)
    energy = None
    if HAVE_PYDUB and os.path.exists(media_path):
        try:
            energy = _audio_energy_series(media_path, cfg.energy_win_ms)
        except Exception:
            energy = None

    results = []
    for c in candidates:
        s = int(max(0, c["start"]))
        e = int(c["end"])
        dur = max(0.0, e - s)
        window_text = _slice_text(segments, s, e)

        # Component scores
        k_keywords, has_laugh = _keyword_score(window_text, cfg)
        k_marks = _punctuation_score(window_text)
        k_sent = _sentiment_score(window_text, cfg)
        k_pace = _pace_score(window_text, dur)
        k_cohesion = _cohesion_score(window_text)
        k_energy = _energy_score(energy, s, e) if energy is not None else 0.0
        k_lenfit = _length_fit_score(dur, cfg)

        # Safety flags
        has_ban = _contains_any(window_text, cfg.ban_words)
        has_nsfw = _contains_any(window_text, cfg.nsfw_words)

        # Weighted sum
        composite = (
            cfg.w_keywords * k_keywords
            + cfg.w_laughter * (1.0 if has_laugh else 0.0)
            + cfg.w_exclaim * k_marks["exclaim"]
            + cfg.w_question * k_marks["question"]
            + cfg.w_sentiment * k_sent
            + cfg.w_pace * k_pace
            + cfg.w_cohesion * k_cohesion
            + cfg.w_energy * k_energy
            + cfg.w_len_fit * k_lenfit
        )

        # Penalties
        if has_ban:
            composite -= cfg.penalty_banword
        if has_nsfw:
            composite -= cfg.penalty_nsfw

        results.append({
            "start": s,
            "end": e,
            "dur": dur,
            "text_preview": (window_text[:180] + "…") if len(window_text) > 180 else window_text,
            "scores": {
                "keywords": round(k_keywords, 3),
                "laughter": 1.0 if has_laugh else 0.0,
                "exclaim": round(k_marks["exclaim"], 3),
                "question": round(k_marks["question"], 3),
                "sentiment": round(k_sent, 3),
                "pace": round(k_pace, 3),
                "cohesion": round(k_cohesion, 3),
                "energy": round(k_energy, 3),
                "len_fit": round(k_lenfit, 3),
            },
            "flags": {"banword": has_ban, "nsfw": has_nsfw},
            "total": round(composite, 3),
        })

    # Sort high → low
    results.sort(key=lambda x: x["total"], reverse=True)
    return results


# ------------ Internals ------------

def _load_transcript_segments(path: str) -> List[Segment]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    segs = []
    # Support Whisper/WhisperX JSON structure
    for s in data.get("segments", []):
        start = float(s.get("start", 0.0))
        end = float(s.get("end", start))
        text = s.get("text", "")
        segs.append(Segment(start, end, text))
    return segs


def _index_text_features(segments: List[Segment]) -> Dict[int, Dict]:
    """
    Rough per-second features (currently unused by default scoring, but useful
    if you later want heatmaps). Returns dict: sec -> {"chars": int, "exclaim": int, ...}
    """
    idx: Dict[int, Dict[str, int]] = {}
    for seg in segments:
        s = int(math.floor(seg.start))
        e = int(math.ceil(seg.end))
        for t in range(s, e + 1):
            if t not in idx:
                idx[t] = {"chars": 0, "exclaim": 0, "question": 0}
            idx[t]["chars"] += len(seg.text)
            idx[t]["exclaim"] += seg.text.count("!")
            idx[t]["question"] += seg.text.count("?")
    return idx


def _slice_text(segments: List[Segment], start_s: int, end_s: int) -> str:
    buf = []
    for seg in segments:
        if seg.end < start_s: 
            continue
        if seg.start > end_s:
            break
        buf.append(seg.text.strip())
    return " ".join(buf)


def _keyword_score(text: str, cfg: ScoreConfig) -> Tuple[float, bool]:
    """
    Score presence of excitement keywords and laughter tokens.
    Returns (score, has_laughter).
    """
    t = text.lower()
    score = 0.0
    for pat in cfg.excite_keywords:
        score += 1.0 if re.search(pat, t) else 0.0
    has_laugh = any(re.search(p, t) for p in cfg.laughter_tokens)
    # small bonus for laughter
    if has_laugh:
        score += 0.5
    return score, has_laugh


def _punctuation_score(text: str) -> Dict[str, float]:
    # Proxy for hype/hook; normalize by length a bit
    n = max(len(text), 1)
    ex = text.count("!") / n * 100.0
    qn = text.count("?") / n * 100.0
    # clamp
    return {"exclaim": min(ex, 1.5), "question": min(qn, 1.0)}


def _sentiment_score(text: str, cfg: ScoreConfig) -> float:
    """
    Very lightweight lexicon polarity. Positive OR negative emotion
    can both be "clippable". We score absolute polarity.
    """
    t = text.lower()
    pos = sum(1 for p in cfg.positive_words if re.search(p, t))
    neg = sum(1 for p in cfg.negative_words if re.search(p, t))
    return min(abs(pos - neg) + (pos + neg) * 0.3, 3.0)


def _pace_score(text: str, dur_s: float) -> float:
    # words per second — prefer active moments (but not too fast)
    words = max(1, len(text.split()))
    if dur_s <= 0.0:
        return 0.0
    wps = words / dur_s
    # ideal band: ~2–4 wps; Gaussian-ish
    mu, sigma = 3.0, 1.0
    return math.exp(-((wps - mu) ** 2) / (2 * sigma ** 2))


def _cohesion_score(text: str) -> float:
    # Self-contained moment heuristic: short sentences with at least one cue
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    if not sentences:
        return 0.0
    avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
    has_setup = any(re.search(r"\b(when|then|after|because|so|and then)\b", s.lower()) for s in sentences)
    base = 1.0 if (6 <= avg_len <= 22) else 0.5
    if has_setup:
        base += 0.3
    return min(base, 1.5)


def _length_fit_score(dur_s: float, cfg: ScoreConfig) -> float:
    # bonus if inside the sweet spot; soft penalty otherwise
    if cfg.min_len_s <= dur_s <= cfg.max_len_s:
        return 1.0
    # linear falloff
    center = (cfg.min_len_s + cfg.max_len_s) / 2
    span = (cfg.max_len_s - cfg.min_len_s) / 2
    if span <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(dur_s - center) / (span * 2))


def _contains_any(text: str, patterns: Tuple[str, ...]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


def _audio_energy_series(media_path: str, win_ms: int) -> List[Tuple[int, float]]:
    """
    Return list of (second, rms_dbfs) pairs sampled over the media.
    """
    audio = AudioSegment.from_file(media_path)  # ffmpeg-backed; auto-detects
    # Downmix to mono for stability
    audio = audio.set_channels(1)
    step = win_ms
    out: List[Tuple[int, float]] = []
    for i in range(0, len(audio), step):
        frame = audio[i:i + step]
        sec = i // 1000
        out.append((int(sec), frame.rms if frame.rms > 0 else 1))
    # convert to dBFS-like scale
    out_db = [(t, 20.0 * math.log10(v)) for (t, v) in out]
    return out_db


def _energy_score(series: List[Tuple[int, float]], start_s: int, end_s: int) -> float:
    if not series:
        return 0.0
    window = [v for (t, v) in series if start_s <= t <= end_s]
    if not window:
        return 0.0
    avg = sum(window) / len(window)
    # Normalize by a robust baseline (10th percentile over series)
    vals = [v for _, v in series]
    vals_sorted = sorted(vals)
    baseline = vals_sorted[max(0, int(0.1 * len(vals_sorted)) - 1)]
    return max(0.0, (avg - baseline) / 10.0)  # roughly 0..~2
