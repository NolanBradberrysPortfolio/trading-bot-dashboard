import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = Path(__file__).resolve().parent
PUBLIC_DATA_PATH = DASHBOARD_ROOT / "public" / "data" / "dashboard-data.json"
POLY_MULTI_STATE = ROOT / "paper_trading_multi_state.json"
POLY_MULTI_CONFIG = ROOT / "paper_trading_multi_config.json"
POLY_SINGLE_STATE = ROOT / "paper_trading_state.json"
QUANT_ROOT = ROOT.parent / "there-s-an-openclaw-instance-called" / "quant_strategy_screen"
QUANT_FORWARD = QUANT_ROOT / "forward_test"
QUANT_ACCOUNT = QUANT_FORWARD / "local_paper_account.json"
QUANT_WATCHLIST = QUANT_ROOT / "output" / "paper_watchlist.json"
QUANT_MARKS = QUANT_FORWARD / "daily_marks.csv"
QUANT_ORDERS = QUANT_FORWARD / "orders.csv"


def utc_now():
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def read_json(path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_csv_rows(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def money(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def classify_strategy(name, strategy_config):
    if name.startswith("edge_"):
        return "Validated Polymarket edge"
    if name == "long_hold_forecaster_tracking":
        return "Forecaster tracking"
    if name == "negative_risk_no_bundle_arb":
        return "Negative-risk arbitrage"
    if name.startswith("favorite"):
        return "Polymarket favorites"
    if strategy_config.get("strategy_type") == "validated_edge":
        return "Validated Polymarket edge"
    return "Polymarket paper"


def describe_strategy(name, strategy_config):
    if strategy_config.get("strategy_type") == "validated_edge":
        days = round((strategy_config["min_days_to_close"] + strategy_config["max_days_to_close"]) / 2)
        return (
            f"{days}d {strategy_config['side_rule']} rule, category={strategy_config['category_filter']}, "
            f"price {strategy_config['price_min']:.2f}-{strategy_config['price_max']:.2f}, "
            f"rank={strategy_config['rank_rule']}."
        )
    descriptions = {
        "favorite_14d_broad": "Buys the highest-probability side about 14 days before resolution.",
        "favorite_7d_high": "Buys high-probability favorites roughly one week before resolution.",
        "long_hold_forecaster_tracking": "Copies selected long-horizon forecasters on larger active positions.",
        "negative_risk_no_bundle_arb": "Buys bundles of mutually exclusive NO contracts when the book implies positive edge.",
    }
    return descriptions.get(name, "Polymarket paper-trading strategy.")


def safe_question(text, public):
    if not text:
        return ""
    text = str(text)
    if not public:
        return text
    # Keep market text because it is needed for public auditability, but strip obvious wallet/account-like data.
    return text.replace("0x", "wallet:")


def import_poly_helpers():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        import polymarket_multi_paper_trader as trader
        from trading_fee_models import fee_for_trade

        return trader, fee_for_trade
    except Exception:
        return None, None


def mark_positions(positions):
    trader, fee_for_trade = import_poly_helpers()
    if not trader or not fee_for_trade:
        return {}, "mark import failed"

    tokens = []
    for position in positions:
        if position.get("type") == "bundle":
            for leg in position.get("legs", []):
                token = leg.get("no_token_id")
                if token:
                    tokens.append(str(token))
        else:
            token = position.get("token_id")
            if token:
                tokens.append(str(token))
    try:
        bids = trader.batch_prices(tokens, "BUY")
        asks = trader.batch_prices(tokens, "SELL")
    except Exception as exc:
        return {}, f"mark fetch failed: {exc}"

    marks = {}
    for position in positions:
        position_id = position.get("id")
        cost = money(position.get("entry_total_cost", position.get("stake", 0.0)))
        if position.get("type") == "bundle":
            bundles = money(position.get("bundles"))
            bid_value = 0.0
            mid_value = 0.0
            missing = 0
            for leg in position.get("legs", []):
                token = str(leg.get("no_token_id", ""))
                bid = bids.get(token)
                ask = asks.get(token)
                if bid is None or ask is None:
                    missing += 1
                    continue
                bid_value += bundles * bid
                mid_value += bundles * ((bid + ask) / 2)
            marks[position_id] = {
                "bid_value": bid_value,
                "mid_value": mid_value,
                "bid_pnl": bid_value - cost,
                "mid_pnl": mid_value - cost,
                "missing_marks": missing,
            }
            continue

        token = str(position.get("token_id", ""))
        bid = bids.get(token)
        ask = asks.get(token)
        if bid is None or ask is None:
            marks[position_id] = {
                "bid_value": 0.0,
                "mid_value": 0.0,
                "bid_pnl": -cost,
                "mid_pnl": -cost,
                "missing_marks": 1,
            }
            continue
        shares = money(position.get("shares"))
        category = position.get("category", "other")
        venue = position.get("fee_model", "kalshi_general_taker")
        mid = (bid + ask) / 2
        bid_exit_fee = fee_for_trade(bid, shares, category, venue)
        mid_exit_fee = fee_for_trade(mid, shares, category, venue)
        bid_value = shares * bid - bid_exit_fee
        mid_value = shares * mid - mid_exit_fee
        marks[position_id] = {
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "bid_value": bid_value,
            "mid_value": mid_value,
            "bid_pnl": bid_value - cost,
            "mid_pnl": mid_value - cost,
            "missing_marks": 0,
        }
    return marks, "live order-book marks"


def poly_positions_for_export(positions, marks, public):
    exported = []
    for position in positions:
        mark = marks.get(position.get("id"), {})
        exported.append(
            {
                "id": position.get("id") if not public else None,
                "question": safe_question(position.get("question") or position.get("event_title"), public),
                "side": position.get("outcome", "bundle"),
                "type": position.get("type", "single"),
                "opened_at": position.get("opened_at"),
                "end_date": position.get("end_date"),
                "entry_price": money(position.get("entry_ask")),
                "cost": money(position.get("entry_total_cost", position.get("stake", 0.0))),
                "bid_pnl": mark.get("bid_pnl"),
                "mid_pnl": mark.get("mid_pnl"),
                "bid": mark.get("bid"),
                "ask": mark.get("ask"),
                "status": position.get("status", "open"),
            }
        )
    exported.sort(key=lambda row: row.get("bid_pnl") if row.get("bid_pnl") is not None else -10**9, reverse=True)
    return exported


def build_polymarket(public=True):
    state = read_json(POLY_MULTI_STATE, {})
    config = read_json(POLY_MULTI_CONFIG, {})
    ledgers = state.get("ledgers", {})
    strategies_config = config.get("strategies", {})
    all_positions = []
    for ledger in ledgers.values():
        all_positions.extend(ledger.get("open_positions", []))
    marks, mark_source = mark_positions(all_positions)

    latest_scan = state.get("scan_history", [{}])[-1] if state.get("scan_history") else {}
    strategies = []
    for name, ledger in ledgers.items():
        strategy_config = strategies_config.get(name, {})
        open_positions = ledger.get("open_positions", [])
        closed_positions = ledger.get("closed_positions", [])
        initial = money(ledger.get("initial_bankroll", strategy_config.get("paper_bankroll", 0.0)))
        cash = money(ledger.get("cash"))
        open_cost = sum(money(p.get("entry_total_cost", p.get("stake", 0.0))) for p in open_positions)
        bid_open_value = sum(marks.get(p.get("id"), {}).get("bid_value", 0.0) for p in open_positions)
        mid_open_value = sum(marks.get(p.get("id"), {}).get("mid_value", 0.0) for p in open_positions)
        realized = sum(money(p.get("pnl")) for p in closed_positions)
        equity_bid = cash + bid_open_value
        equity_mid = cash + mid_open_value
        scan_row = latest_scan.get("strategies", {}).get(name, {})
        strategies.append(
            {
                "id": name,
                "name": name.replace("_", " "),
                "platform": "Polymarket",
                "bot_type": classify_strategy(name, strategy_config),
                "mode": "paper",
                "status": "active" if strategy_config.get("enabled", True) else "paused",
                "description": describe_strategy(name, strategy_config),
                "initial_capital": initial,
                "cash": cash,
                "open_cost": open_cost,
                "equity_bid": equity_bid,
                "equity_mid": equity_mid,
                "realized_pnl": realized,
                "unrealized_bid_pnl": bid_open_value - open_cost,
                "unrealized_mid_pnl": mid_open_value - open_cost,
                "total_bid_pnl": equity_bid - initial,
                "total_mid_pnl": equity_mid - initial,
                "return_bid": (equity_bid - initial) / initial if initial else 0.0,
                "return_mid": (equity_mid - initial) / initial if initial else 0.0,
                "open_positions": len(open_positions),
                "closed_positions": len(closed_positions),
                "last_candidates": scan_row.get("candidates", 0),
                "last_opened": scan_row.get("opened", 0),
                "last_closed": scan_row.get("closed", 0),
                "fee_model": strategy_config.get("venue_fee_model", config.get("venue_fee_model")),
                "mark_source": mark_source,
                "positions": poly_positions_for_export(open_positions, marks, public)[:12],
            }
        )

    return {
        "platform": "Polymarket",
        "mode": "paper",
        "updated_at": state.get("updated_at"),
        "last_scan": latest_scan.get("at"),
        "strategies": strategies,
    }


def parse_screen_report_metrics():
    report = QUANT_ROOT / "output" / "screen_report.md"
    if not report.exists():
        return {}
    metrics = {}
    lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        if not line.startswith("| ") or " | " not in line or line.startswith("| Rank"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 10 or not cells[0].isdigit():
            continue
        strategy = cells[2]
        metrics[strategy] = {
            "cagr": cells[3],
            "vol": cells[4],
            "max_dd": cells[5],
            "sharpe": cells[6],
            "calmar": cells[7],
            "years": cells[8],
            "start": cells[9],
        }
    return metrics


def build_quant(public=True):
    account = read_json(QUANT_ACCOUNT, {})
    watchlist = read_json(QUANT_WATCHLIST, [])
    metrics = parse_screen_report_metrics()
    orders = read_csv_rows(QUANT_ORDERS)
    marks = read_csv_rows(QUANT_MARKS)

    latest_mark = marks[-1] if marks else {}
    total_equity = money(latest_mark.get("total_equity")) or money(account.get("starting_equity"))
    cash = money(latest_mark.get("cash")) or money(account.get("cash"))
    starting = money(account.get("starting_equity"))
    sleeves = []
    for sleeve in account.get("strategy_sleeves", []):
        strategy_id = sleeve.get("strategy")
        watch = next((item for item in watchlist if item.get("strategy") == strategy_id), {})
        sleeves.append(
            {
                "id": strategy_id,
                "name": sleeve.get("archetype") or strategy_id,
                "platform": "Stocks/Crypto",
                "bot_type": watch.get("family", "screened strategy").replace("_", " "),
                "mode": account.get("account_type", "local_paper"),
                "status": "waiting" if not account.get("positions") else "active",
                "description": watch.get("description", ""),
                "initial_capital": money(sleeve.get("target_notional")),
                "cash": money(sleeve.get("target_notional")) if not account.get("positions") else 0.0,
                "open_cost": 0.0,
                "equity_bid": money(sleeve.get("target_notional")),
                "equity_mid": money(sleeve.get("target_notional")),
                "realized_pnl": 0.0,
                "unrealized_bid_pnl": 0.0,
                "unrealized_mid_pnl": 0.0,
                "total_bid_pnl": 0.0,
                "total_mid_pnl": 0.0,
                "return_bid": 0.0,
                "return_mid": 0.0,
                "open_positions": 0,
                "closed_positions": len([o for o in orders if o.get("strategy") == strategy_id]),
                "last_candidates": None,
                "last_opened": 0,
                "last_closed": 0,
                "backtest": metrics.get(strategy_id, {}),
                "positions": [],
            }
        )

    return {
        "platform": "Stocks/Crypto",
        "mode": account.get("account_type", "local_paper"),
        "status": account.get("status"),
        "broker_connected": bool(account.get("broker_connected")),
        "broker_note": account.get("broker_note"),
        "updated_at": dt.datetime.fromtimestamp(QUANT_ACCOUNT.stat().st_mtime, dt.UTC).replace(microsecond=0).isoformat()
        if QUANT_ACCOUNT.exists()
        else None,
        "starting_equity": starting,
        "total_equity": total_equity,
        "cash": cash,
        "pnl": total_equity - starting if starting else 0.0,
        "return": (total_equity - starting) / starting if starting else 0.0,
        "strategies": sleeves,
    }


def aggregate(groups):
    strategies = []
    for group in groups:
        strategies.extend(group.get("strategies", []))
    initial = sum(money(s.get("initial_capital")) for s in strategies)
    equity_bid = sum(money(s.get("equity_bid")) for s in strategies)
    equity_mid = sum(money(s.get("equity_mid")) for s in strategies)
    realized = sum(money(s.get("realized_pnl")) for s in strategies)
    open_positions = sum(int(s.get("open_positions") or 0) for s in strategies)
    closed_positions = sum(int(s.get("closed_positions") or 0) for s in strategies)
    active = sum(1 for s in strategies if s.get("status") == "active")
    return {
        "initial_capital": initial,
        "equity_bid": equity_bid,
        "equity_mid": equity_mid,
        "total_bid_pnl": equity_bid - initial,
        "total_mid_pnl": equity_mid - initial,
        "return_bid": (equity_bid - initial) / initial if initial else 0.0,
        "return_mid": (equity_mid - initial) / initial if initial else 0.0,
        "realized_pnl": realized,
        "open_positions": open_positions,
        "closed_positions": closed_positions,
        "active_strategies": active,
        "strategy_count": len(strategies),
    }


def build_payload(public=True):
    groups = [build_polymarket(public=public), build_quant(public=public)]
    return {
        "generated_at": utc_now(),
        "visibility": "public" if public else "private",
        "security_note": "No API keys, wallet addresses, broker credentials, token IDs, or trading controls are exported.",
        "deployment_recommendation": "Cloudflare Pages plus Cloudflare Access for authenticated sharing; GitHub Pages only for public summaries.",
        "summary": aggregate(groups),
        "groups": groups,
    }


def main():
    parser = argparse.ArgumentParser(description="Export sanitized trading dashboard data.")
    parser.add_argument("--private", action="store_true", help="Include less-redacted local details. Do not publish publicly.")
    parser.add_argument("--out", default=str(PUBLIC_DATA_PATH), help="Output JSON path.")
    args = parser.parse_args()
    payload = build_payload(public=not args.private)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "generated_at": payload["generated_at"], "strategies": payload["summary"]["strategy_count"]}, indent=2))


if __name__ == "__main__":
    main()
