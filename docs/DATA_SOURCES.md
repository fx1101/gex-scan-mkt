# Data sources

Figures in this file are copied from the project research note dated **2026-11-15** (America/Chicago). That note checked official docs or the GitHub API on that date and marked anything it did not verify. This implementation pass did **not** re-open vendor pricing pages or exchange rule pages on 2026-11-16. Nothing below adds a price, a rate limit, a field name, or an hour that the note did not already record. If a cell was unverified there, it stays unverified here.

Phase 0–1 does not call any of these vendors. Tests use `tests/fixtures/` and block sockets. There is no order-placement client.

## What the engine needs from a chain

A later provider must return a `ChainSnapshot`: vendor name, `captured_at` in UTC and in America/Chicago, underlying, official spot (and futures quotes when the vendor has them), and one row per contract with OCC symbol, root, expiry, DTE, call/put, strike, multiplier, exercise style, settlement, bid/ask/last, volume, open interest, IV, delta, gamma, theta, vega, rho (null when the vendor omitted it), quote time, and quality flags.

The raw payload is kept. The fixture loader stores the file text and can gzip it under `vendor/symbol/snapshot_id.json.gz`. Do not drop the raw JSON.

## Source notes (as of the 2026-11-15 research)

### Webull OpenAPI

Docs cited by the research note: [developer.webull.com market-data overview](https://developer.webull.com/apis/docs/market-data-api/overview.md).

- Contract list: `GET /trading/instruments/options/contracts/list` (category `US_OPTION` in the note). The note says the docs list contracts by underlying, expiry, strike, root (example `SPXW`), style, and status, and that they include OCC examples such as `SPX241220P04200000` and underlying types including `INDEX_CALL_OPTION`.
- Snapshots: `GET /market-data/options/snapshots/list`. Fields the note says to map: `open_interest`, `imp_vol`, `gamma`, `delta`, `theta`, `vega`, `rho`, bid/ask, volume, strike price, times. Maximum **20 symbols per call**.
- Rate limits in that note, per `app_key` and per endpoint: production non-display option snapshots **300 requests / 60s** (sandbox **30/60s**); contract list production **60/60s** (sandbox **30/60s**). HTTP 429 on breach. The note says repeated breaches may cause temporary IP blocks.
- Official snapshots are described there as real-time **if** the OpenAPI options entitlement is on. Sandbox is 15-minute delayed by default unless production real-time is also subscribed. App/desktop quote subscriptions do **not** cover OpenAPI. Real-time US options need a separate **OPRA Real-Time Non-display** OpenAPI subscription.
- Retail API access, per the note, requires an opened Webull brokerage account and a Developer Console application (review typically 1–2 business days). Paper/sandbox is auto-approved. Official Python SDK named there: `webull-openapi-python-sdk`. `App Key` and `App Secret` are shown once. Live quotes via API need the non-display subscription and, if used, an IP whitelist.
- Index coverage: the note says Webull's brokerage site advertises Cboe index options **SPX, VIX, XSP, and DJX** ([webull.com/partners/cboe](https://www.webull.com/partners/cboe)), and that the OpenAPI contract-list docs contemplate index roots such as SPX/SPXW. **NDX and RUT availability on Webull was not confirmed** in that research. Do not claim them until a capability probe on the account says so.
- OpenAPI Advanced Quotes price is **not published** on the public docs, according to the note. Do not guess a dollar amount. Check the Advanced Quotes Center after logging into the developer site.
- A full SPX chain does not fit in one call. A later adapter should list, filter to a moneyness band and DTE cap, batch by 20, cache, and back off on 429. The note's design constraint: at 20 contracts per snapshot and 300 calls/minute, a naive full-chain refresh can take on the order of a couple of minutes and will burn the quota.
- **Do not implement order placement.** Insufficient-permission errors should fail clearly. Credentials stay in `.env`.

This release does not include the Webull adapter.

### TradingView

The research note's conclusion: TradingView is a chart and alert surface, not an options data source. There is no official retail API in that note for a full chain with OI and greeks. Pine cannot fetch options open interest. Do not scrape TradingView, and do not use unofficial "TradingView options API" sites. Webhook alerts, when a later phase builds them, follow TradingView's webhook documentation and must not place orders. TradingView plan fees were not needed for that conclusion and are not stated here.

Not implemented in this release.

### Cboe delayed quotes JSON

The research note verified on 2026-11-15 that `https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json` returns HTTP 307 to `https://cdn-api.cboe.com/api/global/delayed_quotes/options/_SPX.json`. Equity/ETF form in the note: `/options/{SYMBOL}.json` (example `SPY.json`). Index form uses a leading underscore (`_SPX`, `_NDX`).

The note says the payload includes open interest (typically prior-session OI) and Cboe-provided `iv`, `delta`, `gamma`, `theta`, `vega`. It is widely described as about 15 minutes delayed. No API key. It is an informal public CDN, not a contracted SLA.

**Terms:** review Cboe market-data policies before any redistribution or public product use. Personal local research is the intended v1 use. That common open-source practice is not a license grant. Free to fetch does not mean free to redistribute.

Not implemented in this release. It is the intended bootstrap source for a later phase, including a saved payload checked in as a fixture. Live fetch, when it exists, must be opt-in.

### Massive (formerly Polygon.io)

Pages cited: [massive.com/options](https://massive.com/options), [pricing](https://massive.com/pricing?product=options).

The note says the official comparison page (updated November 2026; Massive stated prices checked November 4, 2026) lists paid plans at **$29, $79, or $199/mo per market**, real-time US options on **Options Advanced at $199/mo**, and a commercial Options plan at **$1,999/mo**. Paid plans: unlimited API calls. Free plan: end-of-day, 2 years of history, 5 calls/min, per market. The live pricing page is dynamic; re-check it before buying. Confirm current field coverage and SPX/NDX/RUT symbol coverage in their docs rather than assuming this paragraph is still the invoice.

No Massive client is implemented. `MASSIVE_API_KEY` is an empty placeholder.

### ThetaData

Page cited: [thetadata.net/pricing](https://www.thetadata.net/pricing).

The note's individual-use prices (USD, cancel anytime, subject to tax): **Options Value $40/mo**, **Standard $80/mo**, **Pro $160/mo**. It says Options Standard explicitly includes option chain snapshots, coverage is US index and stocks, and individual plans include "Real-time access." Concurrent-request caps in the note: Value 2, Standard 4, Pro 8. Commercial pricing was a separate page and was not copied in full. Endpoint field names were "confirm in current docs," so they are not invented here.

No ThetaData client is implemented. The env placeholders are `THETADATA_USERNAME` and `THETADATA_PASSWORD` until the vendor's current auth docs name the real variables.

### Tradier

Pages cited: [options chain docs](https://docs.tradier.com/brokerage-api/market-data/get-options-chains), [pricing](https://tradier.com/pricing).

The note says the brokerage API has a GET options chain with optional `greeks=true`, and that API access is included on Lite, Pro, and Pro Plus. Plan fees in the note: **Lite $0/mo**, **Pro $10/mo**, **Pro Plus $35/mo**, plus contract commissions, exchange, clearing, and regulatory fees. The fee schedule lists single-listed index options including **SPX, NDX, RUT, VIX, XSP, DJX, OEX, XEO**. That is trading-fee evidence, not by itself a guarantee of API quote coverage. Real-time versus delayed, and index-option entitlements, have to be confirmed for the specific plan.

Do not implement live order placement unless Chris later asks for that specific step in writing.

No Tradier client is implemented. `TRADIER_TOKEN` is empty.

### Charles Schwab Trader API

The note says a public Trader API exists at [developer.schwab.com](https://developer.schwab.com). Community reports of options-chain and Greeks endpoints were **not independently verified from Schwab's official docs** in that pass. The official fee schedule was not fetched. Do not assume the API is free.

Not implemented. Not an env var in this release.

### Interactive Brokers

Page cited: [Market Data Pricing](https://www.interactivebrokers.com/en/pricing/market-data-pricing.php).

The note says options data is available via TWS/API once market-data lines and OPRA are entitled, and that this is also a path to Eurex, Osaka, and other non-US options later. Official delayed OPRA is 15 minutes; real-time needs the OPRA subscription. Official figures in the note: **OPRA Top of Book (L1) USD 1.50/mo non-pro**, **USD 32.75/mo professional**. Non-pro OPRA fee waived at **USD 20** commissions/month/user, per the waiver table on that page. Default 100 market-data lines. Other bundles and futures fees are separate.

Not implemented.

### ORATS

The note calls ORATS a commercial options analytics vendor and says **prices were not verified** from an official ORATS page. Check orats.com before treating any price as real. Not required for v1. Not implemented.

## Fixture provider

`FixtureProvider` reads local JSON. That is the only provider in this release. The chains under `tests/fixtures/` are synthetic: the expected GEX numbers are hand-calculated from the formula in `docs/METHODOLOGY.md`. They are not recorded vendor payloads.

## Logging and secrets

`WEBULL_APP_KEY`, `WEBULL_APP_SECRET`, `MASSIVE_API_KEY`, `THETADATA_USERNAME`, `THETADATA_PASSWORD`, `TRADIER_TOKEN`, and `ALERT_WEBHOOK_URL` are redacted out of log lines when they are set in the environment. Empty values are left alone. Do not print secrets. Do not commit `.env`, token caches, or raw dumps that might contain account ids (see `.gitignore`).
