# app/services/clipper/ranker_llm.py
import json
from typing import List, Dict, Any
from openai import OpenAI

client = OpenAI()


def pick_top_segments(
    transcript_text: str,
    scored_candidates: List[Dict[str, Any]],
    top_n: int = 5,
    model: str = "gpt-4o-mini",
) -> List[Dict[str, Any]]:
    """
    Use an LLM to rank already-scored candidate segments.

    Each candidate has:
      - start, end, dur
      - scores{}: energy, sentiment, exclaim, etc.
      - text_preview
      - total (numeric composite)

    Returns a list of chosen segments with title/desc fields added.
    """

    # Prepare context for the LLM
    # Keep only a subset of fields so prompt is not too huge
    simplified = []
    for c in scored_candidates:
        simplified.append({
            "start": c["start"],
            "end": c["end"],
            "dur": c["dur"],
            "text_preview": c["text_preview"],
            "scores": c["scores"],
            "total": c["total"],
        })

    system_prompt = (
        "You are an editor for viral short-form videos. "
        "You are given candidate segments from a long video, with transcript previews and numeric highlight scores "
        "(energy, exclamation, sentiment, pace, etc). "
        "Your job is to select the best segments that are most likely to go viral as Shorts. "
        "Prefer segments that:\n"
        "- Have strong hooks in the first 3 seconds\n"
        "- Are self-contained with a clear setup + payoff\n"
        "- Show strong emotion (funny, hype, fail, surprise)\n"
        "- Fit the target length (20–60s)\n"
        "Return your answer as JSON list, with each element containing: "
        '{"start":..., "end":..., "reason": "...", "title": "..."}'
    )

    user_prompt = (
        f"Here are the candidates (JSON):\n\n{json.dumps(simplified, indent=2)}\n\n"
        f"TRANSCRIPT (excerpted for context):\n{transcript_text[:3000]}\n\n"
        f"Now choose the top {top_n} segments and generate catchy but honest titles."
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    content = resp.choices[0].message.content.strip()

    try:
        data = json.loads(content)
    except Exception:
        # fallback if model output is not JSON
        data = []

    # Ensure structure
    results: List[Dict[str, Any]] = []
    for d in data:
        results.append({
            "start": d.get("start"),
            "end": d.get("end"),
            "title": d.get("title", "Untitled Clip"),
            "reason": d.get("reason", ""),
        })

    return results
