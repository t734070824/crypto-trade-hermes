import json
import pathlib
import re
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestnetAgentHourlyCronConfigTests(unittest.TestCase):
    def _testnet_agent_prompt(self) -> str:
        data = json.loads((REPO_ROOT / "cron" / "jobs.json").read_text(encoding="utf-8"))
        matches = [job for job in data["jobs"] if job["name"] == "testnet-agent-hourly"]
        self.assertEqual(len(matches), 1)
        return matches[0]["prompt"]

    def test_hourly_testnet_agent_uses_account_proportional_exposure_not_micro_probe_cap(self):
        prompt = self._testnet_agent_prompt()

        self.assertNotIn("max_symbol_exposure=70", prompt)
        self.assertNotRegex(prompt, r"--testnet-max-symbol-exposure\s+70\b")
        self.assertIn("--testnet-max-symbol-exposure-fraction", prompt)

        self.assertEqual(
            re.findall(r"--testnet-max-order-notional\s+(\d+(?:\.\d+)?)", prompt),
            ["1000", "1000"],
        )
        self.assertEqual(
            re.findall(r"--testnet-max-symbol-exposure\s+(\d+(?:\.\d+)?)", prompt),
            ["2000", "2000"],
        )
        self.assertEqual(
            re.findall(r"--testnet-max-symbol-exposure-fraction\s+(\d+(?:\.\d+)?)", prompt),
            ["0.20", "0.20"],
        )


if __name__ == "__main__":
    unittest.main()
