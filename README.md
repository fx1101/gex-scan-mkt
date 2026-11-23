# GEX Session Scanner

Research tool for dealer-style gamma exposure (GEX) on US listed options. The working package name is `gex-scanner`. This repository is the product; it is not nested under another directory.

Phases 0 through 6 are in this tree: the project scaffold, the methodology docs, the offline GEX engine, flip repricing, the Cboe delayed-quotes parser, the America/Chicago session clock, the Webull OpenAPI adapter, the fixture-universe rank, SQLite replay, a local dashboard, TradingView level export, webhook alerts, and the pre-registered validation report. An Alpaca market-data adapter sits beside Webull and does not replace it. A live Cboe download requires `--network`. A Webull download requires sandbox keys in the environment and is not part of `pytest`. An Alpaca download requires `ALPACA_API_KEY` and `ALPACA_API_SECRET` and is not part of `pytest`. No script places orders. The 2026-11-17 report has no chain history in the window, so the dashboard badge stays unvalidated hypothesis.

This is not an auto-trader. There is no order-placement code. Do not put production Webull keys in the environment for this phase. Sandbox is the default written in `.env.example` for a later adapter.

GEX here is an estimate under a stated sign convention. It is not a record of market-maker positions. Ranked setups, when a later phase draws them, are research scores. Profitability belongs in a backtest report after those tests exist.

## Quick start (offline)

Requires Python 3.11 or newer. No network and no API key.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python scripts/gex_fixture.py tests/fixtures/spy_chain.json
python scripts/cboe_snapshot.py --fixture tests/fixtures/recorded/cboe_nok_delayed.json
python scripts/webull_snapshot.py
python scripts/alpaca_snapshot.py
python scripts/scan_fixtures.py
python scripts/export_tv.py tests/fixtures/spx_chain.json
python scripts/dashboard.py
python scripts/validate_history.py
```

`webull_snapshot.py` with empty keys prints a line and exits. It downloads one symbol only when `WEBULL_APP_KEY` and `WEBULL_APP_SECRET` are set and `WEBULL_ENVIRONMENT` is `sandbox`. `alpaca_snapshot.py` does the same when `ALPACA_API_KEY` or `ALPACA_API_SECRET` is empty, and it requests market data only.

`scan_fixtures.py` ranks `config/universe.toml` against `tests/fixtures/` and writes `data/scanner.sqlite`. Symbols with no fixture are skipped. `dashboard.py` serves that file on `127.0.0.1:8765`. `validate_history.py` rewrites `docs/backtests/2026-11-17-validation.md` from the files on disk. It does not download a chain.

## TradingView levels

The overlay does not fetch a chain. Paste one line.

1. Run `python scripts/export_tv.py tests/fixtures/spx_chain.json`.
2. Copy the single printed line. Add `--json levels.json` if you also want the JSON artifact.
3. Open the Pine Editor, paste `src/gex_scanner/tv/pine/gex_levels.pine`, and add it to the chart.
4. Open the indicator settings and paste the line into the Levels input.

The script draws the flip, the call wall, the put wall, and the 0DTE walls. Empty fields stay off the chart. Outgoing alerts use `ALERT_WEBHOOK_URL` and send JSON only. They do not place orders.

`pytest` blocks outbound sockets. Fixture chains live in `tests/fixtures/`. Expected per-contract and per-strike GEX is inside each fixture and is checked within 1 USD of the documented unit.

## Layout

```
src/gex_scanner/          engine, adapters, ranker, SQLite store, local dashboard
tests/fixtures/           synthetic chains, plus recorded/ Cboe and Webull slices
config/universe.toml      indexes, ETFs, and the starter stock list
docs/METHODOLOGY.md       formulas, sign convention, what is not built yet
docs/SESSIONS.md          America/Chicago session definitions
docs/DATA_SOURCES.md      entitlements, limits, and terms notes from the 2026-11-15 research
docs/PRIOR_ART.md         GitHub survey dated 2026-11-16
```

The engine reads each contract's `multiplier`. It does not assume 100.

## License

Original code in this repository is Apache-2.0. See `LICENSE` and `THIRD_PARTY_NOTICES.md`. No third-party GEX source was copied.

## Secrets

Copy `.env.example` to `.env` if a later phase needs keys. `.env` is gitignored. Logs redact the variables named in `.env.example` when those values are set. Do not commit tokens, account dumps, or a filled-in env file.
