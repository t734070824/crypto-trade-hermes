#!/usr/bin/env python3
"""Deterministic hourly Binance USDS-M futures testnet harness for agent cron.

Runs the required testnet preflight and two signed trading cycles once, then emits
compact sanitized JSON for the cron agent to summarize. The cron job stays
agent-type (no_agent=false), but this harness prevents repeated exploratory tool
calls and keeps hourly runs focused. Runtime replay intentionally remains in the
separate daily diagnostics cron.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shlex
import sys
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import binance_usds_futures_trend as trend  # noqa: E402
from scripts.binance_trend_core.brokers import (  # noqa: E402
    BinanceTestnetBroker,
    TestnetRiskLimits,
    resolve_binance_testnet_credentials,
)

BEIJING = timezone(timedelta(hours=8), name="UTC+8")
TESTNET_BASE_URL = "https://testnet.binancefuture.com"
RUNTIME_FILE = Path("state/binance-usds-futures-trend-testnet-runtime.jsonl")
ORDER_JOURNAL_FILE = Path("state/binance-usds-futures-trend-testnet-orders.jsonl")
POST_SUBMISSION_POSTFLIGHT_ATTEMPTS = 3
POST_SUBMISSION_POSTFLIGHT_DELAY_SECONDS = 5
SENSITIVE_KEYS = r"signature|apiSecret|api_secret|secret|LALA_KEY|LALA_SECRET"
SENSITIVE_PARAM_RE = re.compile(rf"(?i)({SENSITIVE_KEYS})\s*=\s*[^&\s,;]+")
SENSITIVE_QUOTED_RE = re.compile(rf"(?i)([\"\'](?:{SENSITIVE_KEYS})[\"\']\s*[:=]\s*)([\"\'][^\"\']*[\"\']|[^,}}\s]+)")

GROUPS = (
    {
        "name": "BTC组",
        "key": "btc",
        "symbols": ["BTCUSDT"],
        "risk_unit": "0.001",
        "max_order_count": "3",
    },
    {
        "name": "Alt组",
        "key": "alt",
        "symbols": ["ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "risk_unit": "0.1",
        "max_order_count": "6",
    },
)


def now_stamps() -> dict[str, str]:
    now_utc = datetime.now(UTC).replace(microsecond=0)
    return {
        "generated_at_utc": now_utc.isoformat(),
        "generated_at_beijing": now_utc.astimezone(BEIJING).isoformat(),
    }


def load_dotenv(path: Path) -> bool:
    if not path.exists():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not _valid_env_key(key):
            continue
        try:
            parsed = shlex.split(value, posix=True)
        except ValueError:
            parsed = [value.strip('"\'')]
        if not os.environ.get(key):
            os.environ[key] = parsed[0] if parsed else ""
    return True


def _valid_env_key(key: str) -> bool:
    return bool(key.replace("_", "A").isalnum() and not key[0].isdigit())


def credential_presence() -> dict[str, str]:
    return {
        "LALA_KEY": "present" if os.environ.get("LALA_KEY") else "missing",
        "LALA_SECRET": "present" if os.environ.get("LALA_SECRET") else "missing",
    }


def signed_preflight(symbols: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        broker = BinanceTestnetBroker(
            credentials=resolve_binance_testnet_credentials(),
            dry_run=False,
            base_url=TESTNET_BASE_URL,
            risk_limits=TestnetRiskLimits(max_order_notional=1000, max_symbol_exposure=2000, max_daily_loss=10, max_order_count=1),
        )
        snapshot = broker.fetch_signed_account_snapshot()
        return {
            "ok": True,
            **now_stamps(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "positions": summarize_positions(snapshot, symbols),
            "open_orders_count": _safe_len(snapshot.get("open_orders")),
            "open_algo_orders_count": _safe_len(snapshot.get("open_algo_orders")),
        }
    except Exception as exc:  # pragma: no cover - exercised in live cron env
        return {
            "ok": False,
            **now_stamps(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": safe_error_message(exc),
            "error_type": exc.__class__.__name__,
        }


def run_cycle(group: dict[str, Any], *, dry_run: bool, no_save_runtime_record: bool) -> dict[str, Any]:
    argv = [
        "--run-testnet-cycle",
        "--base-url",
        TESTNET_BASE_URL,
        "--testnet-base-url",
        TESTNET_BASE_URL,
        "--symbols",
        ",".join(group["symbols"]),
        "--interval",
        "1h",
        "--limit",
        "240",
        "--risk-unit",
        str(group["risk_unit"]),
        "--runtime-record-file",
        str(RUNTIME_FILE),
        "--testnet-sync-account-state",
        "--testnet-track-order-lifecycle",
        "--testnet-max-order-notional",
        "1000",
        "--testnet-max-symbol-exposure",
        "2000",
        "--testnet-max-symbol-exposure-fraction",
        "0.20",
        "--testnet-max-daily-loss",
        "10",
        "--testnet-max-order-count",
        str(group["max_order_count"]),
        "--account-risk-fraction",
        "0.003",
        "--target-leverage",
        "2",
        "--testnet-order-journal-file",
        str(ORDER_JOURNAL_FILE),
    ]
    argv.append("--testnet-dry-run" if dry_run else "--testnet-submit-signed")
    if no_save_runtime_record:
        argv.append("--no-save-runtime-record")

    started = time.monotonic()
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            rc = trend.main(argv)
    except Exception as exc:  # pragma: no cover - normally trend.main handles CLI errors
        return {
            "name": group["name"],
            "symbols": group["symbols"],
            "ok": False,
            **now_stamps(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": safe_error_message(exc),
            "error_type": exc.__class__.__name__,
            "raw_output_excerpt": safe_error_message(stdout.getvalue()[:500]),
        }
    elapsed = round(time.monotonic() - started, 3)
    text = stdout.getvalue()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "name": group["name"],
            "symbols": group["symbols"],
            "ok": False,
            **now_stamps(),
            "duration_seconds": elapsed,
            "error": "cycle_output_json_parse_failed",
            "raw_output_excerpt": safe_error_message(text[:500]),
        }
    return summarize_cycle_payload(group, rc, payload, elapsed)


def summarize_cycle_payload(group: dict[str, Any], rc: int, payload: dict[str, Any], elapsed: float) -> dict[str, Any]:
    cycle = payload.get("testnet_cycle", {}) if isinstance(payload, dict) else {}
    runtime_events = cycle.get("runtime_record", {}).get("execution_events", {}) if isinstance(cycle, dict) else {}
    fills = _first_list(cycle.get("fills"), cycle.get("simulated_fills"), runtime_events.get("simulated_fills")) if isinstance(cycle, dict) else []
    desired_orders = _first_list(cycle.get("desired_orders"), runtime_events.get("desired_orders")) if isinstance(cycle, dict) else []
    sync = cycle.get("testnet_account_sync", {}) if isinstance(cycle, dict) else {}
    after = sync.get("after", {}) if isinstance(sync, dict) else {}
    lifecycle = cycle.get("testnet_order_lifecycle") if isinstance(cycle, dict) else None
    lifecycle_summary = _summarize_lifecycle(lifecycle, runtime_events.get("testnet_order_lifecycle"))
    statuses: dict[str, int] = {}
    signed_count = 0
    real_submitted_count = 0
    attempted_real_order_count = 0
    for fill in fills:
        if not isinstance(fill, dict):
            continue
        status = str(fill.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        signed_count += int(bool(fill.get("signed")))
        real_submitted_count += int(bool(fill.get("real_order_submitted")))
        attempted_real_order_count += int(bool(fill.get("real_order_submitted") or fill.get("attempted_real_order_submitted") or status in {"submitted", "submitted_confirmed", "submitted_unknown"}))
    change = cycle.get("runtime_record_change", {}) if isinstance(cycle, dict) else {}
    execution_sync = runtime_events.get("testnet_account_sync", {}) if isinstance(runtime_events, dict) else {}
    return {
        "name": group["name"],
        "symbols": group["symbols"],
        "ok": bool(payload.get("ok")) and rc == 0,
        **{k: cycle.get(k) for k in ("generated_at_utc", "generated_at_beijing") if isinstance(cycle, dict) and k in cycle},
        "duration_seconds": elapsed,
        "errors_count": cycle.get("errors_count") if isinstance(cycle, dict) else None,
        "desired_orders_count": len(desired_orders),
        "fills_count": len(fills),
        "fill_status_counts": statuses,
        "signed_count": signed_count,
        "real_submitted_count": real_submitted_count,
        "attempted_real_order_count": attempted_real_order_count,
        "lifecycle": lifecycle_summary,
        "lifecycle_count": lifecycle_summary.get("tracked_order_count", 0),
        "nonzero_positions_after": summarize_positions(after, group["symbols"]),
        "protection": {
            "all_positions_protected": execution_sync.get("all_positions_protected"),
            "unprotected_symbols": execution_sync.get("unprotected_symbols", []),
            "after_open_orders_count": execution_sync.get("after_open_orders_count"),
        },
        "runtime_record": {
            "file": str(RUNTIME_FILE),
            "saved": bool(cycle.get("runtime_record_saved")) if isinstance(cycle, dict) else False,
            "records_written": change.get("records_written") if isinstance(change, dict) else None,
        },
        "error_types": summarize_errors(cycle.get("errors", [])) if isinstance(cycle, dict) else [],
    }


def _first_list(*values: Any) -> list[Any]:
    for value in values:
        if isinstance(value, list):
            return value
    return []


def _summarize_lifecycle(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return {
                "tracked_order_count": int(value.get("tracked_order_count") or 0),
                "filled_order_count": int(value.get("filled_order_count") or 0),
                "net_pnl": value.get("net_pnl", 0),
            }
        if isinstance(value, list):
            return {
                "tracked_order_count": len(value),
                "filled_order_count": sum(1 for item in value if isinstance(item, dict) and item.get("lifecycle_state") == "filled"),
                "net_pnl": round(sum(float(item.get("fills_summary", {}).get("net_pnl", 0.0)) for item in value if isinstance(item, dict)), 8),
            }
    return {"tracked_order_count": 0, "filled_order_count": 0, "net_pnl": 0}


def summarize_errors(errors: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    if not isinstance(errors, list):
        return result
    for item in errors:
        if not isinstance(item, dict):
            result.append({"error": safe_error_message(item)})
            continue
        summarized: dict[str, str] = {}
        if item.get("type"):
            summarized["type"] = str(item.get("type"))
        if item.get("error"):
            summarized["error"] = safe_error_message(item.get("error"))
        if summarized:
            result.append(summarized)
    return result


def safe_error_message(error: Any) -> str:
    sanitized = str(trend.sanitize_error_message(error))
    sanitized = SENSITIVE_PARAM_RE.sub("<redacted-sensitive-param>", sanitized)
    return SENSITIVE_QUOTED_RE.sub(lambda match: f"{match.group(1)}'<redacted>'", sanitized)


def postflight_account(symbols: list[str]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        broker = BinanceTestnetBroker(credentials=resolve_binance_testnet_credentials(), dry_run=False, base_url=TESTNET_BASE_URL)
        snapshot = broker.fetch_signed_account_snapshot()
        return {
            "ok": True,
            **now_stamps(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "nonzero_positions": summarize_positions(snapshot, symbols),
            "open_orders_count": _safe_len(snapshot.get("open_orders")),
            "open_algo_orders_count": _safe_len(snapshot.get("open_algo_orders")),
        }
    except Exception as exc:  # pragma: no cover - exercised in live cron env
        return {
            "ok": False,
            **now_stamps(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "error": safe_error_message(exc),
            "error_type": exc.__class__.__name__,
        }


def stabilized_postflight_account(symbols: list[str], *, require_stabilization: bool) -> tuple[dict[str, Any], int, float]:
    started = time.monotonic()
    attempts = POST_SUBMISSION_POSTFLIGHT_ATTEMPTS if require_stabilization else 1
    latest: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            time.sleep(POST_SUBMISSION_POSTFLIGHT_DELAY_SECONDS)
        latest = postflight_account(symbols)
    return latest, attempts, round(time.monotonic() - started, 3)


def summarize_positions(snapshot: dict[str, Any], symbols: list[str]) -> list[dict[str, Any]]:
    wanted = set(symbols)
    rows = snapshot.get("positions", []) if isinstance(snapshot, dict) else []
    result: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol not in wanted:
            continue
        try:
            amt = float(row.get("positionAmt") or row.get("position_amt") or row.get("size") or 0.0)
        except (TypeError, ValueError):
            continue
        if abs(amt) < 1e-12:
            continue
        item: dict[str, Any] = {"symbol": symbol, "positionAmt": round(amt, 8)}
        for src, dst in (("entryPrice", "entryPrice"), ("unRealizedProfit", "unRealizedProfit")):
            try:
                if row.get(src) not in (None, ""):
                    item[dst] = round(float(row[src]), 8)
            except (TypeError, ValueError):
                pass
        result.append(item)
    return result


def _safe_len(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def build_summary(payload: dict[str, Any]) -> str:
    lines = [
        "Binance USDS-M testnet hourly harness complete",
        f"UTC: {payload.get('generated_at_utc')}",
        f"北京时间（UTC+8）: {payload.get('generated_at_beijing')}",
        f"ok={payload.get('ok')} dry_run={payload.get('dry_run')} total_duration_seconds={payload.get('duration_seconds')}",
        f"credentials: LALA_KEY={payload.get('credential_presence', {}).get('LALA_KEY')} LALA_SECRET={payload.get('credential_presence', {}).get('LALA_SECRET')}",
        f"preflight_ok={payload.get('preflight', {}).get('ok')} postflight_ok={payload.get('postflight', {}).get('ok')} postflight_attempts={payload.get('postflight_attempts')} postflight_stabilization_seconds={payload.get('postflight_stabilization_seconds')}",
    ]
    for cycle in payload.get("cycles", []):
        lifecycle = cycle.get("lifecycle", {}) if isinstance(cycle.get("lifecycle"), dict) else {}
        protection = cycle.get("protection", {}) if isinstance(cycle.get("protection"), dict) else {}
        lines.append(
            f"{cycle.get('name')}: ok={cycle.get('ok')} symbols={','.join(cycle.get('symbols', []))} "
            f"desired={cycle.get('desired_orders_count')} fills={cycle.get('fills_count')} "
            f"signed={cycle.get('signed_count')} attempted={cycle.get('attempted_real_order_count')} real_submitted={cycle.get('real_submitted_count')} "
            f"statuses={cycle.get('fill_status_counts')} lifecycle_tracked={lifecycle.get('tracked_order_count')} lifecycle_filled={lifecycle.get('filled_order_count')} "
            f"all_positions_protected={protection.get('all_positions_protected')} unprotected={protection.get('unprotected_symbols')} "
            f"duration={cycle.get('duration_seconds')}s"
        )
    lines.append(f"runtime_record={RUNTIME_FILE}")
    lines.append(f"order_journal={ORDER_JOURNAL_FILE}")
    lines.append("hourly_replay=skipped; replay diagnostics are handled by replay-diagnostics-daily")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run compact hourly signed testnet harness for cron")
    parser.add_argument("--dry-run", action="store_true", help="Do not submit signed orders; still exercises testnet code path")
    parser.add_argument("--no-save-runtime-record", action="store_true", help="Do not append runtime evidence; intended for local tests only")
    parser.add_argument("--skip-dotenv", action="store_true", help="Do not source profile .env")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    os.chdir(REPO_ROOT)
    dotenv_loaded = False if args.skip_dotenv else load_dotenv(REPO_ROOT / ".env")
    all_symbols = [symbol for group in GROUPS for symbol in group["symbols"]]
    started = time.monotonic()
    payload: dict[str, Any] = {
        "ok": False,
        **now_stamps(),
        "mode": "testnet_hourly_harness",
        "dry_run": bool(args.dry_run),
        "testnet_base_url": TESTNET_BASE_URL,
        "dotenv_loaded": dotenv_loaded,
        "credential_presence": credential_presence(),
        "runtime_record_file": str(RUNTIME_FILE),
        "order_journal_file": str(ORDER_JOURNAL_FILE),
        "hourly_replay": "skipped_daily_replay_cron_owns_runtime_evolution",
        "risk_limits": {
            "max_order_notional": 1000,
            "max_symbol_exposure": 2000,
            "max_symbol_exposure_fraction": 0.20,
            "max_daily_loss": 10,
            "account_risk_fraction": 0.003,
            "target_leverage": 2,
        },
        "cycles": [],
    }
    preflight = signed_preflight(all_symbols)
    payload["preflight"] = preflight
    if not preflight.get("ok"):
        payload["duration_seconds"] = round(time.monotonic() - started, 3)
        payload["summary_zh"] = "testnet signed preflight failed; stopped before cycles"
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    cycle_ok = True
    require_postflight_stabilization = False
    for group in GROUPS:
        cycle = run_cycle(group, dry_run=args.dry_run, no_save_runtime_record=args.no_save_runtime_record)
        payload["cycles"].append(cycle)
        cycle_ok = cycle_ok and bool(cycle.get("ok"))
        require_postflight_stabilization = require_postflight_stabilization or bool(cycle.get("real_submitted_count") or cycle.get("attempted_real_order_count"))

    postflight, postflight_attempts, stabilization_seconds = stabilized_postflight_account(
        all_symbols,
        require_stabilization=bool(require_postflight_stabilization and not args.dry_run),
    )
    payload["postflight"] = postflight
    payload["postflight_attempts"] = postflight_attempts
    payload["postflight_stabilization_seconds"] = stabilization_seconds
    payload["duration_seconds"] = round(time.monotonic() - started, 3)
    payload["ok"] = bool(preflight.get("ok")) and cycle_ok and bool(payload["postflight"].get("ok"))
    payload["summary_zh"] = build_summary(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
