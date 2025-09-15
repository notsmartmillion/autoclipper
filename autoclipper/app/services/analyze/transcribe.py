import subprocess, json, os
def transcribe_or_load(media_path:str, video_id:int):
    # Whisper (CPU ok for small; GPU recommended)
    out_json = media_path.replace(".mp4",".json")
    if not os.path.exists(out_json):
        subprocess.check_call(["whisperx", media_path, "--model", "large-v3", "--output_format","json"])
    with open(out_json) as f:
        data = json.load(f)
    text = " ".join([seg["text"] for seg in data["segments"]])
    return out_json, text
