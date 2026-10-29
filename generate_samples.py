"""Create deterministic geometric demo videos. These are not real matches."""
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent / "samples"


def generate(output=ROOT):
    output = Path(output)
    output.mkdir(exist_ok=True, parents=True)
    width, height, fps = 640, 480, 30
    for game in ("football", "basketball", "tic_tac_toe"):
        path = output / f"{game}_demo.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError("Không mở được bộ ghi MP4.")
        try:
            for index in range(180):
                frame = np.full((height, width, 3), (45, 60, 40), np.uint8)
                t = index / fps
                if game == "football":
                    cv2.line(frame, (499, 120), (499, 360), (200, 220, 200), 3)
                    phase = t % 3
                    if phase < 2:
                        cv2.circle(frame, (int((0.20 + phase * 0.36) * width), 240), 13, (0, 140, 255), -1)
                elif game == "basketball":
                    cv2.line(frame, (224, 216), (416, 216), (200, 220, 200), 3)
                    phase = t % 3
                    if phase < 2:
                        cv2.circle(frame, (320, int((0.12 + phase * 0.32) * height)), 13, (0, 140, 255), -1)
                else:
                    x, y, w, h = 64, 48, 512, 384
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 255, 255), -1)
                    for part in (1, 2):
                        cv2.line(frame, (x + part * w // 3, y), (x + part * w // 3, y + h), (0, 0, 0), 3)
                        cv2.line(frame, (x, y + part * h // 3), (x + w, y + part * h // 3), (0, 0, 0), 3)
                    board = ["X", "X", "X", "O", "O", "", "", "", ""]
                    for cell, symbol in enumerate(board):
                        cx, cy = x + (cell % 3 + 0.5) * w / 3, y + (cell // 3 + 0.5) * h / 3
                        if symbol == "X":
                            cv2.line(frame, (int(cx - 30), int(cy - 30)), (int(cx + 30), int(cy + 30)), (0, 0, 0), 7)
                            cv2.line(frame, (int(cx + 30), int(cy - 30)), (int(cx - 30), int(cy + 30)), (0, 0, 0), 7)
                        elif symbol == "O":
                            cv2.circle(frame, (int(cx), int(cy)), 32, (0, 0, 0), 7)
                cv2.putText(frame, "SYNTHETIC DEMO / NOT A REAL MATCH", (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 230, 220), 1)
                writer.write(frame)
        finally:
            writer.release()
        print(path)


if __name__ == "__main__":
    generate()
