"""Family AI Game Day — run with: streamlit run app.py."""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import html
import json
import math
from pathlib import Path
import tempfile
import time
import uuid

import streamlit as st

from ai_judge import (GAMES, MODEL_DIR, JudgeConfig, JudgeError, board_outcome,
                      canonical_bytes, judge_board, light_state, make_result,
                      play_move, preview_frame, process_game_video, sign_results,
                      verify_results_hash)

ROOT = Path(__file__).resolve().parent
LABELS = {
    "football": ("⚽", "Football", "Football", "Score by kicking the ball across the goal line."),
    "tic_tac_toe": ("✕", "Tic Tac Toe", "3 × 3 board", "Take turns placing X and O. Get three in a row to win."),
    "rock_paper_scissors": ("✌️", "Rock Paper Scissors", "Rock · Paper · Scissors", "Show your hands. AI reads the gestures and scores each round."),
    "red_light_green_light": ("🚦", "Red Light Green Light", "Red Light · Green Light", "Move on green. Freeze in place on red."),
    "basketball": ("🏀", "Basketball", "Basketball", "Aim carefully. Score when the ball passes through the hoop."),
}
STEPS = ("Choose a game", "Players & teams", "Rules & setup", "Game time", "AI referee", "Scoreboard")


st.set_page_config(page_title="Family AI · Game Day", page_icon="🏟️", layout="wide")
st.markdown("""
<style>
.block-container {max-width:1160px;padding-top:2.3rem;padding-bottom:4rem;}
h1,h2,h3 {letter-spacing:-.035em;}
h1 {font-size:3rem !important;line-height:1.1 !important;}
[data-testid="stSidebar"] {border-right:1px solid #d9dfd5;}
[data-testid="stButton"] button {border-radius:12px;min-height:44px;font-weight:600;}
[data-testid="stMetric"] {background:#eeeee6;padding:16px 20px;border-radius:14px;}
.eyebrow {font-size:.73rem;letter-spacing:.18em;font-weight:800;color:#087f70;text-transform:uppercase;}
.hero {background:#163a35;color:#f8f7f2;border-radius:24px;padding:36px 40px;margin:16px 0 26px;position:relative;overflow:hidden;}
.hero h1 {color:#f8f7f2;max-width:700px;margin-bottom:14px;}
.hero p {color:#c4d9ce;font-size:1.08rem;max-width:640px;}
.hero .eyebrow {color:#d7e890;margin-bottom:18px;}
.chip {display:inline-block;border:1px solid #668174;border-radius:99px;padding:5px 12px;font-size:.76rem;color:#edf3df;margin-right:7px;}
.game-icon {font-size:2.2rem;line-height:1.3;margin:5px 0 16px;}
.muted {color:#657a70;font-size:.9rem;}
.timer {font-size:4.2rem;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.05em;text-align:center;}
.signal {padding:24px;border-radius:18px;text-align:center;font-size:1.7rem;font-weight:800;letter-spacing:.04em;}
.signal.green {background:#d5edcb;color:#1f6c31;}
.signal.red {background:#f7d6cc;color:#9b3529;}
.score {font-size:3.2rem;font-weight:800;text-align:center;line-height:1.2;}
.team {text-align:center;color:#657a70;text-transform:uppercase;letter-spacing:.12em;font-size:.8rem;}
</style>
""", unsafe_allow_html=True)


def initialize():
    defaults = {
        "step": 0, "unlocked": 0, "game": "football", "config": asdict(JudgeConfig()),
        "players": {"P1": "Player 1", "P2": "Player 2", "P3": "Player 3", "P4": "Player 4"},
        "teams": {"A": "Green Team", "B": "Yellow Team"}, "reports": [],
        "round_id": uuid.uuid4().hex, "board": [""] * 9, "started_at": None,
        "result": None, "analysis_key": None, "saved": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize()
S = st.session_state


def cfg():
    return JudgeConfig(**S.config)


def go(step):
    S.step = step
    S.unlocked = max(S.unlocked, step)
    st.rerun()


def new_round():
    S.round_id = uuid.uuid4().hex
    S.board, S.started_at = [""] * 9, None
    S.result, S.analysis_key, S.saved = None, None, False
    S.step, S.unlocked = 0, 0
    st.rerun()


def display_player(pid):
    return f"{pid} · {S.players.get(pid, pid)}"


def wrapped_result(result):
    return sign_results({**result, "round_id": S.round_id, "players": S.players, "teams": S.teams})


def choose_game():
    st.markdown('<div class="eyebrow">Family game day</div>', unsafe_allow_html=True)
    st.markdown('''<div class="hero"><div class="eyebrow">FAMILY AI / GAME DAY</div>
    <h1>Play your best.<br>Let AI keep score.</h1>
    <p>Five challenges, two teams, one great day. Choose your first game and make it memorable.</p>
    <span class="chip">5 games</span><span class="chip">4 players</span><span class="chip">Video referee</span></div>''', unsafe_allow_html=True)
    st.subheader("What shall we play today?")
    for group in (GAMES[:3], GAMES[3:]):
        columns = st.columns(len(group))
        for column, game in zip(columns, group):
            emoji, name, subtitle, description = LABELS[game]
            with column, st.container(border=True):
                st.markdown(f'<div class="game-icon">{emoji}</div>', unsafe_allow_html=True)
                st.subheader(name)
                st.caption(subtitle)
                st.write(description)
                if st.button("Choose this game →", key=f"pick_{game}", use_container_width=True):
                    S.game = game
                    S.config = asdict(replace(cfg(), points=2 if game == "basketball" else 1))
                    go(1)
    st.caption("Videos are processed on this server. Review events before adding scores to the tournament.")


def setup_players():
    st.title("Meet your teammates.")
    st.write("Each team has two players. Choose representatives next; switch representatives between rounds.")
    if S.reports:
        st.info("Keep player names unchanged during the tournament so scores and MVP tracking stay consistent.")
        for team, ids in (("A", ("P1", "P2")), ("B", ("P3", "P4"))):
            st.write(f"**{S.teams[team]}** · " + " · ".join(display_player(p) for p in ids))
        if st.button("Keep teams & continue →", type="primary"):
            go(2)
        return
    with st.form("players_form"):
        cols = st.columns(2)
        names, teams = {}, {}
        for column, team, players in zip(cols, ("A", "B"), (("P1", "P2"), ("P3", "P4"))):
            with column:
                st.subheader(f"Team {team}")
                teams[team] = st.text_input(f"Team name {team}", value=S.teams[team], max_chars=40).strip()
                for pid in players:
                    names[pid] = st.text_input(f"Name {pid}", value=S.players[pid], max_chars=40).strip()
        if st.form_submit_button("Save teams & continue →", type="primary"):
            if not all(names.values()) or not all(teams.values()):
                st.error("Enter names for all four players and both teams.")
            elif len({v.casefold() for v in names.values()}) != 4 or teams["A"].casefold() == teams["B"].casefold():
                st.error("Player and team names must be unique for a clear scoreboard.")
            else:
                S.players, S.teams = names, teams
                go(2)


def rules():
    st.title("Clear rules. Great games.")
    descriptions = {
        "football": "Take turns shooting: one player per clip. A ball crossing the line in the correct direction scores. Keep the camera still. Use a brightly colored ball and avoid similarly colored objects.",
        "basketball": "Take turns shooting: one player per clip. The ball scores when it travels down through the calibrated hoop. Film from the side so the ball is visible before and after the hoop.",
        "tic_tac_toe": "Team A uses X and Team B uses O. X goes first. Take turns choosing an empty square; three in a row wins. Play on screen or upload a board video.",
        "rock_paper_scissors": "Player A shows one hand on the left half of the frame; Player B uses the right. Hold each gesture for at least 0.55 seconds. Both players must remove their hands for at least 0.4 seconds between turns. Rock beats scissors, scissors beat paper, and paper beats rock.",
        "red_light_green_light": "Each player stands in one half of the frame with their full body visible. Move on green. Freeze after the reaction time when the light turns red. Valid completed red phases score; movement loses that phase’s point.",
    }
    st.info(descriptions[S.game])
    current = cfg()
    player_labels = {pid: display_player(pid) for pid in S.players}
    team_labels = dict(S.teams)
    with st.form("rules_form"):
        left, right = st.columns(2)
        with left:
            duration = st.number_input("Round duration (seconds)", min_value=10, max_value=600, value=int(current.duration), step=10)
            player_a = st.selectbox("Team A representative / left side / X", ("P1", "P2"), format_func=player_labels.__getitem__,
                                    index=("P1", "P2").index(current.player_a))
        with right:
            points = st.number_input("Points per win / score", min_value=1, max_value=10, value=current.points)
            player_b = st.selectbox("Team B representative / right side / O", ("P3", "P4"), format_func=player_labels.__getitem__,
                                    index=("P3", "P4").index(current.player_b))
        active_team, color = current.active_team, current.ball_color
        green, red, grace = current.green_seconds, current.red_seconds, current.grace_seconds
        if S.game in ("football", "basketball"):
            active_team = st.radio("Team playing this clip", ("A", "B"), format_func=team_labels.__getitem__, horizontal=True)
            color = st.selectbox("Ball color", ("orange", "yellow", "green", "white"),
                                 format_func=lambda c: {"orange": "Orange", "yellow": "Yellow", "green": "Green", "white": "White"}[c])
            st.caption("Score each clip, then start a new round for the other team. You assign the shooter/player.")
        if S.game == "red_light_green_light":
            a, b, c = st.columns(3)
            green = a.number_input("Green light (seconds)", 1.0, 15.0, current.green_seconds, 0.5)
            red = b.number_input("Red light (seconds)", 1.0, 15.0, current.red_seconds, 0.5)
            grace = c.number_input("Reaction time (seconds)", 0.0, 0.9, current.grace_seconds, 0.1)
            st.caption("Start recording when you start the round. If recording begins early, enter the offset during video review.")
        st.write("**On a tie:** keep the tie, or play a tiebreaker round.")
        st.caption("MVP is based on score, then observed time; ties share MVP.")
        if st.form_submit_button("Ready to play →", type="primary"):
            config = replace(current, duration=float(duration), points=points, player_a=player_a, player_b=player_b,
                             active_team=active_team, active_player=player_a if active_team == "A" else player_b,
                             ball_color=color, green_seconds=green, red_seconds=red, grace_seconds=grace)
            try:
                config.validate()
            except JudgeError as exc:
                st.error(str(exc))
            else:
                S.config = asdict(config)
                go(3)


def finish_round():
    if S.game == "tic_tac_toe" and S.started_at is not None:
        if board_outcome(S.board):
            S.result = wrapped_result(judge_board(S.board, cfg()))
        else:
            S.result = wrapped_result(make_result("tic_tac_toe", {"A": 0, "B": 0}, {}, [], cfg(), "interactive",
                                                 "Round ended without a winning line: 0–0 tie.", board=S.board))
    go(4)


@st.fragment(run_every=0.25)
def round_clock():
    elapsed = 0.0 if S.started_at is None else time.monotonic() - S.started_at
    remaining = max(0, math.ceil(cfg().duration - elapsed))
    st.markdown(f'<div class="timer">{remaining // 60:02d}:{remaining % 60:02d}</div>', unsafe_allow_html=True)
    st.progress(min(elapsed / cfg().duration, 1.0))
    if S.game == "red_light_green_light":
        color, _, age = light_state(elapsed, cfg())
        label = "GREEN LIGHT · MOVE" if color == "green" else "RED LIGHT · FREEZE"
        if S.started_at is None:
            label = "READY · WAIT TO START"
        st.markdown(f'<div class="signal {color}">{label}</div>', unsafe_allow_html=True)
        if color == "red" and age < cfg().grace_seconds:
            st.caption("Reaction time in progress.")
    if S.started_at is not None and remaining == 0:
        finish_round()


def active_round():
    st.title("Let the games begin.")
    st.write(f"**{S.teams['A']}** · {display_player(cfg().player_a)}　 vs　 **{S.teams['B']}** · {display_player(cfg().player_b)}")
    round_clock()
    if S.started_at is None:
        if st.button("▶ Start round", type="primary", use_container_width=True):
            S.started_at = time.monotonic()
            st.rerun()
    if S.game == "tic_tac_toe":
        current = "X" if S.board.count("X") == S.board.count("O") else "O"
        pid = cfg().player_a if current == "X" else cfg().player_b
        st.subheader(f"Turn {current} · {display_player(pid)}")
        for row in range(3):
            for col, column in enumerate(st.columns(3)):
                index = row * 3 + col
                if column.button(S.board[index] or "·", key=f"cell_{index}", use_container_width=True,
                                 disabled=bool(S.board[index]) or S.started_at is None):
                    # Check the deadline again inside the move handler.
                    if time.monotonic() - S.started_at >= cfg().duration:
                        finish_round()
                    S.board = play_move(S.board, index)
                    if board_outcome(S.board):
                        finish_round()
                    st.rerun()
    else:
        st.info("Record with a phone or webcam and upload the clip in the AI Referee step. Keep the camera fixed throughout the round.")
        if S.game == "red_light_green_light":
            st.caption("Show players the on-screen light. Start recording with the timer and do not pause the video.")
    left, right = st.columns(2)
    if left.button("End round →", disabled=S.started_at is None, use_container_width=True):
        finish_round()
    if right.button("I already have a video →", use_container_width=True):
        go(4)


def calibration(current):
    with st.expander("Calibrate scoring area", expanded=S.game in ("football", "basketball", "tic_tac_toe")):
        st.caption("Coordinates use image ratios: 0 is the left/top edge and 1 is the right/bottom edge. Align the green guide in the preview.")
        if S.game == "football":
            x = st.slider("Goal line position (X)", 0.05, 0.95, current.goal_x, 0.01)
            low, high = st.slider("Goal line endpoints (Y)", 0.0, 1.0, (current.goal_y_min, current.goal_y_max), 0.01)
            direction = st.selectbox("Goal direction", ("right", "left"),
                                     format_func=lambda d: "Left to right →" if d == "right" else "← Right to left")
            current = replace(current, goal_x=x, goal_y_min=low, goal_y_max=high, goal_direction=direction)
        elif S.game == "basketball":
            y = st.slider("Hoop height (Y)", 0.05, 0.95, current.hoop_y, 0.01)
            low, high = st.slider("Hoop edges (X)", 0.0, 1.0, (current.hoop_x_min, current.hoop_x_max), 0.01)
            current = replace(current, hoop_y=y, hoop_x_min=low, hoop_x_max=high)
        elif S.game == "tic_tac_toe":
            st.caption("Use a white board with black lines, filmed directly from above. Fit the calibration area tightly around the 3 × 3 board.")
            x1, x2 = st.slider("Board left/right edges", 0.0, 1.0, (0.1, 0.9), 0.01)
            y1, y2 = st.slider("Board top/bottom edges", 0.0, 1.0, (0.1, 0.9), 0.01)
            current = replace(current, board_roi=(x1, y1, x2 - x1, y2 - y1))
        elif S.game == "red_light_green_light":
            offset = st.number_input("At what timer second does the video start?", 0.0, 600.0, current.video_offset, 0.1)
            threshold = st.slider("Motion threshold (image ratio)", 0.005, 0.15, current.motion_threshold, 0.005)
            current = replace(current, video_offset=offset, motion_threshold=threshold)
        else:
            st.write("Team A stays on the left half of the frame; Team B stays on the right. Each player should show only one hand.")
    return current


def score_cards(result):
    left, center, right = st.columns((2, 1, 2))
    for col, team, score in ((left, "A", result["team_a_score"]), (right, "B", result["team_b_score"])):
        col.markdown(f'<div class="team">{html.escape(result.get("teams", S.teams)[team])}</div><div class="score">{score}</div>', unsafe_allow_html=True)
    center.markdown('<div class="score" style="color:#9eac9e">:</div>', unsafe_allow_html=True)


def review_result(result):
    st.subheader("Round results")
    score_cards(result)
    st.write(result["details"])
    for warning in result.get("warnings", []):
        st.warning(warning)
    if result.get("source") == "video":
        st.caption(f"Analyzed {result['frames_analyzed']} frames / {result['duration_seconds']} seconds. Visual events are estimates and should be reviewed.")
    if result["events"]:
        with st.expander("Scored events", expanded=True):
            st.dataframe(result["events"], hide_index=True, use_container_width=True)
    if verify_results_hash(result):
        st.success("SHA-256 matches the report content.")
    else:
        st.error("Report integrity check failed.")
        return
    st.caption("SHA-256 detects changes from the saved digest; it does not verify the creator or AI accuracy.")
    if st.button("Confirm & add to scoreboard →", type="primary", disabled=S.saved):
        # The same bytes cannot be scored a second time in this tournament,
        # even if the user changes a setting or starts a new round.
        source_digest = result.get("video_sha256")
        duplicate = any(r["round_id"] == result["round_id"] or (source_digest and source_digest == r.get("video_sha256")) for r in S.reports)
        if duplicate:
            st.error("This round or video has already been scored. Use a new clip for the next round.")
        else:
            S.reports = [*S.reports, result]
            S.saved = True
            go(5)


def ai_review():
    st.title("The referee is ready.")
    if S.result and S.result["source"] == "interactive":
        review_result(S.result)
        return
    st.write("Upload a video, calibrate the scoring area, and review events before saving scores.")
    current = calibration(cfg())
    file = st.file_uploader("Round video · up to 150 MB", type=("mp4", "mov", "avi", "mkv", "webm"), key=f"video_{S.round_id}")
    sample_paths = {"football": ROOT / "samples/football_demo.mp4", "basketball": ROOT / "samples/basketball_demo.mp4", "tic_tac_toe": ROOT / "samples/tic_tac_toe_demo.mp4"}
    sample = sample_paths.get(S.game)
    use_demo = False
    if sample and sample.exists():
        use_demo = st.checkbox("Use a demo video to test the workflow", key=f"demo_{S.round_id}")
        if use_demo:
            st.info("Synthetic demo clip for testing the detector. This is not a real game.")
            st.download_button("Download sample clip", sample.read_bytes(), file_name=sample.name, mime="video/mp4")
    if file is None and not use_demo:
        st.caption("Football/Basketball: one player per clip. Rock Paper Scissors/Red Light Green Light: representatives occupy opposite halves of the frame.")
        return
    data = sample.read_bytes() if use_demo else file.getvalue()
    if len(data) > 150 * 1024 * 1024:
        st.error("Video exceeds the 150 MB limit.")
        return
    suffix = ".mp4" if use_demo else Path(file.name).suffix
    fingerprint = hashlib.sha256(data + canonical_bytes(asdict(current))).hexdigest()
    if S.analysis_key != fingerprint:
        S.result = None
    # A unique, scoped directory is deleted after preview/analysis, including errors.
    with tempfile.TemporaryDirectory(prefix="family_ai_") as directory:
        path = Path(directory) / f"clip{suffix}"
        path.write_bytes(data)
        try:
            current.validate()
            st.image(preview_frame(str(path), current, S.game), caption="First frame · green line marks the scoring area", use_container_width=True)
        except JudgeError as exc:
            st.error(str(exc))
            return
        with st.expander("View original video"):
            st.video(data)
        if st.button("Analyze video", type="primary"):
            bar = st.progress(0.0, text="Reading video frames…")
            try:
                result = process_game_video(str(path), S.game, current, lambda ratio: bar.progress(ratio, text="Scoring…"))
                S.result = wrapped_result({**result, "demo": use_demo})
                S.analysis_key = fingerprint
            except (JudgeError, RuntimeError) as exc:
                S.result = None
                st.error(str(exc))
            finally:
                bar.empty()
    if S.result:
        if S.result.get("demo"):
            st.info("Demo result: for preview only; it is not added to the tournament scoreboard.")
            score_cards(S.result)
            st.json(S.result, expanded=False)
            st.download_button("Download demo report", json.dumps(S.result, ensure_ascii=False, indent=2), file_name="demo_result.json", mime="application/json")
        else:
            review_result(S.result)


def scoreboard():
    st.title("Every point tells a story.")
    reports = [r for r in S.reports if verify_results_hash(r)]
    if len(reports) != len(S.reports):
        st.error("A report was modified and excluded from the totals.")
    if not reports:
        st.info("No confirmed rounds yet.")
        if st.button("Start the first round"):
            new_round()
        return
    total = {"team_a_score": sum(r["team_a_score"] for r in reports), "team_b_score": sum(r["team_b_score"] for r in reports)}
    score_cards(total)
    winner = "A" if total["team_a_score"] > total["team_b_score"] else "B" if total["team_b_score"] > total["team_a_score"] else None
    st.subheader(f"🏆 {S.teams[winner]} is leading" if winner else "🤝 The teams are tied")
    points = {pid: sum(r["player_points"].get(pid, 0) for r in reports) for pid in S.players}
    observed = {pid: sum(r["observed_seconds"].get(pid, 0) for r in reports) for pid in S.players}
    candidates = [pid for pid in S.players if points[pid] > 0 or observed[pid] > 0]
    best = max(((points[p], round(observed[p], 2)) for p in candidates), default=None)
    mvps = [display_player(p) for p in candidates if (points[p], round(observed[p], 2)) == best]
    if mvps:
        st.success("⭐ MVP: " + " & ".join(mvps))
        st.caption("MVP is based on points, then observed time for the assigned player. Ties share MVP.")
    else:
        st.info("Not enough data to select an MVP.")
    rows = [{"Round": i + 1, "Game": LABELS[r["game_type"]][1], "Team A": r["team_a_score"], "Team B": r["team_b_score"], "Source": "Video" if r["source"] == "video" else "Board", "MVP": r["mvp"] or "—"} for i, r in enumerate(reports)]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.subheader("Individual stats")
    st.dataframe([{"Player": display_player(p), "Team": S.teams["A" if p in ("P1", "P2") else "B"], "Points": points[p], "Observed time (seconds)": round(observed[p], 1)} for p in S.players], hide_index=True, use_container_width=True)
    bundle = sign_results({"schema_version": 1, "teams": S.teams, "players": S.players, "rounds": reports, "totals": total})
    st.download_button("↓ Download all results (JSON)", json.dumps(bundle, ensure_ascii=False, indent=2), file_name="family_game_day_results.json", mime="application/json", use_container_width=True)
    if S.result:
        st.download_button("↓ Download latest round report", json.dumps(S.result, ensure_ascii=False, indent=2), file_name=f"{S.game}_result.json", mime="application/json")
    if st.button("+ Play next round", type="primary", use_container_width=True):
        new_round()


with st.sidebar:
    st.markdown("### 🏟️ Family AI")
    st.caption("GAME DAY / PLAY TOGETHER")
    st.divider()
    for i, label in enumerate(STEPS):
        # Once a round has started, setup is immutable; use a fresh round to change it.
        enabled = i == S.step or (i == 5 and bool(S.reports))
        if st.button(f"{'●' if i == S.step else str(i + 1).zfill(2)}  {label}", key=f"step_{i}",
                     type="primary" if i == S.step else "secondary", disabled=not enabled, use_container_width=True):
            S.step = i
            st.rerun()
    st.divider()
    st.caption(f"{len(S.reports)} rounds scored")
    if S.step > 0:
        st.write(f"{LABELS[S.game][0]} **{LABELS[S.game][1]}**")
    if S.step > 0 and st.button("Choose again / new round", use_container_width=True):
        new_round()
    if st.button("Reset players", disabled=bool(S.reports) or S.step != 0):
        S.players = {f"P{i}": f"Player {i}" for i in range(1, 5)}
        st.rerun()
    with st.expander("Verify JSON report"):
        uploaded_report = st.file_uploader("Report to verify", type="json")
        if uploaded_report:
            try:
                report = json.loads(uploaded_report.getvalue())
                valid = verify_results_hash(report)
                if isinstance(report, dict) and "rounds" in report:
                    valid = valid and isinstance(report["rounds"], list) and all(verify_results_hash(r) for r in report["rounds"])
                if valid:
                    st.success("Content matches SHA-256.")
                else:
                    st.error("Content or SHA-256 is invalid.")
            except (ValueError, TypeError):
                st.error("Could not read JSON.")
        st.caption("Integrity check only; this is not a verified signature.")
    with st.expander("AI status"):
        for name, label in (("hand_landmarker.task", "Hand detection"), ("pose_landmarker_lite.task", "Pose detection")):
            st.write(f"{'✅' if (MODEL_DIR / name).exists() else '○'} {label}")
        st.caption("If a model is missing, run python download_models.py in the project folder.")
    st.caption("The scoreboard is stored in this session. Download the JSON before closing or refreshing.")

if S.step > 0:
    st.markdown(f'<div class="eyebrow">STEP {S.step + 1} / 6 · {html.escape(STEPS[S.step])}</div>', unsafe_allow_html=True)
    st.progress((S.step + 1) / 6)

(choose_game, setup_players, rules, active_round, ai_review, scoreboard)[S.step]()
