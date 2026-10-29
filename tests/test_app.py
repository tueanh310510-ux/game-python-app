from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from streamlit.testing.v1 import AppTest
from ai_judge import verify_results_hash

APP = Path(__file__).resolve().parents[1] / "app.py"


def click_label(app, label):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception, list(app.exception)


class AppFlowTests(unittest.TestCase):
    def start_game(self, game):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertFalse(app.exception)
        app.button(key=f"pick_{game}").click().run()
        click_label(app, "Lưu đội & tiếp tục →")
        click_label(app, "Sẵn sàng vào sân →")
        return app

    def test_play_confirm_download_and_persist_next_round(self):
        app = self.start_game("tic_tac_toe")
        click_label(app, "▶ Bắt đầu vòng")
        for cell in (0, 3, 1, 4, 2):
            app.button(key=f"cell_{cell}").click().run()
            self.assertFalse(app.exception)
        self.assertEqual(app.session_state["step"], 4)
        self.assertEqual(app.session_state["result"]["team_a_score"], 1)
        click_label(app, "Xác nhận & ghi vào bảng điểm →")
        self.assertEqual(app.session_state["step"], 5)
        self.assertEqual(len(app.session_state["reports"]), 1)
        self.assertTrue(verify_results_hash(app.session_state["reports"][0]))
        app.run()
        self.assertEqual(len(app.session_state["reports"]), 1)
        click_label(app, "+ Chơi vòng tiếp theo")
        self.assertEqual(app.session_state["board"], [""] * 9)
        self.assertEqual(len(app.session_state["reports"]), 1)
        app.button(key="pick_basketball").click().run()
        click_label(app, "Giữ đội & tiếp tục →")
        self.assertEqual(app.session_state["config"]["points"], 2)

    def test_all_video_games_reach_upload_without_errors(self):
        for game in ("football", "basketball", "rock_paper_scissors", "red_light_green_light"):
            with self.subTest(game=game):
                app = self.start_game(game)
                click_label(app, "Tôi đã có video →")
                self.assertEqual(app.session_state["step"], 4)
                self.assertFalse(app.exception)

    def test_duplicate_names_block_progress(self):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        app.button(key="pick_football").click().run()
        next(field for field in app.text_input if field.label == "Tên P2").set_value("Người chơi 1")
        click_label(app, "Lưu đội & tiếp tục →")
        self.assertEqual(app.session_state["step"], 1)
        self.assertTrue(app.error)


if __name__ == "__main__":
    unittest.main()
