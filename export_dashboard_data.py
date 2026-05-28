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


def first_money(*values):
    for value in values:
        if value is not None:
            return money(value)
    return 0.0


def write_json_atomic(path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


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
    return text.replace("0x", "[hex-redacted]:")


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
        marks = {}
        for position in positions:
            cost = money(position.get("entry_total_cost", position.get("stake", 0.0)))
            marks[position.get("id")] = {
                "bid_value": cost,
                "mid_value": cost,
                "bid_pnl": 0.0,
                "mid_pnl": 0.0,
                "missing_marks": 1,
                "mark_warning": f"mark fetch failed; carrying at cost: {exc}",
            }
        return marks, f"mark fetch failed; carrying positions at cost: {exc}"

    marks = {}
    for position in positions:
        position_id = position.get("id")
        cost = money(position.get("entry_total_cost", position.get("stake", 0.0)))
        if position.get("type") == "bundle":
            bundles = money(position.get("bundles"))
            bid_value = 0.0
            mid_value = 0.0
            bid_exit_fees = 0.0
            mid_exit_fees = 0.0
            missing = 0
            for leg in position.get("legs", []):
                token = str(leg.get("no_token_id", ""))
                bid = bids.get(token)
                ask = asks.get(token)
                if bid is None or ask is None:
                    missing += 1
                    continue
                mid = (bid + ask) / 2
                category = leg.get("category", "other")
                venue = position.get("fee_model", "polymarket_global_taker")
                bid_value += bundles * bid
                mid_value += bundles * mid
                bid_exit_fees += fee_for_trade(bid, bundles, category, venue)
                mid_exit_fees += fee_for_trade(mid, bundles, category, venue)
            bid_value -= bid_exit_fees
            mid_value -= mid_exit_fees
            marks[position_id] = {
                "bid_value": bid_value,
                "mid_value": mid_value,
                "bid_pnl": bid_value - cost,
                "mid_pnl": mid_value - cost,
                "missing_marks": missing,
                "bid_exit_fee": bid_exit_fees,
                "mid_exit_fee": mid_exit_fees,
                "mark_warning": "partial bundle quote data" if missing else None,
            }
            continue

        token = str(position.get("token_id", ""))
        bid = bids.get(token)
        ask = asks.get(token)
        if bid is None or ask is None:
            marks[position_id] = {
                "bid_value": cost,
                "mid_value": cost,
                "bid_pnl": 0.0,
                "mid_pnl": 0.0,
                "missing_marks": 1,
                "mark_warning": "missing quote; carrying at cost",
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
            "mark_warning": None,
        }
    return marks, "live order-book marks"


def poly_positions_for_export(positions, marks, public):
    exported = []
    for position in positions:
        mark = marks.get(position.get("id"), {})
        is_bundle = position.get("type") == "bundle"
        bundles = money(position.get("bundles")) if is_bundle else 0.0
        cost = money(position.get("entry_total_cost", position.get("stake", 0.0)))
        entry_price = cost / bundles if is_bundle and bundles else money(position.get("entry_ask"))
        bid = mark.get("bid")
        ask = mark.get("ask")
        quote_kind = "bid / ask"
        if is_bundle:
            bid = mark.get("bid_value") / bundles if bundles else None
            ask = mark.get("mid_value") / bundles if bundles else None
            quote_kind = "bundle bid / mid"
        exported.append(
            {
                "id": position.get("id") if not public else None,
                "question": safe_question(position.get("question") or position.get("event_title"), public),
                "side": position.get("outcome", "bundle"),
                "type": position.get("type", "single"),
                "opened_at": position.get("opened_at"),
                "end_date": position.get("end_date"),
                "entry_price": entry_price,
                "cost": cost,
                "bid_pnl": mark.get("bid_pnl"),
                "mid_pnl": mark.get("mid_pnl"),
                "bid": bid,
                "ask": ask,
                "quote_kind": quote_kind,
                "mark_warning": mark.get("mark_warning"),
                "missing_marks": mark.get("missing_marks", 0),
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
        missing_mark_count = sum(int(marks.get(p.get("id"), {}).get("missing_marks", 0)) for p in open_positions)
        realized = sum(money(p.get("pnl")) for p in closed_positions)
        equity_bid = cash + bid_open_value
        equity_mid = cash + mid_open_value
        scan_row = latest_scan.get("strategies", {}).get(name, {})
        exported_positions = poly_positions_for_export(open_positions, marks, public)
        strategies.append(
            {
                "id": name,
                "name": name.replace("_", " "),
                "platform": "Polymarket",
                "bot_type": classify_strategy(name, strategy_config),
                "mode": "paper",
                "status": "active" if strategy_config.get("enabled", True) else "paused",
                "description": describe_strategy(name, strategy_config),
                "execution_model": "paper taker at displayed best ask; order-book depth is not simulated",
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
                "missing_mark_count": missing_mark_count,
                "positions_exported": len(exported_positions),
                "positions_truncated": False,
                "positions": exported_positions,
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


def quant_order_stats(orders):
    cost_bps = 1.0
    positions = {}
    realized_by_strategy = {}
    order_count_by_strategy = {}
    exit_count_by_strategy = {}

    for order in orders:
        strategy = order.get("strategy")
        symbol = order.get("symbol")
        if not strategy or not symbol:
            continue
        side = str(order.get("side", "")).upper()
        quantity = money(order.get("quantity"))
        notional = money(order.get("notional"))
        if quantity <= 0 or notional <= 0:
            continue
        order_count_by_strategy[strategy] = order_count_by_strategy.get(strategy, 0) + 1
        key = (strategy, symbol)
        current = positions.setdefault(key, {"quantity": 0.0, "cost_basis": 0.0})
        fee = notional * cost_bps / 10000.0
        if side == "BUY":
            current["quantity"] += quantity
            current["cost_basis"] += notional + fee
        elif side == "SELL":
            exit_count_by_strategy[strategy] = exit_count_by_strategy.get(strategy, 0) + 1
            prior_qty = max(current["quantity"], 0.0)
            basis_reduction = current["cost_basis"] * min(quantity / prior_qty, 1.0) if prior_qty else 0.0
            proceeds = notional - fee
            realized_by_strategy[strategy] = realized_by_strategy.get(strategy, 0.0) + proceeds - basis_reduction
            current["quantity"] = max(0.0, current["quantity"] - quantity)
            current["cost_basis"] = max(0.0, current["cost_basis"] - basis_reduction)

    avg_entry = {}
    for key, value in positions.items():
        qty = value["quantity"]
        avg_entry[key] = value["cost_basis"] / qty if qty else 0.0

    return {
        "positions": positions,
        "avg_entry": avg_entry,
        "realized_by_strategy": realized_by_strategy,
        "order_count_by_strategy": order_count_by_strategy,
        "exit_count_by_strategy": exit_count_by_strategy,
    }


def build_quant(public=True):
    account = read_json(QUANT_ACCOUNT, {})
    watchlist = read_json(QUANT_WATCHLIST, [])
    metrics = parse_screen_report_metrics()
    orders = read_csv_rows(QUANT_ORDERS)
    marks = read_csv_rows(QUANT_MARKS)
    order_stats = quant_order_stats(orders)

    latest_mark = marks[-1] if marks else {}
    sleeve_states = account.get("sleeve_states", {})
    total_equity = money(account.get("total_equity")) or money(latest_mark.get("total_equity")) or money(account.get("starting_equity"))
    cash = money(account.get("cash")) or money(latest_mark.get("cash"))
    starting = money(account.get("starting_equity"))
    sleeves = []
    for sleeve in account.get("strategy_sleeves", []):
        strategy_id = sleeve.get("strategy")
        platform = "Crypto" if "BTC-USD" in strategy_id or "ETH-USD" in strategy_id else "Stocks"
        watch = next((item for item in watchlist if item.get("strategy") == strategy_id), {})
        state = sleeve_states.get(strategy_id, {})
        positions = state.get("positions", {})
        initial = money(sleeve.get("target_notional"))
        equity = money(state.get("equity")) if "equity" in state else initial
        sleeve_cash = money(state.get("cash")) if state else initial
        positions_value = money(state.get("positions_value"))
        realized_pnl = order_stats["realized_by_strategy"].get(strategy_id, money(state.get("realized_pnl")))
        order_count = order_stats["order_count_by_strategy"].get(strategy_id, 0)
        exit_count = order_stats["exit_count_by_strategy"].get(strategy_id, 0)
        position_rows = []
        for symbol, position in positions.items():
            quantity = money(position.get("quantity"))
            price = money(position.get("last_price"))
            market_value = money(position.get("market_value")) or quantity * price
            if abs(quantity) <= 1e-10:
                continue
            order_position = order_stats["positions"].get((strategy_id, symbol), {})
            cost_basis = order_position.get("cost_basis", 0.0)
            if not cost_basis:
                cost_basis = money(position.get("cost_basis"))
            if not cost_basis:
                cost_basis = market_value
            avg_entry = order_stats["avg_entry"].get((strategy_id, symbol), 0.0)
            if not avg_entry:
                avg_entry = money(position.get("average_entry_price")) or price
            weight = market_value / equity if equity else 0.0
            label = symbol
            if platform == "Crypto" and symbol == "BIL":
                label = "BIL (fallback cash/T-bill sleeve for crypto strategy)"
            position_rows.append(
                {
                    "question": label,
                    "side": "Long",
                    "type": "asset",
                    "opened_at": account.get("last_run_at"),
                    "end_date": None,
                    "last_signal_date": state.get("last_signal_date"),
                    "entry_price": avg_entry,
                    "cost": cost_basis,
                    "bid_pnl": market_value - cost_basis,
                    "mid_pnl": market_value - cost_basis,
                    "bid": price,
                    "ask": price,
                    "quantity": quantity,
                    "market_value": market_value,
                    "weight": weight,
                    "status": "open",
                }
            )
        sleeves.append(
            {
                "id": strategy_id,
                "name": sleeve.get("archetype") or strategy_id,
                "platform": platform,
                "bot_type": watch.get("family", "screened strategy").replace("_", " "),
                "mode": account.get("account_type", "local_paper"),
                "status": "active" if position_rows else "waiting",
                "description": watch.get("description", ""),
                "initial_capital": initial,
                "cash": sleeve_cash,
                "open_cost": sum(money(row.get("cost")) for row in position_rows),
                "equity_bid": equity,
                "equity_mid": equity,
                "realized_pnl": realized_pnl,
                "unrealized_bid_pnl": sum(money(row.get("bid_pnl")) for row in position_rows),
                "unrealized_mid_pnl": sum(money(row.get("mid_pnl")) for row in position_rows),
                "total_bid_pnl": equity - initial,
                "total_mid_pnl": equity - initial,
                "return_bid": (equity - initial) / initial if initial else 0.0,
                "return_mid": (equity - initial) / initial if initial else 0.0,
                "open_positions": len(position_rows),
                "closed_positions": exit_count,
                "orders_count": order_count,
                "last_candidates": None,
                "last_opened": 0,
                "last_closed": exit_count,
                "backtest": metrics.get(strategy_id, {}),
                "last_signal_date": state.get("last_signal_date"),
                "execution_model": account.get("execution_model", "daily close model paper fills; not broker-routed"),
                "target_weights": state.get("target_weights", {}),
                "positions": position_rows,
            }
        )

    updated_at = (
        dt.datetime.fromtimestamp(QUANT_ACCOUNT.stat().st_mtime, dt.UTC).replace(microsecond=0).isoformat()
        if QUANT_ACCOUNT.exists()
        else None
    )
    groups = []
    for platform_name in ("Stocks", "Crypto"):
        platform_strategies = [strategy for strategy in sleeves if strategy.get("platform") == platform_name]
        group_starting = sum(money(strategy.get("initial_capital")) for strategy in platform_strategies)
        group_equity = sum(money(strategy.get("equity_bid")) for strategy in platform_strategies)
        group_cash = sum(money(strategy.get("cash")) for strategy in platform_strategies)
        groups.append(
            {
                "platform": platform_name,
                "mode": account.get("account_type", "local_paper"),
                "status": "active" if any(strategy.get("status") == "active" for strategy in platform_strategies) else "waiting",
                "broker_connected": bool(account.get("broker_connected")),
                "broker_note": account.get("broker_note") if not public else None,
                "updated_at": updated_at,
                "starting_equity": group_starting,
                "total_equity": group_equity,
                "cash": group_cash,
                "pnl": group_equity - group_starting if group_starting else 0.0,
                "return": (group_equity - group_starting) / group_starting if group_starting else 0.0,
                "strategies": platform_strategies,
            }
        )
    return groups


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
    groups = [build_polymarket(public=public), *build_quant(public=public)]
    return {
        "generated_at": utc_now(),
        "visibility": "public" if public else "private",
        "security_note": "No API keys, wallet addresses, broker credentials, token IDs, or trading controls are exported. Public data still includes market names, sides, prices, and paper position sizes.",
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
    write_json_atomic(out, payload)
    print(json.dumps({"out": str(out), "generated_at": payload["generated_at"], "strategies": payload["summary"]["strategy_count"]}, indent=2))


if __name__ == "__main__":
    main()
