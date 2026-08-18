"""Scan long-dated options and rank them by option lambda (elasticity)."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Iterable, Sequence

from watchlist import TICKERS


@dataclass(frozen=True)
class OptionResult:
    ticker: str
    option_type: str
    contract: str
    expiration: str
    days: int
    strike: float
    spot: float
    price: float
    implied_volatility: float
    delta: float
    lambda_value: float
    volume: int
    open_interest: int


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def black_scholes_delta(
    spot: float,
    strike: float,
    years: float,
    volatility: float,
    risk_free_rate: float,
    dividend_yield: float,
    option_type: str,
) -> float:
    """Return Black-Scholes delta for a European call or put."""
    if min(spot, strike, years, volatility) <= 0:
        raise ValueError("spot, strike, years, and volatility must be positive")
    d1 = (
        math.log(spot / strike)
        + (risk_free_rate - dividend_yield + volatility**2 / 2.0) * years
    ) / (volatility * math.sqrt(years))
    discounted = math.exp(-dividend_yield * years)
    if option_type == "call":
        return discounted * _normal_cdf(d1)
    if option_type == "put":
        return discounted * (_normal_cdf(d1) - 1.0)
    raise ValueError("option_type must be 'call' or 'put'")


def option_lambda(delta: float, spot: float, option_price: float) -> float:
    """Return option elasticity: delta times underlying price / option price."""
    if option_price <= 0:
        raise ValueError("option price must be positive")
    return delta * spot / option_price


def _number(value: object, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _option_price(row: object) -> float:
    bid = _number(getattr(row, "bid", None))
    ask = _number(getattr(row, "ask", None))
    if bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return _number(getattr(row, "lastPrice", None))


def _spot_price(ticker: object) -> float:
    try:
        spot = _number(ticker.fast_info["last_price"])
    except (KeyError, TypeError, AttributeError):
        spot = 0.0
    if spot <= 0:
        history = ticker.history(period="5d")
        if not history.empty:
            spot = _number(history["Close"].dropna().iloc[-1])
    if spot <= 0:
        raise ValueError("could not determine a positive underlying price")
    return spot


def scan_symbol(
    symbol: str,
    *,
    minimum_days: int = 365,
    risk_free_rate: float = 0.045,
    option_types: Sequence[str] = ("call", "put"),
    today: date | None = None,
) -> list[OptionResult]:
    """Download and calculate qualifying contracts for one symbol."""
    import yfinance as yf

    today = today or datetime.now().date()
    ticker = yf.Ticker(symbol)
    spot = _spot_price(ticker)
    try:
        dividend_yield = max(0.0, _number(ticker.info.get("dividendYield")))
    except (AttributeError, TypeError):
        dividend_yield = 0.0

    results: list[OptionResult] = []
    for expiration_text in ticker.options:
        expiration = datetime.strptime(expiration_text, "%Y-%m-%d").date()
        days = (expiration - today).days
        if days < minimum_days:
            continue
        chain = ticker.option_chain(expiration_text)
        for option_type in option_types:
            frame = getattr(chain, f"{option_type}s")
            for row in frame.itertuples(index=False):
                price = _option_price(row)
                strike = _number(getattr(row, "strike", None))
                volatility = _number(getattr(row, "impliedVolatility", None))
                if min(price, strike, volatility) <= 0:
                    continue
                try:
                    delta = black_scholes_delta(
                        spot,
                        strike,
                        days / 365.0,
                        volatility,
                        risk_free_rate,
                        dividend_yield,
                        option_type,
                    )
                    elasticity = option_lambda(delta, spot, price)
                except (ValueError, OverflowError):
                    continue
                results.append(
                    OptionResult(
                        ticker=symbol.upper(),
                        option_type=option_type,
                        contract=str(getattr(row, "contractSymbol", "")),
                        expiration=expiration_text,
                        days=days,
                        strike=strike,
                        spot=spot,
                        price=price,
                        implied_volatility=volatility,
                        delta=delta,
                        lambda_value=elasticity,
                        volume=int(_number(getattr(row, "volume", None))),
                        open_interest=int(_number(getattr(row, "openInterest", None))),
                    )
                )
    return results


def scan_watchlist(
    tickers: Iterable[str], **scan_options: object
) -> tuple[list[OptionResult], list[str]]:
    results: list[OptionResult] = []
    errors: list[str] = []
    for symbol in tickers:
        try:
            results.extend(scan_symbol(symbol, **scan_options))
        except Exception as exc:  # Keep a bad remote symbol from stopping the scan.
            errors.append(f"{symbol}: {exc}")
    results.sort(key=lambda item: item.lambda_value, reverse=True)
    return results, errors


def print_table(results: Sequence[OptionResult]) -> None:
    headers = ("TICKER", "TYPE", "EXPIRY", "DAYS", "STRIKE", "SPOT", "PRICE", "IV", "DELTA", "LAMBDA", "VOLUME", "OI", "CONTRACT")
    print(" ".join(f"{header:>10}" for header in headers[:-1]) + "  CONTRACT")
    for item in results:
        values = (
            item.ticker, item.option_type, item.expiration, str(item.days),
            f"{item.strike:.2f}", f"{item.spot:.2f}", f"{item.price:.2f}",
            f"{item.implied_volatility:.2%}", f"{item.delta:.3f}",
            f"{item.lambda_value:.2f}", str(item.volume), str(item.open_interest),
        )
        print(" ".join(f"{value:>10}" for value in values) + f"  {item.contract}")


def write_csv(path: str, results: Sequence[OptionResult]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=[field.name for field in fields(OptionResult)])
        writer.writeheader()
        writer.writerows(item.__dict__ for item in results)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-days", type=int, default=365, help="minimum calendar days to expiration (default: 365)")
    parser.add_argument("--risk-free-rate", type=float, default=0.045, help="annual decimal risk-free rate (default: 0.045)")
    parser.add_argument("--type", choices=("call", "put", "both"), default="both", help="contract type to include")
    parser.add_argument("--limit", type=int, default=50, help="maximum displayed rows; 0 means all")
    parser.add_argument("--csv", metavar="PATH", help="also write all matching rows to CSV")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.min_days < 0 or args.limit < 0:
        print("--min-days and --limit cannot be negative", file=sys.stderr)
        return 2
    option_types = ("call", "put") if args.type == "both" else (args.type,)
    results, errors = scan_watchlist(
        TICKERS,
        minimum_days=args.min_days,
        risk_free_rate=args.risk_free_rate,
        option_types=option_types,
    )
    visible = results if args.limit == 0 else results[: args.limit]
    print_table(visible)
    if args.csv:
        write_csv(args.csv, results)
    for error in errors:
        print(f"warning: {error}", file=sys.stderr)
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
