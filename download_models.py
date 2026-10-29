"""Download official MediaPipe task assets. No network requests during judging."""
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent / "models"
MODELS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
}


def main():
    ROOT.mkdir(exist_ok=True)
    for name, url in MODELS.items():
        target = ROOT / name
        if target.exists() and target.stat().st_size > 1_000_000:
            print(f"Đã có: {name}")
            continue
        temporary = target.with_suffix(".part")
        print(f"Đang tải: {name}", flush=True)
        try:
            with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            if temporary.stat().st_size < 1_000_000:
                raise RuntimeError("Model tải về không đầy đủ.")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Sẵn sàng: {target}")


if __name__ == "__main__":
    main()
