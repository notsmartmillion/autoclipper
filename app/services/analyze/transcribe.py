from pathlib import Path
import json

def transcribe_or_load(media_path: str, video_id: str, model_size: str = "medium"):
    out = Path("tmp/transcripts"); out.mkdir(parents=True, exist_ok=True)
    out_json = out / f"{video_id}.json"
    if out_json.exists():
        data = json.loads(out_json.read_text())
        return str(out_json), data.get("text", "")

    # Lazy import + robust fallback
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        segments, info = model.transcribe(media_path, vad_filter=True)
        segs, texts = [], []
        for s in segments:
            segs.append({"id": getattr(s, "id", None), "start": s.start, "end": s.end, "text": s.text.strip()})
            texts.append(s.text.strip())
        data = {"language": getattr(info, "language", None), "text": " ".join(texts), "segments": segs}
    except Exception as e:
        # Fallback to CPU whisper (PyTorch) so pipeline still works
        print(f"[transcribe] faster-whisper failed ({e}); falling back to CPU whisper.")
        import whisper  # openai/whisper
        model = whisper.load_model("medium")  # CPU
        res = model.transcribe(media_path)
        segs = [{"id": i, "start": s["start"], "end": s["end"], "text": s["text"].strip()} for i, s in enumerate(res.get("segments", []))]
        data = {"language": res.get("language"), "text": res.get("text", ""), "segments": segs}

    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return str(out_json), data["text"]
