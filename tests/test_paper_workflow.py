import contextlib
import io
import json
import unittest
from unittest.mock import patch

from yatl.__main__ import main
from yatl.paper_workflow import PaperWorkflowError, load_and_validate, validate_paper_workflow


def fixture():
    return {
        "schema_version": 1,
        "mode": "PAPER_ONLY",
        "live_master_lock": "OFF",
        "exchange_order_submission": False,
        "policy": {
            "market": "SPOT", "direction": "LONG_ONLY",
            "primary_analysis_timeframe": "1h", "higher_timeframe_regime": "4h",
            "entry_context_timeframe": "15m", "execution_timeframe": "NOT_ENABLED",
        },
        "workflows": [
            {"workflow_id": "btc", "symbol": "BTCUSDT", "entry": "60000",
             "stop": "59400", "target": "61200", "position_size": "0.08",
             "account_equity": "10000", "risk_percent": "0.5", "max_loss": "48.00",
             "potential_reward": "96.00", "risk_reward_ratio": "2",
             "status": "MANUAL_PAPER_FIXTURE", "notes": "fixture"},
            {"workflow_id": "eth", "symbol": "ETHUSDT", "entry": "3000",
             "stop": "2940", "target": "3120", "position_size": "0.8",
             "account_equity": "10000", "risk_percent": "0.5", "max_loss": "48.0",
             "potential_reward": "96.0", "risk_reward_ratio": "2",
             "status": "MANUAL_PAPER_FIXTURE", "notes": "fixture"},
        ],
    }


class PaperWorkflowTests(unittest.TestCase):
    def test_valid_fixture_has_required_fields_and_results(self):
        result = validate_paper_workflow(fixture())
        self.assertEqual([item["symbol"] for item in result], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(result[0]["max_loss"], "48.00")
        self.assertEqual(result[1]["risk_reward_ratio"], "2")

    def test_policy_fails_closed(self):
        changes = [
            ("mode", "LIVE"), ("live_master_lock", "ON"),
            ("exchange_order_submission", True),
        ]
        for field, value in changes:
            data = fixture()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(PaperWorkflowError):
                validate_paper_workflow(data)
        for field, value in (("market", "FUTURES"), ("direction", "SHORT"),
                             ("execution_timeframe", "5m"),
                             ("primary_analysis_timeframe", "5m")):
            data = fixture()
            data["policy"][field] = value
            with self.subTest(field=field), self.assertRaises(PaperWorkflowError):
                validate_paper_workflow(data)

    def test_schema_symbols_and_types_fail_closed(self):
        variants = []
        data = fixture(); data["unknown"] = True; variants.append(data)
        data = fixture(); data["workflows"][0]["unknown"] = "x"; variants.append(data)
        data = fixture(); data["workflows"][1]["symbol"] = "BTCUSDT"; variants.append(data)
        data = fixture(); data["workflows"][0]["symbol"] = "XRPUSDT"; variants.append(data)
        data = fixture(); data["workflows"][0]["entry"] = 60000; variants.append(data)
        for data in variants:
            with self.subTest(), self.assertRaises(PaperWorkflowError):
                validate_paper_workflow(data)

    def test_price_order_risk_arithmetic_and_leverage_fail_closed(self):
        variants = []
        for field, value in (("stop", "60000"), ("target", "59999"),
                             ("risk_percent", "1.1"), ("max_loss", "47"),
                             ("potential_reward", "95"), ("risk_reward_ratio", "1.9"),
                             ("position_size", "1"), ("entry", "NaN")):
            data = fixture()
            data["workflows"][0][field] = value
            variants.append(data)
        for data in variants:
            with self.subTest(), self.assertRaises(PaperWorkflowError):
                validate_paper_workflow(data)

    def test_file_loading_size_json_and_io_fail_closed(self):
        with patch("yatl.paper_workflow.Path.open", return_value=io.BytesIO(json.dumps(fixture()).encode())):
            self.assertEqual(len(load_and_validate()), 2)
        for stream in (io.BytesIO(b"{"), io.BytesIO(b"x" * 65_537)):
            with patch("yatl.paper_workflow.Path.open", return_value=stream):
                with self.assertRaises(PaperWorkflowError):
                    load_and_validate()
        with patch("yatl.paper_workflow.Path.open", side_effect=OSError("private path")):
            with self.assertRaisesRegex(PaperWorkflowError, "Cannot read"):
                load_and_validate()

    @patch("yatl.__main__.load_and_validate")
    @patch("sys.argv", ["yatl", "paper-check"])
    def test_cli_validates_locally_and_reports_no_submission(self, load):
        load.return_value = [{"symbol": "BTCUSDT", "entry": "1", "stop": "0.9",
                              "target": "1.2", "position_size": "1", "max_loss": "0.1",
                              "risk_reward_ratio": "2"}]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(), 0)
        self.assertIn("No exchange order submitted", output.getvalue())
        load.assert_called_once_with("fixtures/p0-paper-workflows.json")


if __name__ == "__main__":
    unittest.main()
