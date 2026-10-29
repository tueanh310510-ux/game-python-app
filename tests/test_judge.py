from dataclasses import replace
import itertools
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ai_judge import (JudgeConfig, JudgeError, LineCrossing, RPSRounds, RedLightJudge,
                      board_outcome, classify_hand, judge_board, light_state,
                      play_move, process_game_video, rps_winner, sign_results, verify_results_hash)


class RulesTests(unittest.TestCase):
    def test_hash_unicode_roundtrip_and_nested_tampering(self):
        result = sign_results({"team": "Đội Nắng", "events": [{"points": 2}]})
        self.assertTrue(verify_results_hash(json.loads(json.dumps(result))))
        result["events"][0]["points"] = 99
        self.assertFalse(verify_results_hash(result))
        for invalid in (None, [], {}, {"hash": "🟢" * 64}, {"hash": "f" * 64, "score": float("nan")}):
            self.assertFalse(verify_results_hash(invalid))

    def test_signature_detaches_nested_data(self):
        original = {"a": [1]}
        signed = sign_results(original)
        original["a"].append(2)
        self.assertTrue(verify_results_hash(signed))
        self.assertEqual(signed["a"], [1])

    def test_every_tic_tac_toe_state_against_reachable_game_tree(self):
        reachable = set()
        lines = ((0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6))
        def visit(board, turn):
            if board in reachable:
                return
            reachable.add(board)
            if any(board[a] and board[a] == board[b] == board[c] for a,b,c in lines):
                return
            for i, value in enumerate(board):
                if not value:
                    visit(board[:i] + (turn,) + board[i+1:], "O" if turn == "X" else "X")
        visit(("",) * 9, "X")
        self.assertEqual(len(reachable), 5478)
        for board in itertools.product(("", "X", "O"), repeat=9):
            try:
                board_outcome(list(board))
                valid = True
            except JudgeError:
                valid = False
            self.assertEqual(valid, board in reachable, board)

    def test_moves_winner_and_draw(self):
        board = [""] * 9
        for cell in (0, 3, 1, 4, 2):
            board = play_move(board, cell)
        result = judge_board(board, JudgeConfig(points=3, player_a="P2"))
        self.assertEqual((result["team_a_score"], result["mvp"]), (3, "P2"))
        with self.assertRaises(JudgeError):
            play_move(board, 8)
        draw = judge_board(list("XOXXOOOXX"))
        self.assertEqual(draw["winner"], "draw")
        self.assertIsNone(draw["mvp"])

    def test_rps_all_nine_pairs(self):
        for a, b in itertools.product(("rock", "paper", "scissors"), repeat=2):
            winner = rps_winner(a, b)
            if a == b:
                self.assertIsNone(winner)
            else:
                self.assertNotEqual(winner, rps_winner(b, a))
        with self.assertRaises(JudgeError):
            rps_winner("bad", "rock")

    def test_rps_requires_stability_and_two_missing_hands_to_rearm(self):
        rounds = RPSRounds()
        self.assertIsNone(rounds.update("rock", "scissors", 0))
        self.assertEqual(rounds.update("rock", "scissors", .6)["winner"], "A")
        self.assertIsNone(rounds.update("rock", "paper", 1))
        self.assertIsNone(rounds.update("rock", "paper", 2))
        rounds.update(None, "paper", 3)
        rounds.update(None, "paper", 4)
        self.assertIsNone(rounds.update("paper", "rock", 5))
        rounds.update(None, None, 6)
        rounds.update(None, None, 6.5)
        rounds.update("paper", "rock", 7)
        self.assertEqual(rounds.update("paper", "rock", 7.6)["winner"], "A")

    def test_landmark_gestures(self):
        for extended, gesture in (((0,0,0,0), "rock"), ((1,1,1,1), "paper"), ((1,1,0,0), "scissors"), ((1,0,0,0), None)):
            hand = [SimpleNamespace(x=0, y=0, z=0) for _ in range(21)]
            for active, (tip, pip) in zip(extended, ((8,6), (12,10), (16,14), (20,18))):
                hand[pip].y = 1
                hand[tip].y = 1.5 if active else .8
            self.assertEqual(classify_hand(hand), gesture)

    def test_directed_crossing_gaps_cooldown_and_interpolation(self):
        line = LineCrossing(0, .5, .3, .7, 1, 1.5)
        self.assertFalse(line.update((.4, .5), 0))
        self.assertTrue(line.update((.55, .5), .1))
        self.assertFalse(line.update((.4, .5), .2))
        self.assertFalse(line.update((.55, .5), .3))
        line.update(None, 2)
        self.assertFalse(line.update((.6, .5), 2.1))
        line.update((.4, .5), 3)
        self.assertFalse(line.update((.6, .5), 4))  # gap cannot count
        line.update((.4, .5), 5)
        self.assertTrue(line.update((.6, .5), 5.1))
        line = LineCrossing(0, .5, .3, .7, 1, 1)
        line.update((.4, .2), 0)
        self.assertFalse(line.update((.51, .3), .1))  # crossing just outside mouth
        reverse = LineCrossing(0, .5, .3, .7, -1, 1)
        reverse.update((.6, .5), 0)
        self.assertTrue(reverse.update((.4, .5), .1))

    def test_red_light_full_observed_phase_only_and_slow_drift(self):
        cfg = JudgeConfig(green_seconds=2, red_seconds=2, grace_seconds=.2, motion_threshold=.03)
        judge = RedLightJudge(cfg)
        for i in range(40):
            t = i / 10
            # A drifts slowly: consecutive deltas are small, cumulative isn't.
            judge.update({"A": {11: (.2 + max(0, t - 2.2) * .04, .5)}, "B": {11: (.8, .5)}}, t)
        self.assertEqual(judge.events(3.8), [])
        events = judge.events(4)
        self.assertEqual([(e["team"], e["kind"], e["points"]) for e in events], [("A", "red_movement", 0), ("B", "red_survived", 1)])
        empty = RedLightJudge(cfg)
        for i in range(41):
            empty.update({}, i / 10)
        self.assertEqual(empty.events(4), [])
        self.assertEqual(light_state(2, cfg)[0], "red")
        self.assertEqual(light_state(4, cfg)[0], "green")

    def test_invalid_configuration(self):
        for config in (JudgeConfig(duration=0), JudgeConfig(points=-1), JudgeConfig(goal_y_min=.8, goal_y_max=.2),
                       JudgeConfig(motion_threshold=float("nan")), JudgeConfig(board_roi=(.8,.8,.5,.5)),
                       JudgeConfig(player_a="P1", player_b="P1")):
            with self.assertRaises(JudgeError):
                config.validate()


class VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import cv2
        import numpy as np
        from generate_samples import generate
        cls.cv2, cls.np = cv2, np
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        generate(cls.folder)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_synthetic_videos_known_scores_and_valid_hashes(self):
        for game, points, expected in (("football", 1, 2), ("basketball", 2, 4), ("tic_tac_toe", 1, 1)):
            with self.subTest(game=game):
                progress = []
                result = process_game_video(str(self.folder / f"{game}_demo.mp4"), game, JudgeConfig(points=points), progress.append)
                self.assertEqual(result["team_a_score"], expected)
                self.assertEqual(result["team_b_score"], 0)
                self.assertTrue(verify_results_hash(result))
                self.assertEqual(progress[-1], 1)
                self.assertEqual(result["duration_seconds"], 6)

    def test_assign_clip_to_team_b_and_limit_duration(self):
        result = process_game_video(str(self.folder / "football_demo.mp4"), "football", JudgeConfig(active_team="B", active_player="P4", duration=3))
        self.assertEqual(result["team_b_score"], 1)
        self.assertEqual(result["team_a_score"], 0)
        self.assertEqual(result["mvp"], "P4")
        self.assertEqual(result["duration_seconds"], 3)
        self.assertTrue(result["warnings"])

    def test_invalid_video_never_returns_fake_scores(self):
        bad = self.folder / "bad.mp4"
        bad.write_bytes(b"not a video")
        with self.assertRaises(JudgeError):
            process_game_video(str(bad), "football")
        blank = self.folder / "blank.avi"
        writer = self.cv2.VideoWriter(str(blank), self.cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240))
        for _ in range(20):
            writer.write(self.np.zeros((240, 320, 3), self.np.uint8))
        writer.release()
        with self.assertRaisesRegex(JudgeError, "Không nhận diện"):
            process_game_video(str(blank), "football")


if __name__ == "__main__":
    unittest.main()
