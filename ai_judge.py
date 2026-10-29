"""Local video referee for a calibrated family game setup, Python 3.10+.

Vision results are estimates for review. Player IDs come from explicit lane/clip
assignments, never inferred identities. SHA-256 checks integrity, not authorship.
"""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import math
from pathlib import Path
from typing import Callable

GAMES = ("football", "tic_tac_toe", "rock_paper_scissors", "red_light_green_light", "basketball")
MODEL_DIR = Path(__file__).resolve().parent / "models"


class JudgeError(ValueError):
    """An actionable input, dependency, or observation error."""


@dataclass
class JudgeConfig:
    duration: float = 60.0
    points: int = 1
    player_a: str = "P1"
    player_b: str = "P3"
    active_team: str = "A"
    active_player: str = "P1"
    ball_color: str = "orange"
    goal_x: float = 0.78
    goal_y_min: float = 0.25
    goal_y_max: float = 0.75
    goal_direction: str = "right"
    hoop_y: float = 0.45
    hoop_x_min: float = 0.35
    hoop_x_max: float = 0.65
    cooldown: float = 1.5
    green_seconds: float = 4.0
    red_seconds: float = 3.0
    grace_seconds: float = 0.5
    motion_threshold: float = 0.035
    video_offset: float = 0.0
    board_roi: tuple = (0.1, 0.1, 0.8, 0.8)

    def validate(self):
        values = (self.duration, self.cooldown, self.green_seconds, self.red_seconds,
                  self.grace_seconds, self.motion_threshold, self.video_offset,
                  self.goal_x, self.goal_y_min, self.goal_y_max, self.hoop_y,
                  self.hoop_x_min, self.hoop_x_max)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise JudgeError("Cấu hình phải chứa số hữu hạn.")
        if not 1 <= self.duration <= 600 or type(self.points) is not int or not 1 <= self.points <= 10:
            raise JudgeError("Thời gian 1–600 giây; điểm mỗi lượt là số nguyên 1–10.")
        if not 0 < self.goal_x < 1 or not 0 <= self.goal_y_min < self.goal_y_max <= 1:
            raise JudgeError("Vùng cầu môn không hợp lệ.")
        if not 0 < self.hoop_y < 1 or not 0 <= self.hoop_x_min < self.hoop_x_max <= 1:
            raise JudgeError("Vùng vành rổ không hợp lệ.")
        if self.goal_direction not in ("left", "right") or self.ball_color not in ("orange", "yellow", "green", "white"):
            raise JudgeError("Hướng cầu môn hoặc màu bóng không hợp lệ.")
        if self.active_team not in ("A", "B") or not self.active_player:
            raise JudgeError("Cần gán người chơi và đội cho clip.")
        if not self.player_a or not self.player_b or self.player_a == self.player_b:
            raise JudgeError("Hai làn phải được gán cho hai người chơi khác nhau.")
        if not 0.2 <= self.cooldown <= 10 or not 0.5 <= self.green_seconds <= 30 or not 1 <= self.red_seconds <= 30:
            raise JudgeError("Chu kỳ đèn hoặc thời gian chống đếm lặp không hợp lệ.")
        if not 0 <= self.grace_seconds < self.red_seconds or not 0.005 <= self.motion_threshold <= 0.3:
            raise JudgeError("Ngưỡng chuyển động hoặc thời gian phản ứng không hợp lệ.")
        if not 0 <= self.video_offset <= 600:
            raise JudgeError("Độ lệch video phải nằm trong 0–600 giây.")
        if len(self.board_roi) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in self.board_roi):
            raise JudgeError("Vùng bàn cờ phải có bốn số x, y, rộng, cao.")
        x, y, w, h = self.board_roi
        if min(x, y) < 0 or min(w, h) <= 0 or x + w > 1 or y + h > 1:
            raise JudgeError("Vùng bàn cờ phải nằm trong ảnh.")
        return self


def canonical_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sign_results(data: dict) -> dict:
    """Return a detached JSON payload, so later nested edits cannot alter it."""
    result = json.loads(canonical_bytes({k: v for k, v in data.items() if k != "hash"}))
    result["hash"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    return result


def verify_results_hash(results_dict: dict) -> bool:
    if not isinstance(results_dict, dict):
        return False
    provided = results_dict.get("hash")
    if not isinstance(provided, str) or len(provided) != 64 or any(c not in "0123456789abcdef" for c in provided):
        return False
    try:
        payload = {k: v for k, v in results_dict.items() if k != "hash"}
        return hmac.compare_digest(provided, hashlib.sha256(canonical_bytes(payload)).hexdigest())
    except (ValueError, TypeError, OverflowError):
        return False


WIN_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))


def board_outcome(board: list[str]) -> str | None:
    if len(board) != 9 or any(c not in ("", "X", "O") for c in board):
        raise JudgeError("Bàn cờ cần 9 ô X/O/trống.")
    nx, no = board.count("X"), board.count("O")
    wins = {board[a] for a, b, c in WIN_LINES if board[a] and board[a] == board[b] == board[c]}
    if nx not in (no, no + 1) or len(wins) > 1 or ("X" in wins and nx != no + 1) or ("O" in wins and nx != no):
        raise JudgeError("Trạng thái bàn cờ không hợp lệ: X đi trước và hai bên luân phiên.")
    return next(iter(wins)) if wins else ("draw" if "" not in board else None)


def play_move(board: list[str], cell: int) -> list[str]:
    if board_outcome(board) is not None:
        raise JudgeError("Ván cờ đã kết thúc.")
    if type(cell) is not int or not 0 <= cell < 9 or board[cell]:
        raise JudgeError("Hãy chọn ô trống.")
    new = list(board)
    new[cell] = "X" if board.count("X") == board.count("O") else "O"
    return new


def rps_winner(a: str, b: str) -> str | None:
    if a not in ("rock", "paper", "scissors") or b not in ("rock", "paper", "scissors"):
        raise JudgeError("Cử chỉ phải là kéo, búa hoặc bao.")
    if a == b:
        return None
    return "A" if (a, b) in (("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")) else "B"


def light_state(t: float, config: JudgeConfig) -> tuple[str, int, float]:
    phase = max(0.0, t) % (config.green_seconds + config.red_seconds)
    cycle = int(max(0.0, t) // (config.green_seconds + config.red_seconds))
    return ("green", cycle, phase) if phase < config.green_seconds else ("red", cycle, phase - config.green_seconds)


class LineCrossing:
    """Count a continuous, directed crossing; gaps/jumps reset tracking.

    A ball must be observed on the approach side outside a hysteresis band.
    The crossing coordinate is interpolated; looking only at endpoints would
    count balls that crossed outside the mouth of the goal/hoop.
    """
    def __init__(self, axis: int, line: float, low: float, high: float, direction: int, cooldown: float):
        self.axis, self.line, self.low, self.high = axis, line, low, high
        self.direction, self.cooldown = direction, cooldown
        self.previous = None
        self.armed = False
        self.last_score = -math.inf

    def update(self, point, t: float) -> bool:
        if point is None:
            self.previous, self.armed = None, False
            return False
        signed = (point[self.axis] - self.line) * self.direction
        old = self.previous
        self.previous = (point, t)
        if old is None or not 0 < t - old[1] <= 0.35 or math.dist(point, old[0]) > 0.25:
            self.armed = signed < -0.025
            return False
        if signed < -0.025:
            self.armed = True
        prev = (old[0][self.axis] - self.line) * self.direction
        if self.armed and prev < 0 <= signed:
            self.armed = False
            fraction = -prev / max(signed - prev, 1e-9)
            cross = old[0][1 - self.axis] + fraction * (point[1 - self.axis] - old[0][1 - self.axis])
            if self.low <= cross <= self.high and t - self.last_score >= self.cooldown:
                self.last_score = t
                return True
        return False


class RPSRounds:
    """A stable pair is one throw. Both hands must disappear before the next."""
    def __init__(self, hold=0.55, reset=0.4):
        self.hold, self.reset = hold, reset
        self.pair, self.since, self.absent_since = None, 0.0, None
        self.locked = False

    def update(self, a, b, t):
        if a is None and b is None:
            if self.absent_since is None:
                self.absent_since = t
            if t - self.absent_since >= self.reset:
                self.locked = False
        else:
            self.absent_since = None
        if a is None or b is None:
            self.pair = None
            return None
        pair = (a, b)
        if pair != self.pair:
            self.pair, self.since = pair, t
        if not self.locked and t - self.since >= self.hold:
            self.locked = True
            return {"a": a, "b": b, "winner": rps_winner(a, b)}
        return None


class RedLightJudge:
    """Compare pose to a fixed red-phase baseline, so slow drift is caught."""
    def __init__(self, config: JudgeConfig):
        self.config = config
        self.phases = {}
        self.previous = {}

    def update(self, poses: dict, t: float):
        color, cycle, age = light_state(t, self.config)
        if color != "red" or age < self.config.grace_seconds:
            self.previous.clear()
            return
        for team in ("A", "B"):
            state = self.phases.setdefault((cycle, team), {"baseline": None, "observed": 0.0, "violation": False})
            pose = poses.get(team)
            if pose is None:
                self.previous.pop(team, None)
                continue
            old = self.previous.get(team)
            if old is not None and old[0] == cycle:
                state["observed"] += min(max(t - old[1], 0), 0.25)
            self.previous[team] = (cycle, t)
            if state["baseline"] is None:
                state["baseline"] = pose
            displacement = max(math.dist(pose[k], state["baseline"][k]) for k in pose)
            if displacement > self.config.motion_threshold:
                state["violation"] = True

    def events(self, last_t: float):
        result = []
        length = self.config.green_seconds + self.config.red_seconds
        for (cycle, team), phase in sorted(self.phases.items()):
            end = (cycle + 1) * length
            required = (self.config.red_seconds - self.config.grace_seconds) * 0.7
            if end > last_t + 0.06:
                continue  # Never award a partial phase at end of video.
            if phase["violation"]:
                result.append({"time": round(end, 3), "team": team, "kind": "red_movement", "points": 0})
            elif phase["observed"] >= required:
                result.append({"time": round(end, 3), "team": team, "kind": "red_survived", "points": self.config.points})
        return result


def make_result(game: str, scores: dict, activity: dict, events: list, config: JudgeConfig,
                source: str, details: str, **extra) -> dict:
    player_points = Counter()
    for event in events:
        if event.get("player"):
            player_points[event["player"]] += event.get("points", 0)
    candidates = [p for p in set(activity) | set(player_points) if activity.get(p, 0) > 0 or player_points[p] > 0]
    top = max(((player_points[p], round(activity.get(p, 0), 2)) for p in candidates), default=None)
    mvps = sorted(p for p in candidates if (player_points[p], round(activity.get(p, 0), 2)) == top)
    return sign_results({
        "schema_version": 1, "game_type": game,
        "team_a_score": scores.get("A", 0), "team_b_score": scores.get("B", 0),
        "winner": "A" if scores.get("A", 0) > scores.get("B", 0) else "B" if scores.get("B", 0) > scores.get("A", 0) else "draw",
        "mvp": ", ".join(mvps) if mvps else None,
        "mvp_basis": "Điểm, sau đó thời gian quan sát; người chơi được gán theo clip/làn.",
        "player_points": dict(player_points),
        "observed_seconds": {p: round(v, 3) for p, v in sorted(activity.items())},
        "details": details, "events": events, "config": asdict(config), "source": source, **extra,
    })


def judge_board(board: list[str], config: JudgeConfig | None = None) -> dict:
    cfg = (config or JudgeConfig()).validate()
    outcome = board_outcome(board)
    if outcome is None:
        raise JudgeError("Ván cờ chưa kết thúc.")
    team = "A" if outcome == "X" else "B" if outcome == "O" else None
    scores = {"A": 0, "B": 0}
    events = []
    if team:
        scores[team] = cfg.points
        events.append({"time": 0, "kind": "tic_tac_toe_win", "team": team,
                       "player": cfg.player_a if team == "A" else cfg.player_b, "points": cfg.points})
    return make_result("tic_tac_toe", scores, {}, events, cfg, "interactive",
                       "Hòa." if not team else f"{outcome} hoàn thành hàng 3 ô.", board=board)


def _cv():
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise JudgeError("Thiếu OpenCV/NumPy. Chạy: python -m pip install -r requirements.txt") from exc
    return cv2, np


def detect_ball(frame, color: str):
    cv2, np = _cv()
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    ranges = {"orange": ((3, 110, 100), (25, 255, 255)), "yellow": ((23, 100, 100), (38, 255, 255)),
              "green": ((40, 100, 80), (85, 255, 255)), "white": ((0, 0, 185), (179, 65, 255))}
    low, high = ranges[color]
    mask = cv2.inRange(hsv, np.array(low, np.uint8), np.array(high, np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = frame.shape[:2]
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if not 0.00008 * w * h < area < 0.025 * w * h or perimeter == 0:
            continue
        circularity = 4 * math.pi * area / perimeter ** 2
        (x, y), radius = cv2.minEnclosingCircle(contour)
        fill = area / max(math.pi * radius * radius, 1)
        if circularity >= 0.65 and fill >= 0.65:
            candidates.append((area * circularity, (x / w, y / h)))
    # Ambiguous similarly sized blobs are not a usable ball observation.
    candidates.sort(reverse=True)
    if not candidates or (len(candidates) > 1 and candidates[1][0] > candidates[0][0] * 0.65):
        return None
    return candidates[0][1]


def classify_hand(landmarks) -> str | None:
    def distance(a, b):
        return math.sqrt(sum((getattr(landmarks[a], k) - getattr(landmarks[b], k)) ** 2 for k in ("x", "y", "z")))
    # Distance to wrist is orientation-independent; ambiguous bends are rejected.
    extended = []
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        ratio = distance(tip, 0) / max(distance(pip, 0), 1e-5)
        if 1.08 < ratio < 1.2:
            return None
        extended.append(ratio >= 1.2)
    return {(False, False, False, False): "rock", (True, True, True, True): "paper",
            (True, True, False, False): "scissors"}.get(tuple(extended))


def _landmarker(kind: str):
    try:
        import mediapipe as mp
    except ImportError as exc:
        raise JudgeError("Thiếu MediaPipe. Chạy: python -m pip install -r requirements.txt") from exc
    filename = "hand_landmarker.task" if kind == "hand" else "pose_landmarker_lite.task"
    model = MODEL_DIR / filename
    if not model.is_file():
        raise JudgeError(f"Thiếu models/{filename}. Chạy: python download_models.py")
    vision = mp.tasks.vision
    base = mp.tasks.BaseOptions(model_asset_path=str(model), delegate=mp.tasks.BaseOptions.Delegate.CPU)
    try:
        if kind == "hand":
            detector = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                base_options=base, running_mode=vision.RunningMode.VIDEO, num_hands=2,
                min_hand_detection_confidence=0.6, min_hand_presence_confidence=0.6))
        else:
            detector = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=base, running_mode=vision.RunningMode.VIDEO, num_poses=2,
                min_pose_detection_confidence=0.6, min_pose_presence_confidence=0.6))
    except Exception as exc:
        raise JudgeError(f"Không khởi tạo được MediaPipe: {exc}") from exc
    return detector, mp


def read_board(frame, roi) -> list[str] | None:
    """Read large black X/O on a white, axis-aligned 3x3 board.

    Grid borders are excluded. An unrecognized cell invalidates this frame.
    """
    cv2, np = _cv()
    height, width = frame.shape[:2]
    x, y, w, h = roi
    crop = frame[int(y * height):int((y + h) * height), int(x * width):int((x + w) * width)]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(cv2.resize(crop, (360, 360)), cv2.COLOR_BGR2GRAY)
    board = []
    for row in range(3):
        for col in range(3):
            cell = gray[row * 120 + 16:row * 120 + 104, col * 120 + 16:col * 120 + 104]
            _, mask = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
            if float(np.mean(cell)) > 220 and float(np.mean(mask > 0)) < 0.025:
                board.append("")
                continue
            contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            if not contours or hierarchy is None:
                return None
            idx = max(range(len(contours)), key=lambda i: cv2.contourArea(contours[i]))
            contour = contours[idx]
            area = cv2.contourArea(contour)
            if area < 80:
                return None
            bx, by, bw, bh = cv2.boundingRect(contour)
            if not 0.55 < bw / max(bh, 1) < 1.8:
                return None
            child = hierarchy[0][idx][2]
            perimeter = cv2.arcLength(contour, True)
            if child >= 0 and cv2.contourArea(contours[child]) > area * 0.25 and 4 * math.pi * area / max(perimeter ** 2, 1) > 0.65:
                board.append("O")
                continue
            normalized = cv2.resize(mask[by:by + bh, bx:bx + bw], (64, 64)) > 0
            yy, xx = np.indices((64, 64))
            diagonal = (np.abs(xx - yy) < 10) | (np.abs(xx + yy - 63) < 10)
            overlap = np.count_nonzero(normalized & diagonal) / max(np.count_nonzero(normalized), 1)
            quadrants = [np.count_nonzero(normalized[r:r + 24, c:c + 24]) for r in (0, 40) for c in (0, 40)]
            if child < 0 and overlap > 0.82 and min(quadrants) > 25:
                board.append("X")
            else:
                return None
    try:
        board_outcome(board)
    except JudgeError:
        return None
    return board


def preview_frame(video_path: str, config: JudgeConfig, game_type: str):
    cv2, _ = _cv()
    capture = cv2.VideoCapture(str(video_path))
    try:
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise JudgeError("Không đọc được khung hình đầu tiên.")
    h, w = frame.shape[:2]
    green = (80, 220, 40)
    if game_type == "football":
        cv2.line(frame, (int(config.goal_x * w), int(config.goal_y_min * h)), (int(config.goal_x * w), int(config.goal_y_max * h)), green, 4)
    elif game_type == "basketball":
        cv2.line(frame, (int(config.hoop_x_min * w), int(config.hoop_y * h)), (int(config.hoop_x_max * w), int(config.hoop_y * h)), green, 4)
    elif game_type == "tic_tac_toe":
        x, y, rw, rh = config.board_roi
        cv2.rectangle(frame, (int(x * w), int(y * h)), (int((x + rw) * w), int((y + rh) * h)), green, 3)
    else:
        cv2.line(frame, (w // 2, 0), (w // 2, h), green, 3)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def process_game_video(video_path: str, game_type: str, config: JudgeConfig | None = None,
                       progress_callback: Callable[[float], None] | None = None) -> dict:
    """Analyze real frames; no hardcoded scores or silent dependency fallbacks."""
    if game_type not in GAMES:
        raise JudgeError(f"Trò chơi không được hỗ trợ: {game_type}")
    cfg = (config or JudgeConfig()).validate()
    path = Path(video_path)
    if not path.is_file() or path.stat().st_size == 0:
        raise JudgeError("Video không tồn tại hoặc rỗng.")
    if path.stat().st_size > 150 * 1024 * 1024:
        raise JudgeError("Video tối đa 150 MB.")
    cv2, _ = _cv()
    scores, activity, events = {"A": 0, "B": 0}, Counter(), []
    warnings = []
    pair_rounds, light_judge = RPSRounds(), RedLightJudge(cfg)
    tracker = LineCrossing(0, cfg.goal_x, cfg.goal_y_min, cfg.goal_y_max,
                           1 if cfg.goal_direction == "right" else -1, cfg.cooldown) if game_type == "football" else LineCrossing(
                               1, cfg.hoop_y, cfg.hoop_x_min, cfg.hoop_x_max, 1, cfg.cooldown)
    stable_board, stable_since, final_board = None, 0.0, None
    observed, sampled, frames_read, last_t = 0, 0, 0, 0.0
    with ExitStack() as stack:
        cap = cv2.VideoCapture(str(path))
        stack.callback(cap.release)
        if not cap.isOpened():
            raise JudgeError("Không mở được video. Hãy dùng MP4 H.264 hoặc AVI MJPEG.")
        fps, total = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(fps) or not 1 <= fps <= 240:
            raise JudgeError("Video thiếu tốc độ khung hình hợp lệ (1–240 FPS).")
        if cap.get(cv2.CAP_PROP_FRAME_WIDTH) * cap.get(cv2.CAP_PROP_FRAME_HEIGHT) > 4096 * 2160:
            raise JudgeError("Hãy giảm video xuống độ phân giải tối đa 4K.")
        step = max(1, int(fps / (24 if game_type in ("football", "basketball") else 12)))
        detector = mp = None
        if game_type in ("rock_paper_scissors", "red_light_green_light"):
            detector, mp = _landmarker("hand" if game_type == "rock_paper_scissors" else "pose")
            stack.callback(detector.close)
        previous_visible = set()
        previous_t = None
        while frames_read / fps < cfg.duration:
            ok, frame = cap.read()
            if not ok:
                break
            index = frames_read
            frames_read += 1
            last_t = frames_read / fps
            if index % step:
                continue
            t = index / fps
            sampled += 1
            if frame.shape[1] > 960:
                frame = cv2.resize(frame, (960, max(1, round(frame.shape[0] * 960 / frame.shape[1]))))
            visible = set()
            if game_type in ("football", "basketball"):
                point = detect_ball(frame, cfg.ball_color)
                if point is not None:
                    visible.add(cfg.active_player)
                if tracker.update(point, t):
                    scores[cfg.active_team] += cfg.points
                    events.append({"time": round(t, 3), "kind": "goal_candidate" if game_type == "football" else "basket_candidate",
                                   "team": cfg.active_team, "player": cfg.active_player, "points": cfg.points})
            elif game_type in ("rock_paper_scissors", "red_light_green_light"):
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                detection = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(round(t * 1000)))
                lanes = {"A": [], "B": []}
                if game_type == "rock_paper_scissors":
                    for hand in detection.hand_landmarks:
                        lanes["A" if hand[0].x < 0.5 else "B"].append(classify_hand(hand))
                    gestures = {team: hands[0] if len(hands) == 1 else None for team, hands in lanes.items()}
                    visible = {cfg.player_a if team == "A" else cfg.player_b for team, gesture in gestures.items() if gesture is not None}
                    throw = pair_rounds.update(gestures["A"], gestures["B"], t)
                    if throw:
                        winner = throw["winner"]
                        if winner:
                            scores[winner] += cfg.points
                        events.append({"time": round(t, 3), "kind": "rps_round", "team": winner,
                                       "player": (cfg.player_a if winner == "A" else cfg.player_b) if winner else None,
                                       "points": cfg.points if winner else 0, **throw})
                else:
                    for pose in detection.pose_landmarks:
                        keys = (11, 12, 15, 16, 23, 24, 27, 28)
                        if all(pose[k].visibility >= 0.6 for k in keys):
                            center = (pose[23].x + pose[24].x) / 2
                            lanes["A" if center < 0.5 else "B"].append({k: (pose[k].x, pose[k].y) for k in keys})
                    poses = {team: items[0] for team, items in lanes.items() if len(items) == 1}
                    visible = {cfg.player_a if team == "A" else cfg.player_b for team in poses}
                    light_judge.update(poses, t + cfg.video_offset)
            else:
                board = read_board(frame, cfg.board_roi)
                if board is None:
                    stable_board, final_board = None, None
                else:
                    observed += 1
                    if board != stable_board:
                        stable_board, stable_since, final_board = board, t, None
                    if t - stable_since >= 0.6:
                        final_board = board
            if visible:
                observed += 1
            if previous_t is not None:
                for player in visible & previous_visible:
                    activity[player] += min(t - previous_t, 0.25)
            previous_t, previous_visible = t, visible
            if progress_callback and sampled % 12 == 0:
                expected = min(total, cfg.duration * fps) if total > 0 else cfg.duration * fps
                progress_callback(min(frames_read / max(expected, 1), 0.99))
        if frames_read < 2:
            raise JudgeError("Video không có đủ khung hình để phân tích.")
    if not observed:
        raise JudgeError("Không nhận diện được bóng/người/bàn cờ phù hợp. Kiểm tra màu bóng, ánh sáng, góc quay và vùng chấm điểm.")
    if game_type == "tic_tac_toe":
        if final_board is None:
            raise JudgeError("Không đọc được bàn cờ ổn định ở cuối clip. Giữ nguyên bàn cờ ít nhất 1 giây.")
        result = judge_board(final_board, cfg)
        scores = {"A": result["team_a_score"], "B": result["team_b_score"]}
        events = result["events"]
    if game_type == "red_light_green_light":
        events = light_judge.events(last_t + cfg.video_offset)
        for event in events:
            event["player"] = cfg.player_a if event["team"] == "A" else cfg.player_b
            scores[event["team"]] += event["points"]
    if observed / max(sampled, 1) < 0.5:
        warnings.append("Đối tượng nhìn thấy ở dưới 50% khung hình; hãy xem lại video trước khi lưu điểm.")
    if not events:
        warnings.append("Không có lượt ghi điểm hoàn chỉnh; kết quả 0–0 không chứng minh cả hai đội đã thi đấu.")
    if total > cfg.duration * fps + 1:
        warnings.append(f"Chỉ phân tích {cfg.duration:g} giây đầu theo thời gian đã đặt.")
    details = {"football": "Ước lượng bóng vượt vạch cầu môn theo hướng đã chọn.",
               "basketball": "Ước lượng bóng đi xuống qua vành rổ trong vùng đã chọn; mỗi lần tính điểm cố định.",
               "rock_paper_scissors": "Hai tay ở hai nửa ảnh; giữ cử chỉ 0,55 giây, rút cả hai tay để bắt đầu lượt mới.",
               "red_light_green_light": "Mỗi pha đỏ hoàn chỉnh đứng yên nhận điểm; chuyển động mất điểm của pha đó. Cần nhìn rõ toàn thân.",
               "tic_tac_toe": "Đọc trạng thái bàn cờ kết thúc từ các khung hình ổn định cuối clip."}[game_type]
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if progress_callback:
        progress_callback(1.0)
    return make_result(game_type, scores, activity, events, cfg, "video", details,
                       video_sha256=digest.hexdigest(), duration_seconds=round(last_t, 3),
                       frames_analyzed=sampled, observation_ratio=round(observed / max(sampled, 1), 3),
                       warnings=warnings, **({"board": final_board} if game_type == "tic_tac_toe" else {}))
