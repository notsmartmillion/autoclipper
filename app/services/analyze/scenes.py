from scenedetect import VideoManager, SceneManager
from scenedetect.detectors import ContentDetector

def find_candidate_segments(media_path, transcript_text):
    # scenes + amplitude peaks → short windows (20–60s)
    vm = VideoManager([media_path])
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=27.0))
    vm.start(); sm.detect_scenes(frame_source=vm)
    scenes = sm.get_scene_list()
    # convert to candidate windows (start, end) and attach transcript slices
    candidates = []
    for s, e in scenes:
        dur = (e.get_seconds() - s.get_seconds())
        if 12 <= dur <= 80:
            candidates.append({"start": int(s.get_seconds()), "end": int(e.get_seconds())})
    return candidates[:30]  # cap
