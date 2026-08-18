# Long-dated options scanner

This command-line scanner downloads option chains with `yfinance`, keeps contracts
with at least 365 calendar days to expiration, and sorts them by **lambda** from
highest to lowest. Lambda (also called elasticity or leverage) is calculated as:

```text
lambda = Black-Scholes delta × underlying price / option midpoint
```

Put delta—and therefore put lambda—is negative. The midpoint of bid and ask is
used when both are available; otherwise the last traded price is used. Contracts
without a usable price, strike, or implied volatility are skipped.

## Setup and use

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python options_scanner.py
```

Edit `TICKERS` in `watchlist.py` to change the independently maintained watchlist.
Useful options include:

```bash
python options_scanner.py --type call --limit 25
python options_scanner.py --min-days 500 --csv options.csv
python options_scanner.py --risk-free-rate 0.04 --limit 0
```

The risk-free rate is an annual decimal assumption and defaults to 4.5%. The
scanner uses each symbol's reported dividend yield. `--csv` contains every match,
even when `--limit` shortens the terminal display.
