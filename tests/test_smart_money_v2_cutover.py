"""Static offline safety guards for the VPS paper-pilot cutover scripts.

The actual VPS stop/start must only run with user authorization and remote
access; these tests do NOT stop tmux sessions or make network requests.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops"


class CutoverSafetyTests(unittest.TestCase):
    def test_v1_cannot_be_overwritten_by_v2_switch(self):
        s = (OPS / "sml-v2-cutover.sh").read_text()
        self.assertIn('tmux send-keys -t yatl-sml-paper:0.0 C-c', s)
        self.assertLess(s.index('tmux send-keys -t yatl-sml-paper:0.0 C-c'),
                        s.index('tar -czf "$archive"'))
        self.assertLess(s.index('tar -czf "$archive"'),
                        s.index('tmux new-session -d -s yatl-sml-v2'))
        self.assertIn("sha256sum", s)
        self.assertIn('[[ ! -f "$NEW/data/smart_money/state.json" ]]', s)
        self.assertIn('cp -n "$OLD/data/smart_money/screened.json"', s)
        for dangerous in ("rm -rf", "kill -9", "sudo ", "git reset --hard"):
            self.assertNotIn(dangerous, s)

    def test_v2_preserves_original_request_budget_and_hidden_key(self):
        s = (OPS / "run-smart-money-v2.sh").read_text()
        self.assertIn("read -rsp", s)
        self.assertIn('export YATL_SML_HELIUS_BUDGET_FILE="$BUDGET"', s)
        self.assertIn('OLD="/home/ubuntu/yatl-smart-money"', s)
        self.assertIn('arguments+=(--resume)', s)
        self.assertIn('observe --exploratory', s)
        self.assertIn('--poll-seconds 180', s)
        self.assertNotIn("private_key", s)
        self.assertNotIn("sendTransaction", s)

    def test_dashboard_switch_changes_only_publisher_source(self):
        s = (OPS / "sml-v2-switch-dashboard.sh").read_text()
        self.assertIn("V2 paper report is recent", s)
        self.assertIn('tmux kill-session -t yatl-sml-hostinger', s)
        self.assertIn('YATL_REPORT_DIR=', s)
        self.assertIn('bash ops/publish-sml-hostinger.sh --init', s)
        self.assertNotIn('tmux kill-session -t yatl-sml-v2', s)
        self.assertNotIn('tmux kill-session -t yatl-sml-paper', s)
        publisher = (OPS / "publish-sml-hostinger.sh").read_text()
        self.assertIn('YATL_REPORT_DIR="${YATL_REPORT_DIR:-', publisher)


if __name__ == "__main__":
    unittest.main()
