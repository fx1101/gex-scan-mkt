# GEX Session Scanner

Research tool for dealer-style gamma exposure (GEX) on US listed options. The working package name is `gex-scanner`. This repository is the product; it is not nested under another directory.

Phases 0 through 2 are in this tree: the project scaffold, the methodology docs, the offline GEX engine, and flip repricing on a spot grid. Later phases (live vendors, the session clock, ranking, TradingView, backtests) are not started.

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
```

`pytest` blocks outbound sockets. Fixture chains live in `tests/fixtures/`. Expected per-contract and per-strike GEX is inside each fixture and is checked within 1 USD of the documented unit.

## Layout

```
src/gex_scanner/          pure engine, fixture adapter, session key list
tests/fixtures/           synthetic SPY, SPX-style, non-standard, and missing-IV chains
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
