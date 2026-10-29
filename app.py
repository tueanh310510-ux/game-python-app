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
    "football": ("⚽", "Football", "Bóng đá", "Sút bóng qua vạch cầu môn. Mỗi cú sút là một cơ hội."),
    "tic_tac_toe": ("✕", "Tic Tac Toe", "Cờ caro 3 × 3", "Luân phiên X và O. Ba ô thẳng hàng để chiến thắng."),
    "rock_paper_scissors": ("✌️", "Rock Paper Scissors", "Kéo · Búa · Bao", "Cùng ra tay. AI đọc cử chỉ và phân xử từng lượt."),
    "red_light_green_light": ("🚦", "Red Light Green Light", "Đèn đỏ · Đèn xanh", "Di chuyển khi đèn xanh. Giữ nguyên tư thế khi đèn đỏ."),
    "basketball": ("🏀", "Basketball", "Bóng rổ", "Nhắm chuẩn, ném bóng. Ghi điểm khi bóng đi qua vành rổ."),
}
STEPS = ("Chọn trò chơi", "Người chơi & đội", "Luật & thiết lập", "Vào sân", "Trọng tài AI", "Bảng kết quả")

TRANSLATIONS = {
    "Sân chơi của cả nhà": "Family game day", "Cùng chơi hết mình.": "Play your best.",
    "Để AI giữ điểm.": "Let AI keep score.", "Hôm nay, mình chơi gì?": "What shall we play today?",
    "Chọn trò chơi →": "Choose this game →", "Chia đội, gọi đồng đội.": "Meet your teammates.",
    "Giữ đội & tiếp tục →": "Keep teams & continue →", "Lưu đội & tiếp tục →": "Save teams & continue →",
    "Luật rõ ràng. Chơi thật vui.": "Clear rules. Great games.", "Sẵn sàng vào sân →": "Ready to play →",
    "Đến lượt cả nhà tỏa sáng.": "Let the games begin.", "▶ Bắt đầu vòng": "▶ Start round",
    "Kết thúc vòng →": "End round →", "Tôi đã có video →": "I already have a video →",
    "Căn vùng chấm điểm": "Calibrate scoring area", "Kết quả vòng này": "Round results",
    "Các sự kiện được chấm": "Scored events", "Xác nhận & ghi vào bảng điểm →": "Confirm & add to scoreboard →",
    "Trọng tài đã sẵn sàng.": "The referee is ready.", "Phân tích video": "Analyze video",
    "Đang đọc khung hình…": "Reading video frames…", "Đang chấm điểm…": "Scoring…",
    "Tải clip mẫu": "Download sample clip", "Xem video gốc": "View original video",
    "Mỗi điểm số, một khoảnh khắc.": "Every point tells a story.", "Bắt đầu vòng đầu tiên": "Start the first round",
    "Chọn lại / vòng mới": "Choose again / new round", "Tải lại đội ban đầu": "Reset players",
    "Kiểm tra báo cáo JSON": "Verify JSON report", "Báo cáo cần kiểm tra": "Report to verify",
    "Trạng thái AI": "AI status", "Nhận diện bàn tay": "Hand detection", "Nhận diện tư thế": "Pose detection",
    "Bảng kết quả": "Scoreboard", "Người chơi & đội": "Players & teams", "Luật & thiết lập": "Rules & setup",
    "Vào sân": "Game time", "Trọng tài AI": "AI referee", "Chọn trò chơi": "Choose a game",
    "Bóng đá": "Football", "Cờ caro 3 × 3": "Tic-tac-toe 3 × 3", "Kéo · Búa · Bao": "Rock · Paper · Scissors",
    "Đèn đỏ · Đèn xanh": "Red Light · Green Light", "Bóng rổ": "Basketball", "Cam": "Orange", "Vàng": "Yellow",
    "Xanh lá": "Green", "Trắng": "White", "Chơi vòng tiếp theo": "Play next round", "CÙNG NHAU VỀ ĐÍCH": "PLAY TOGETHER",
}

def _translate(value):
    if st.session_state.get("language", "English") != "English" or not isinstance(value, str):
        return value
    for source, target in sorted(TRANSLATIONS.items(), key=lambda item: -len(item[0])):
        value = value.replace(source, target)
    return value

def _localize_streamlit():
    for name in ("title", "header", "subheader", "caption", "write", "info", "warning", "error", "success", "button", "text_input", "number_input", "selectbox", "radio", "download_button", "form_submit_button", "markdown"):
        original = getattr(st, name)
        if getattr(original, "_family_localized", False):
            continue
        def localized(*args, _original=original, **kwargs):
            args = tuple(_translate(arg) for arg in args)
            if "label" in kwargs:
                kwargs["label"] = _translate(kwargs["label"])
            return _original(*args, **kwargs)
        localized._family_localized = True
        setattr(st, name, localized)


st.set_page_config(page_title="Family AI · Game Day", page_icon="🏟️", layout="wide")
if "language" not in st.session_state:
    st.session_state["language"] = "Tiếng Việt"
_localize_streamlit()

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
        "players": {"P1": "Người chơi 1", "P2": "Người chơi 2", "P3": "Người chơi 3", "P4": "Người chơi 4"},
        "teams": {"A": "Đội Lá Xanh", "B": "Đội Nắng Vàng"}, "reports": [],
        "round_id": uuid.uuid4().hex, "board": [""] * 9, "started_at": None,
        "result": None, "analysis_key": None, "saved": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize()
S = st.session_state
S.language = st.sidebar.selectbox("Language / Ngôn ngữ", ("English", "Tiếng Việt"), index=0 if S.language == "English" else 1)


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
    st.markdown('<div class="eyebrow">Sân chơi của cả nhà</div>', unsafe_allow_html=True)
    st.markdown('''<div class="hero"><div class="eyebrow">FAMILY AI / GAME DAY</div>
    <h1>Cùng chơi hết mình.<br>Để AI giữ điểm.</h1>
    <p>Năm thử thách, hai đội, một ngày vui. Chọn sân chơi đầu tiên và tạo khoảnh khắc của cả nhà.</p>
    <span class="chip">5 trò chơi</span><span class="chip">4 người chơi</span><span class="chip">Trọng tài video</span></div>''', unsafe_allow_html=True)
    st.subheader("Hôm nay, mình chơi gì?")
    for group in (GAMES[:3], GAMES[3:]):
        columns = st.columns(len(group))
        for column, game in zip(columns, group):
            emoji, name, subtitle, description = LABELS[game]
            with column, st.container(border=True):
                st.markdown(f'<div class="game-icon">{emoji}</div>', unsafe_allow_html=True)
                st.subheader(name)
                st.caption(subtitle)
                st.write(description)
                if st.button("Chọn trò chơi →", key=f"pick_{game}", use_container_width=True):
                    S.game = game
                    S.config = asdict(replace(cfg(), points=2 if game == "basketball" else 1))
                    go(1)
    st.caption("AI xử lý video trên máy chạy ứng dụng. Hãy xem lại sự kiện trước khi ghi điểm vào giải.")


def setup_players():
    st.title("Chia đội, gọi đồng đội.")
    st.write("Mỗi đội có hai thành viên. Chọn người đại diện ở bước tiếp theo; đổi người qua từng vòng.")
    if S.reports:
        st.info("Giữ nguyên danh sách người chơi trong giải để tổng điểm và MVP nhất quán.")
        for team, ids in (("A", ("P1", "P2")), ("B", ("P3", "P4"))):
            st.write(f"**{S.teams[team]}** · " + " · ".join(display_player(p) for p in ids))
        if st.button("Giữ đội & tiếp tục →", type="primary"):
            go(2)
        return
    with st.form("players_form"):
        cols = st.columns(2)
        names, teams = {}, {}
        for column, team, players in zip(cols, ("A", "B"), (("P1", "P2"), ("P3", "P4"))):
            with column:
                st.subheader(f"Đội {team}")
                teams[team] = st.text_input(f"Tên đội {team}", value=S.teams[team], max_chars=40).strip()
                for pid in players:
                    names[pid] = st.text_input(f"Tên {pid}", value=S.players[pid], max_chars=40).strip()
        if st.form_submit_button("Lưu đội & tiếp tục →", type="primary"):
            if not all(names.values()) or not all(teams.values()):
                st.error("Điền đủ tên của bốn người chơi và hai đội.")
            elif len({v.casefold() for v in names.values()}) != 4 or teams["A"].casefold() == teams["B"].casefold():
                st.error("Tên người chơi và tên hai đội cần phân biệt để đọc bảng điểm.")
            else:
                S.players, S.teams = names, teams
                go(2)


def rules():
    st.title("Luật rõ ràng. Chơi thật vui.")
    descriptions = {
        "football": "Thi sút luân phiên: một người trong mỗi clip. Bóng vượt vạch theo đúng hướng nhận điểm. Camera cố định, dùng bóng màu nổi bật và tránh các vật cùng màu.",
        "basketball": "Thi ném luân phiên: một người trong mỗi clip. Bóng đi xuống qua đoạn vành rổ đã chọn nhận điểm cố định. Quay ngang sao cho nhìn rõ bóng trước và sau vành.",
        "tic_tac_toe": "Đội A dùng X, đội B dùng O. X đi trước. Luân phiên chọn ô trống; hàng ngang, dọc hoặc chéo gồm ba ô thắng ván. Có thể chơi trên màn hình hoặc tải video bàn cờ.",
        "rock_paper_scissors": "Người đội A đưa một tay ở nửa trái ảnh, đội B ở nửa phải. Giữ cử chỉ ít nhất 0,55 giây. Sau mỗi lượt, cả hai rút tay khỏi ảnh ít nhất 0,4 giây. Búa thắng kéo; kéo thắng bao; bao thắng búa.",
        "red_light_green_light": "Mỗi người đứng trong một nửa ảnh, nhìn rõ toàn thân. Đèn xanh được di chuyển. Sau thời gian phản ứng khi đèn đỏ bật, phải đứng yên; mỗi pha đỏ hoàn chỉnh hợp lệ nhận điểm. Di chuyển mất điểm của pha đó.",
    }
    st.info(descriptions[S.game])
    current = cfg()
    player_labels = {pid: display_player(pid) for pid in S.players}
    team_labels = dict(S.teams)
    with st.form("rules_form"):
        left, right = st.columns(2)
        with left:
            duration = st.number_input("Thời gian vòng (giây)", min_value=10, max_value=600, value=int(current.duration), step=10)
            player_a = st.selectbox("Đại diện đội A / phía trái / X", ("P1", "P2"), format_func=player_labels.__getitem__,
                                    index=("P1", "P2").index(current.player_a))
        with right:
            points = st.number_input("Điểm mỗi lần thắng / ghi bàn", min_value=1, max_value=10, value=current.points)
            player_b = st.selectbox("Đại diện đội B / phía phải / O", ("P3", "P4"), format_func=player_labels.__getitem__,
                                    index=("P3", "P4").index(current.player_b))
        active_team, color = current.active_team, current.ball_color
        green, red, grace = current.green_seconds, current.red_seconds, current.grace_seconds
        if S.game in ("football", "basketball"):
            active_team = st.radio("Đội thực hiện clip này", ("A", "B"), format_func=team_labels.__getitem__, horizontal=True)
            color = st.selectbox("Màu bóng", ("orange", "yellow", "green", "white"),
                                 format_func=lambda c: {"orange": "Cam", "yellow": "Vàng", "green": "Xanh lá", "white": "Trắng"}[c])
            st.caption("Chấm từng clip rồi tạo vòng mới để đội còn lại thi. Danh tính người sút/ném do bạn gán.")
        if S.game == "red_light_green_light":
            a, b, c = st.columns(3)
            green = a.number_input("Đèn xanh (giây)", 1.0, 15.0, current.green_seconds, 0.5)
            red = b.number_input("Đèn đỏ (giây)", 1.0, 15.0, current.red_seconds, 0.5)
            grace = c.number_input("Thời gian phản ứng (giây)", 0.0, 0.9, current.grace_seconds, 0.1)
            st.caption("Video phải bắt đầu đúng lúc bấm Bắt đầu. Nếu quay sớm, nhập độ lệch ở bước chấm video.")
        st.write("**Nếu hòa:** giữ kết quả hòa; tạo vòng phụ nếu muốn phân thắng bại.")
        st.caption("MVP xét điểm trước, sau đó thời gian quan sát; đồng hạng được ghi nhận cùng nhau.")
        if st.form_submit_button("Sẵn sàng vào sân →", type="primary"):
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
                                                 "Vòng dừng trước khi có hàng thắng: hòa 0–0.", board=S.board))
    go(4)


@st.fragment(run_every=0.25)
def round_clock():
    elapsed = 0.0 if S.started_at is None else time.monotonic() - S.started_at
    remaining = max(0, math.ceil(cfg().duration - elapsed))
    st.markdown(f'<div class="timer">{remaining // 60:02d}:{remaining % 60:02d}</div>', unsafe_allow_html=True)
    st.progress(min(elapsed / cfg().duration, 1.0))
    if S.game == "red_light_green_light":
        color, _, age = light_state(elapsed, cfg())
        label = "ĐÈN XANH · DI CHUYỂN" if color == "green" else "ĐÈN ĐỎ · ĐỨNG YÊN"
        if S.started_at is None:
            label = "SẴN SÀNG · CHỜ BẮT ĐẦU"
        st.markdown(f'<div class="signal {color}">{label}</div>', unsafe_allow_html=True)
        if color == "red" and age < cfg().grace_seconds:
            st.caption("Đang trong thời gian phản ứng.")
    if S.started_at is not None and remaining == 0:
        finish_round()


def active_round():
    st.title("Đến lượt cả nhà tỏa sáng.")
    st.write(f"**{S.teams['A']}** · {display_player(cfg().player_a)}　 vs　 **{S.teams['B']}** · {display_player(cfg().player_b)}")
    round_clock()
    if S.started_at is None:
        if st.button("▶ Bắt đầu vòng", type="primary", use_container_width=True):
            S.started_at = time.monotonic()
            st.rerun()
    if S.game == "tic_tac_toe":
        current = "X" if S.board.count("X") == S.board.count("O") else "O"
        pid = cfg().player_a if current == "X" else cfg().player_b
        st.subheader(f"Lượt {current} · {display_player(pid)}")
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
        st.info("Quay video bằng điện thoại hoặc webcam của bạn, rồi tải clip ở bước Trọng tài AI. Giữ camera cố định suốt vòng.")
        if S.game == "red_light_green_light":
            st.caption("Cho người chơi thấy đèn trên màn hình. Bắt đầu video cùng lúc với đồng hồ; không tạm dừng giữa clip.")
    left, right = st.columns(2)
    if left.button("Kết thúc vòng →", disabled=S.started_at is None, use_container_width=True):
        finish_round()
    if right.button("Tôi đã có video →", use_container_width=True):
        go(4)


def calibration(current):
    with st.expander("Căn vùng chấm điểm", expanded=S.game in ("football", "basketball", "tic_tac_toe")):
        st.caption("Tọa độ tính theo tỷ lệ ảnh: 0 là mép trái/trên, 1 là mép phải/dưới. Xem vạch xanh trên khung hình để căn chỉnh.")
        if S.game == "football":
            x = st.slider("Vị trí vạch cầu môn (X)", 0.05, 0.95, current.goal_x, 0.01)
            low, high = st.slider("Hai đầu cầu môn (Y)", 0.0, 1.0, (current.goal_y_min, current.goal_y_max), 0.01)
            direction = st.selectbox("Hướng bóng đi vào cầu môn", ("right", "left"),
                                     format_func=lambda d: "Từ trái sang phải →" if d == "right" else "← Từ phải sang trái")
            current = replace(current, goal_x=x, goal_y_min=low, goal_y_max=high, goal_direction=direction)
        elif S.game == "basketball":
            y = st.slider("Độ cao vành rổ (Y)", 0.05, 0.95, current.hoop_y, 0.01)
            low, high = st.slider("Hai mép vành rổ (X)", 0.0, 1.0, (current.hoop_x_min, current.hoop_x_max), 0.01)
            current = replace(current, hoop_y=y, hoop_x_min=low, hoop_x_max=high)
        elif S.game == "tic_tac_toe":
            st.caption("Bàn cờ nền trắng, nét đen, quay thẳng từ trên xuống. Căn vùng vừa sát mép ngoài bàn 3 × 3.")
            x1, x2 = st.slider("Mép trái/phải bàn cờ", 0.0, 1.0, (0.1, 0.9), 0.01)
            y1, y2 = st.slider("Mép trên/dưới bàn cờ", 0.0, 1.0, (0.1, 0.9), 0.01)
            current = replace(current, board_roi=(x1, y1, x2 - x1, y2 - y1))
        elif S.game == "red_light_green_light":
            offset = st.number_input("Video bắt đầu ở giây thứ mấy của đồng hồ?", 0.0, 600.0, current.video_offset, 0.1)
            threshold = st.slider("Ngưỡng chuyển động (tỷ lệ chiều ảnh)", 0.005, 0.15, current.motion_threshold, 0.005)
            current = replace(current, video_offset=offset, motion_threshold=threshold)
        else:
            st.write("Đội A ở nửa trái ảnh, đội B ở nửa phải. Mỗi người chỉ đưa một tay vào ảnh.")
    return current


def score_cards(result):
    left, center, right = st.columns((2, 1, 2))
    for col, team, score in ((left, "A", result["team_a_score"]), (right, "B", result["team_b_score"])):
        col.markdown(f'<div class="team">{html.escape(result.get("teams", S.teams)[team])}</div><div class="score">{score}</div>', unsafe_allow_html=True)
    center.markdown('<div class="score" style="color:#9eac9e">:</div>', unsafe_allow_html=True)


def review_result(result):
    st.subheader("Kết quả vòng này")
    score_cards(result)
    st.write(result["details"])
    for warning in result.get("warnings", []):
        st.warning(warning)
    if result.get("source") == "video":
        st.caption(f"Đã phân tích {result['frames_analyzed']} khung hình / {result['duration_seconds']} giây. Các sự kiện thị giác là ước lượng cần xem lại.")
    if result["events"]:
        with st.expander("Các sự kiện được chấm", expanded=True):
            st.dataframe(result["events"], hide_index=True, use_container_width=True)
    if verify_results_hash(result):
        st.success("Mã SHA-256 khớp với nội dung báo cáo.")
    else:
        st.error("Báo cáo không vượt qua kiểm tra toàn vẹn.")
        return
    st.caption("SHA-256 phát hiện thay đổi so với mã đã lưu; không xác thực danh tính người tạo hoặc độ chính xác của AI.")
    if st.button("Xác nhận & ghi vào bảng điểm →", type="primary", disabled=S.saved):
        # The same bytes cannot be scored a second time in this tournament,
        # even if the user changes a setting or starts a new round.
        source_digest = result.get("video_sha256")
        duplicate = any(r["round_id"] == result["round_id"] or (source_digest and source_digest == r.get("video_sha256")) for r in S.reports)
        if duplicate:
            st.error("Vòng hoặc video này đã được tính điểm. Hãy sử dụng clip mới cho vòng tiếp theo.")
        else:
            S.reports = [*S.reports, result]
            S.saved = True
            go(5)


def ai_review():
    st.title("Trọng tài đã sẵn sàng.")
    if S.result and S.result["source"] == "interactive":
        review_result(S.result)
        return
    st.write("Tải video, kiểm tra vùng chấm và xem lại các sự kiện trước khi lưu điểm.")
    current = calibration(cfg())
    file = st.file_uploader("Video vòng thi · tối đa 150 MB", type=("mp4", "mov", "avi", "mkv", "webm"), key=f"video_{S.round_id}")
    sample_paths = {"football": ROOT / "samples/football_demo.mp4", "basketball": ROOT / "samples/basketball_demo.mp4", "tic_tac_toe": ROOT / "samples/tic_tac_toe_demo.mp4"}
    sample = sample_paths.get(S.game)
    use_demo = False
    if sample and sample.exists():
        use_demo = st.checkbox("Dùng video mô phỏng để thử quy trình", key=f"demo_{S.round_id}")
        if use_demo:
            st.info("Clip hình học mô phỏng để kiểm tra bộ đếm. Đây không phải trận đấu thật.")
            st.download_button("Tải clip mẫu", sample.read_bytes(), file_name=sample.name, mime="video/mp4")
    if file is None and not use_demo:
        st.caption("Bóng đá/bóng rổ: mỗi clip chỉ dành cho một người. Kéo búa bao/đèn đỏ đèn xanh: hai đại diện ở hai nửa ảnh.")
        return
    data = sample.read_bytes() if use_demo else file.getvalue()
    if len(data) > 150 * 1024 * 1024:
        st.error("Video vượt giới hạn 150 MB.")
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
            st.image(preview_frame(str(path), current, S.game), caption="Khung đầu tiên · vạch xanh là vùng chấm điểm", use_container_width=True)
        except JudgeError as exc:
            st.error(str(exc))
            return
        with st.expander("Xem video gốc"):
            st.video(data)
        if st.button("Phân tích video", type="primary"):
            bar = st.progress(0.0, text="Đang đọc khung hình…")
            try:
                result = process_game_video(str(path), S.game, current, lambda ratio: bar.progress(ratio, text="Đang chấm điểm…"))
                S.result = wrapped_result({**result, "demo": use_demo})
                S.analysis_key = fingerprint
            except (JudgeError, RuntimeError) as exc:
                S.result = None
                st.error(str(exc))
            finally:
                bar.empty()
    if S.result:
        if S.result.get("demo"):
            st.info("Kết quả mô phỏng: có thể xem thử, nhưng không cộng vào bảng điểm giải.")
            score_cards(S.result)
            st.json(S.result, expanded=False)
            st.download_button("Tải báo cáo mô phỏng", json.dumps(S.result, ensure_ascii=False, indent=2), file_name="demo_result.json", mime="application/json")
        else:
            review_result(S.result)


def scoreboard():
    st.title("Mỗi điểm số, một khoảnh khắc.")
    reports = [r for r in S.reports if verify_results_hash(r)]
    if len(reports) != len(S.reports):
        st.error("Một báo cáo đã thay đổi. Báo cáo đó được loại khỏi tổng điểm.")
    if not reports:
        st.info("Chưa có vòng thi được xác nhận.")
        if st.button("Bắt đầu vòng đầu tiên"):
            new_round()
        return
    total = {"team_a_score": sum(r["team_a_score"] for r in reports), "team_b_score": sum(r["team_b_score"] for r in reports)}
    score_cards(total)
    winner = "A" if total["team_a_score"] > total["team_b_score"] else "B" if total["team_b_score"] > total["team_a_score"] else None
    st.subheader(f"🏆 {S.teams[winner]} đang dẫn đầu" if winner else "🤝 Hai đội đang hòa điểm")
    points = {pid: sum(r["player_points"].get(pid, 0) for r in reports) for pid in S.players}
    observed = {pid: sum(r["observed_seconds"].get(pid, 0) for r in reports) for pid in S.players}
    candidates = [pid for pid in S.players if points[pid] > 0 or observed[pid] > 0]
    best = max(((points[p], round(observed[p], 2)) for p in candidates), default=None)
    mvps = [display_player(p) for p in candidates if (points[p], round(observed[p], 2)) == best]
    if mvps:
        st.success("⭐ MVP: " + " & ".join(mvps))
        st.caption("Ưu tiên điểm, sau đó thời gian quan sát đối tượng của người chơi đã gán. Cùng chỉ số được đồng MVP.")
    else:
        st.info("Chưa đủ dữ liệu để chọn MVP.")
    rows = [{"Vòng": i + 1, "Trò chơi": LABELS[r["game_type"]][1], "Đội A": r["team_a_score"], "Đội B": r["team_b_score"], "Nguồn": "Video" if r["source"] == "video" else "Bàn cờ", "MVP": r["mvp"] or "—"} for i, r in enumerate(reports)]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    st.subheader("Thành tích từng người")
    st.dataframe([{"Người chơi": display_player(p), "Đội": S.teams["A" if p in ("P1", "P2") else "B"], "Điểm": points[p], "Thời gian quan sát (giây)": round(observed[p], 1)} for p in S.players], hide_index=True, use_container_width=True)
    bundle = sign_results({"schema_version": 1, "teams": S.teams, "players": S.players, "rounds": reports, "totals": total})
    st.download_button("↓ Tải toàn bộ kết quả JSON", json.dumps(bundle, ensure_ascii=False, indent=2), file_name="family_game_day_results.json", mime="application/json", use_container_width=True)
    if S.result:
        st.download_button("↓ Tải báo cáo vòng gần nhất", json.dumps(S.result, ensure_ascii=False, indent=2), file_name=f"{S.game}_result.json", mime="application/json")
    if st.button("+ Chơi vòng tiếp theo", type="primary", use_container_width=True):
        new_round()


with st.sidebar:
    st.markdown("### 🏟️ Family AI")
    st.caption("GAME DAY / CÙNG NHAU VỀ ĐÍCH")
    st.divider()
    for i, label in enumerate(STEPS):
        # Once a round has started, setup is immutable; use a fresh round to change it.
        enabled = i == S.step or (i == 5 and bool(S.reports))
        if st.button(f"{'●' if i == S.step else str(i + 1).zfill(2)}  {label}", key=f"step_{i}",
                     type="primary" if i == S.step else "secondary", disabled=not enabled, use_container_width=True):
            S.step = i
            st.rerun()
    st.divider()
    st.caption(f"{len(S.reports)} vòng đã ghi điểm")
    if S.step > 0:
        st.write(f"{LABELS[S.game][0]} **{LABELS[S.game][1]}**")
    if S.step > 0 and st.button("Chọn lại / vòng mới", use_container_width=True):
        new_round()
    if st.button("Tải lại đội ban đầu", disabled=bool(S.reports) or S.step != 0):
        S.players = {f"P{i}": f"Người chơi {i}" for i in range(1, 5)}
        st.rerun()
    with st.expander("Kiểm tra báo cáo JSON"):
        uploaded_report = st.file_uploader("Báo cáo cần kiểm tra", type="json")
        if uploaded_report:
            try:
                report = json.loads(uploaded_report.getvalue())
                valid = verify_results_hash(report)
                if isinstance(report, dict) and "rounds" in report:
                    valid = valid and isinstance(report["rounds"], list) and all(verify_results_hash(r) for r in report["rounds"])
                if valid:
                    st.success("Nội dung khớp mã SHA-256.")
                else:
                    st.error("Nội dung hoặc mã SHA-256 không hợp lệ.")
            except (ValueError, TypeError):
                st.error("Không đọc được JSON.")
        st.caption("Kiểm tra toàn vẹn, không phải chữ ký xác thực.")
    with st.expander("Trạng thái AI"):
        for name, label in (("hand_landmarker.task", "Nhận diện bàn tay"), ("pose_landmarker_lite.task", "Nhận diện tư thế")):
            st.write(f"{'✅' if (MODEL_DIR / name).exists() else '○'} {label}")
        st.caption("Nếu thiếu model, chạy python download_models.py trong thư mục dự án.")
    st.caption("Bảng điểm giữ trong phiên trình duyệt. Tải JSON trước khi đóng hoặc tải lại trang.")

if S.step > 0:
    st.markdown(f'<div class="eyebrow">BƯỚC {S.step + 1} / 6 · {html.escape(STEPS[S.step])}</div>', unsafe_allow_html=True)
    st.progress((S.step + 1) / 6)

(choose_game, setup_players, rules, active_round, ai_review, scoreboard)[S.step]()
