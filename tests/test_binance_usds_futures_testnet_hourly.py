import json
import os
from unittest import mock

from scripts import binance_usds_futures_testnet_hourly as hourly


class FakeBroker:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def fetch_signed_account_snapshot(self):
        return {
            "positions": [
                {"symbol": "BTCUSDT", "positionAmt": "0.01", "entryPrice": "100000", "unRealizedProfit": "1.23"},
                {"symbol": "ETHUSDT", "positionAmt": "0"},
            ],
            "open_orders": [{"symbol": "BTCUSDT"}],
            "open_algo_orders": [{"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"}],
        }


def fake_trend_main(argv):
    symbols = argv[argv.index("--symbols") + 1].split(",")
    max_count = argv[argv.index("--testnet-max-order-count") + 1]
    payload = {
        "ok": True,
        "testnet_cycle": {
            "generated_at_utc": "2026-06-16T00:00:00+00:00",
            "generated_at_beijing": "2026-06-16T08:00:00+08:00",
            "errors_count": 0,
            "desired_orders": [{"symbol": symbols[0]}],
            "fills": [
                {"status": "submitted", "signed": True, "real_order_submitted": True},
                {"status": "rejected", "signed": False, "real_order_submitted": False},
            ],
            "testnet_order_lifecycle": [{"symbol": symbols[0]}],
            "runtime_record_saved": "--no-save-runtime-record" not in argv,
            "runtime_record_change": {"records_written": 1},
            "runtime_record": {
                "execution_events": {
                    "testnet_account_sync": {
                        "all_positions_protected": True,
                        "unprotected_symbols": [],
                        "after_open_orders_count": int(max_count),
                    }
                }
            },
            "testnet_account_sync": {
                "after": {
                    "positions": [{"symbol": symbols[0], "positionAmt": "0.01", "entryPrice": "100.0"}],
                    "open_orders": [],
                    "open_algo_orders": [],
                }
            },
            "errors": [],
        },
    }
    print(json.dumps(payload))
    return 0


def test_hourly_harness_emits_compact_safe_json_and_skips_replay(capsys, monkeypatch):
    monkeypatch.setenv("LALA_KEY", "dummy-key")
    monkeypatch.setenv("LALA_SECRET", "dummy-secret")
    monkeypatch.chdir(hourly.REPO_ROOT)

    captured_argv = []

    def recording_main(argv):
        captured_argv.append(list(argv))
        return fake_trend_main(argv)

    with mock.patch.object(hourly, "BinanceTestnetBroker", FakeBroker), mock.patch.object(hourly, "resolve_binance_testnet_credentials", lambda: object()), mock.patch.object(hourly.trend, "main", recording_main):
        rc = hourly.main(["--skip-dotenv", "--no-save-runtime-record"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["mode"] == "testnet_hourly_harness"
    assert payload["credential_presence"] == {"LALA_KEY": "present", "LALA_SECRET": "present"}
    assert payload["hourly_replay"] == "skipped_daily_replay_cron_owns_runtime_evolution"
    assert payload["preflight"]["ok"] is True
    assert payload["postflight"]["open_algo_orders_count"] == 2
    assert [cycle["name"] for cycle in payload["cycles"]] == ["BTC组", "Alt组"]
    assert payload["cycles"][0]["symbols"] == ["BTCUSDT"]
    assert payload["cycles"][1]["symbols"] == ["ETHUSDT", "SOLUSDT", "BNBUSDT"]
    assert payload["cycles"][0]["fill_status_counts"] == {"rejected": 1, "submitted": 1}
    assert payload["cycles"][0]["real_submitted_count"] == 1
    assert "hourly_replay=skipped" in payload["summary_zh"]
    encoded = json.dumps(payload)
    assert "dummy-key" not in encoded
    assert "dummy-secret" not in encoded

    assert len(captured_argv) == 2
    assert captured_argv[0][captured_argv[0].index("--symbols") + 1] == "BTCUSDT"
    assert captured_argv[1][captured_argv[1].index("--symbols") + 1] == "ETHUSDT,SOLUSDT,BNBUSDT"
    for argv in captured_argv:
        assert "--replay-runtime-evidence" not in argv
        assert "--base-url" in argv
        assert argv[argv.index("--base-url") + 1] == hourly.TESTNET_BASE_URL
        assert "--testnet-base-url" in argv
        assert argv[argv.index("--testnet-base-url") + 1] == hourly.TESTNET_BASE_URL
        assert "--testnet-submit-signed" in argv
        assert "--testnet-sync-account-state" in argv
        assert "--testnet-track-order-lifecycle" in argv
        assert "--interval" in argv
        assert argv[argv.index("--interval") + 1] == "1h"


def test_btc_group_order_budget_covers_atomic_entry_protection_group():
    btc_group = next(group for group in hourly.GROUPS if group["key"] == "btc")

    atomic_entry_protection_order_count = 4  # entry + stop loss + two take-profit tranches

    assert int(btc_group["max_order_count"]) >= atomic_entry_protection_order_count


def test_hourly_harness_stops_before_cycles_when_preflight_fails(capsys, monkeypatch):
    monkeypatch.delenv("LALA_KEY", raising=False)
    monkeypatch.delenv("LALA_SECRET", raising=False)

    with mock.patch.object(hourly, "signed_preflight", return_value={"ok": False, "error_type": "RuntimeError", "error": "boom"}), mock.patch.object(hourly.trend, "main") as trend_main:
        rc = hourly.main(["--skip-dotenv"])

    assert rc == 1
    trend_main.assert_not_called()
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["cycles"] == []
    assert payload["summary_zh"] == "testnet signed preflight failed; stopped before cycles"


def test_load_dotenv_supports_export_and_overrides_blank_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("export LALA_KEY=from-file\nLALA_SECRET='quoted-secret'\n", encoding="utf-8")
    monkeypatch.setenv("LALA_KEY", "")
    monkeypatch.delenv("LALA_SECRET", raising=False)

    assert hourly.load_dotenv(env_file) is True
    assert os.environ["LALA_KEY"] == "from-file"
    assert os.environ["LALA_SECRET"] == "quoted-secret"


def test_summarize_errors_is_sanitized():
    errors = [
        {"type": "RuntimeError", "error": "signature=abc123&timestamp=999"},
        "raw apiSecret=xyz",
        {"error": "{'apiSecret': 'xyz', 'signature': 'abc'}"},
        {"error": '{"api_secret":"xyz","signature":"abc"}'},
    ]
    summarized = hourly.summarize_errors(errors)
    encoded = json.dumps(summarized)
    assert summarized[0]["type"] == "RuntimeError"
    assert "abc123" not in encoded
    assert "xyz" not in encoded


def test_dry_run_wrapper_points_to_harness_and_forces_dry_run():
    text = (hourly.REPO_ROOT / "scripts/binance_usds_futures_testnet_dry_run.sh").read_text(encoding="utf-8")
    assert "python3 scripts/binance_usds_futures_testnet_hourly.py --dry-run" in text


def test_run_cycle_counts_testnet_simulated_fills_from_runtime_events(capsys):
    payload = {
        "ok": True,
        "testnet_cycle": {
            "generated_at_utc": "2026-06-16T00:00:00+00:00",
            "generated_at_beijing": "2026-06-16T08:00:00+08:00",
            "desired_orders": [{"symbol": "BTCUSDT"}, {"symbol": "BTCUSDT"}],
            "simulated_fills": [
                {"status": "submitted", "signed": True, "real_order_submitted": True},
                {"status": "submitted_unknown", "signed": True, "attempted_real_order_submitted": True},
            ],
            "runtime_record_saved": True,
            "runtime_record_change": {"records_written": 1},
            "runtime_record": {
                "execution_events": {
                    "testnet_account_sync": {"all_positions_protected": False, "unprotected_symbols": ["BTCUSDT"]},
                    "testnet_order_lifecycle": {"tracked_order_count": 1, "filled_order_count": 1, "net_pnl": 0.12},
                }
            },
            "testnet_account_sync": {"after": {"positions": [], "open_orders": [], "open_algo_orders": []}},
            "errors": [],
        },
    }

    with mock.patch.object(hourly.trend, "main", side_effect=lambda argv: print(json.dumps(payload)) or 0):
        cycle = hourly.run_cycle(hourly.GROUPS[0], dry_run=False, no_save_runtime_record=False)

    assert cycle["ok"] is True
    assert cycle["fills_count"] == 2
    assert cycle["fill_status_counts"] == {"submitted": 1, "submitted_unknown": 1}
    assert cycle["signed_count"] == 2
    assert cycle["real_submitted_count"] == 1
    assert cycle["attempted_real_order_count"] == 2
    assert cycle["lifecycle"]["tracked_order_count"] == 1
    assert cycle["lifecycle"]["filled_order_count"] == 1


def test_hourly_harness_waits_for_postflight_after_real_submissions(capsys, monkeypatch):
    monkeypatch.setenv("LALA_KEY", "dummy-key")
    monkeypatch.setenv("LALA_SECRET", "dummy-secret")
    postflight_calls = []

    def fake_postflight(symbols):
        postflight_calls.append(list(symbols))
        return {"ok": True, "open_algo_orders_count": len(postflight_calls), "nonzero_positions": []}

    with (
        mock.patch.object(hourly, "signed_preflight", return_value={"ok": True}),
        mock.patch.object(hourly, "run_cycle", side_effect=[
            {"name": "BTC组", "ok": True, "real_submitted_count": 0, "attempted_real_order_count": 0},
            {"name": "Alt组", "ok": True, "real_submitted_count": 2, "attempted_real_order_count": 2},
        ]),
        mock.patch.object(hourly, "postflight_account", side_effect=fake_postflight),
        mock.patch.object(hourly.time, "sleep") as sleep_mock,
    ):
        rc = hourly.main(["--skip-dotenv"])

    assert rc == 0
    assert len(postflight_calls) == 3
    assert sleep_mock.call_count == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["postflight_attempts"] == 3
    assert payload["postflight_stabilization_seconds"] >= 0
    assert "Alt组" in payload["summary_zh"]
    assert "attempted=2" in payload["summary_zh"]


def test_run_cycle_propagates_exception_as_sanitized_error(monkeypatch):
    monkeypatch.setenv("LALA_KEY", "dummy-key")
    monkeypatch.setenv("LALA_SECRET", "dummy-secret")

    with mock.patch.object(hourly.trend, "main", side_effect=RuntimeError("signature=abc123 leaked")):
        cycle = hourly.run_cycle(hourly.GROUPS[0], dry_run=True, no_save_runtime_record=True)

    assert cycle["ok"] is False
    assert cycle["error_type"] == "RuntimeError"
    assert "signature=" not in cycle["error"]
    assert "leaked" in cycle["error"]
