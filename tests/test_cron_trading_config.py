import json
import pathlib
import unittest
from unittest import mock

from scripts import binance_usds_futures_testnet_hourly as hourly


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestnetAgentHourlyCronConfigTests(unittest.TestCase):
    def _testnet_agent_job(self) -> dict:
        data = json.loads((REPO_ROOT / "cron" / "jobs.json").read_text(encoding="utf-8"))
        matches = [job for job in data["jobs"] if job["name"] == "testnet-agent-hourly"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_hourly_testnet_agent_is_script_owned_no_agent_job(self):
        job = self._testnet_agent_job()

        self.assertIs(job["no_agent"], True)
        self.assertEqual(job["script"], "binance_usds_futures_testnet_hourly.sh")
        self.assertEqual(job["schedule"]["display"], "5 * * * *")
        self.assertEqual(job["schedule"]["expr"], "5 * * * *")

    def test_hourly_testnet_script_uses_account_proportional_exposure_not_micro_probe_cap(self):
        captured_argv = []

        def fake_trend_main(argv):
            captured_argv.append(list(argv))
            payload = {
                "ok": True,
                "testnet_cycle": {
                    "generated_at_utc": "2026-06-17T00:00:00+00:00",
                    "generated_at_beijing": "2026-06-17T08:00:00+08:00",
                    "desired_orders": [],
                    "simulated_fills": [],
                    "runtime_record_saved": False,
                    "runtime_record_change": {"records_written": 0},
                    "runtime_record": {"execution_events": {"testnet_account_sync": {}}},
                    "testnet_account_sync": {"after": {"positions": [], "open_orders": [], "open_algo_orders": []}},
                    "errors": [],
                },
            }
            print(json.dumps(payload))
            return 0

        with mock.patch.object(hourly.trend, "main", fake_trend_main):
            for group in hourly.GROUPS:
                hourly.run_cycle(group, dry_run=True, no_save_runtime_record=True)

        self.assertEqual(len(captured_argv), 2)
        for argv in captured_argv:
            joined = " ".join(argv)
            self.assertNotIn("max_symbol_exposure=70", joined)
            self.assertNotIn("--testnet-max-symbol-exposure 70", joined)
            self.assertIn("--testnet-max-symbol-exposure-fraction", argv)
            self.assertEqual(argv[argv.index("--testnet-max-order-notional") + 1], "1000")
            self.assertEqual(argv[argv.index("--testnet-max-symbol-exposure") + 1], "2000")
            self.assertEqual(argv[argv.index("--testnet-max-symbol-exposure-fraction") + 1], "0.20")


if __name__ == "__main__":
    unittest.main()
