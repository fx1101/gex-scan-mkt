# Data sources

Prices, rate limits, and vendor plan notes in this file are copied from the project research note dated **2026-11-15** (America/Chicago). That note checked official docs or the GitHub API on that date and marked anything it did not verify. Those cells were not re-checked on 2026-11-16. Two later reads are dated where they appear: a Cboe delayed-quotes payload saved on 2026-11-16, and the NYSE holiday table cited in `docs/SESSIONS.md`. Nothing below adds a price or a rate limit the 2026-11-15 note did not already record.

Tests use `tests/fixtures/` and block sockets. Live Cboe download is opt-in (`--network`) and is not part of the test run. There is no order-placement client. The Webull and Alpaca adapters read market data only.

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

`gex_scanner.adapters.webull` maps those documented fields. HTTP 401 and 403 raise `EntitlementError` and name the OPRA Real-Time Non-display subscription. HTTP 429 uses a token bucket and backoff. The bucket uses the rates in the list above: sandbox 30/60s on both the contract list and the option snapshots; production 300/60s snapshots and 60/60s on the contract list. Snapshot calls are batches of at most 20. Before those calls, contracts outside ±15% of spot or beyond a 30-day DTE cap are skipped. The official SDK's `end_date` parameter is an inclusive lower bound on expiration, so it is not used as that cap.

The capability probe asks the contract list about SPX, SPXW (root on SPX), NDX, RUT, SPY, QQQ, and IWM. A name is covered only when at least one contract comes back. An empty page or a 403 is not coverage.

`scripts/webull_snapshot.py` is the dry run. Empty `WEBULL_APP_KEY` or `WEBULL_APP_SECRET` exits without importing the SDK and without a socket. `WEBULL_ENVIRONMENT` must be `sandbox`; anything else is refused. When sandbox keys are set it imports `webull-openapi-python-sdk` and uses that package's US region table. This repository does not embed an API host and does not construct a trade client.

`tests/fixtures/recorded/webull_spy_chain.json` is a redacted example. The field names are the ones in `webull-inc/webull-openapi-python-sdk` and `webull-openapi-mcp` as read on 2026-11-16. It is not a capture from an account, and it contains no app key, app secret, or token.

### Alpaca Market Data

Read on 2026-11-22 from the public docs, not from a live call: [option chain](https://docs.alpaca.markets/us/reference/optionchain), [option snapshots](https://docs.alpaca.markets/us/reference/optionsnapshots), and [About Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api). Dollar prices on that About page were not copied here. Re-check them before treating a plan as an invoice.

`gex_scanner.adapters.alpaca` requests only `https://data.alpaca.markets`.

- Chain: `GET /v1beta1/options/snapshots/{underlying}` with an explicit `feed`. The dry run sends `indicative`. `opra` is not assumed. The snapshot object maps `latestQuote` (`bp`, `ap`, `t`), `latestTrade` (`p`, and `s` as last-trade size, flagged `volume_is_last_trade_size`), `impliedVolatility`, and `greeks` (`delta`, `gamma`, `theta`, `vega`, `rho`) when those values are numbers.
- Spot for a US equity or ETF: `GET /v2/stocks/{symbol}/trades/latest?feed=iex`. `spot_field` is `iex`. That print is one venue, not the consolidated tape.
- Auth: `ALPACA_API_KEY` and `ALPACA_API_SECRET` are mapped inside the adapter to `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`. The dry-run script does not name those headers.
- The published snapshot schema does not include open interest. `open_interest` and `open_interest_date` are copied only when a payload includes them. The contracts list that carries those fields on Alpaca's trading host is not called. A null open interest is not stored as zero. Missing `greeks` stays null and is flagged `missing_greeks`. The adapter does not compute Black-Scholes gamma.
- Multiplier uses `size` when the payload has it. A missing multiplier is stored as 100 and flagged `multiplier_not_in_payload`. Style is copied from `style` when it is `american` or `european`. Settlement is not inferred.
- Scope is US equity and ETF underlyings, filtered to ±15% of spot and 30 calendar days. NDX, RUT, SPX, and futures symbols raise `CoverageError` before a request. `futures` on the snapshot is empty. There is no order path and no websocket.
- The token bucket uses 200 calls per minute, the Basic historical figure in the 2026-11-22 read of the About page. HTTP 429 backs off. HTTP 401 and 403 are entitlement errors.

`scripts/alpaca_snapshot.py` prints a line and exits when either Alpaca env value is empty. It does not open a socket in that case.

`tests/fixtures/recorded/alpaca_spy_chain.json` is a field example built from those public schemas. It is not an account capture.

### TradingView

The research note's conclusion: TradingView is a chart and alert surface, not an options data source. There is no official retail API in that note for a full chain with OI and greeks. Pine cannot fetch options open interest. Do not scrape TradingView, and do not use unofficial "TradingView options API" sites. TradingView plan fees were not needed for that conclusion and are not stated here.

`scripts/export_tv.py` prints a level string. `src/gex_scanner/tv/pine/gex_levels.pine` draws those inputs. Outgoing alerts are JSON from `ALERT_WEBHOOK_URL`. Incoming TradingView webhooks are accepted as JSON with `symbol`, `price`, and `event`. Neither path places an order, and the JSON does not include API keys. The webhook shape follows TradingView's [webhook alert](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/) documentation only as a destination for a message this app already computed.

### Cboe delayed quotes JSON

The research note verified on 2026-11-15 that `https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json` returns HTTP 307 to `https://cdn-api.cboe.com/api/global/delayed_quotes/options/_SPX.json`. Equity/ETF form in the note: `/options/{SYMBOL}.json` (example `SPY.json`). Index form uses a leading underscore (`_SPX`, `_NDX`).

The note says the payload includes open interest (typically prior-session OI) and Cboe-provided `iv`, `delta`, `gamma`, `theta`, `vega`. It is widely described as about 15 minutes delayed. No API key. It is an informal public CDN, not a contracted SLA.

**Terms of use.** Review Cboe market-data policies before any redistribution or a public hosted product. Personal local research is the intended v1 use. Open-source tools that fetch this CDN are not a license grant. Free to fetch does not mean free to redistribute. The checked-in files are short slices of two responses saved for the parser test, not a data product.

`gex_scanner.adapters.cboe_delayed` parses that JSON. `scripts/cboe_snapshot.py` reads a saved file with `--fixture`. A download happens only when the script is given `--network` (or `fetch_delayed_quotes(..., network=True)`). The client follows the 307 to `cdn-api.cboe.com`. The raw body is kept on the snapshot and can be gzipped under `vendor/symbol/snapshot_id`.

On 2026-11-16 this tree saved two truncated responses. The objects that remain were copied from the CDN body; the `options` arrays were shortened. Those slices are not an 18-month archive. The validation window 2025-05-17 through 2026-11-17 has no chain session built from them. ThetaData and Massive were not called.

| File | URL | CDN timestamp | What was kept |
| --- | --- | --- | --- |
| `tests/fixtures/recorded/cboe_nok_delayed.json` | `.../options/NOK.json` | `2026-11-16 00:29:44` | Header plus 4 of 772 contracts |
| `tests/fixtures/recorded/cboe_spx_delayed.json` | `.../options/_SPX.json` | `2026-11-15 22:25:08` | Header plus 1 of 30074 contracts |

Fields present on those payloads, and used by the parser: `timestamp`, `symbol`, `data.symbol`, `data.security_type`, `data.current_price`, `data.options[]` with `option`, `bid`, `ask`, `iv`, `open_interest`, `volume`, `delta`, `gamma`, `theta`, `vega`, `rho`, `last_trade_price`, `last_trade_time`. The payload has no multiplier. The adapter sets 100 and flags `multiplier_not_in_payload`. Style and settlement are also absent: `stock` is mapped to American physical and `index` to European cash, both flagged `style_not_in_payload`. Underlying `iv30` is not copied onto contracts. Option `iv` is stored as the number in the file.

The NOK chain `timestamp` matched the HTTP `Last-Modified` GMT clock within a few seconds, so a naive chain timestamp is read as UTC. Naive `last_trade_time` values on these recordings sit on the US cash close (`15:59:59` for NOK, `16:14:59` for SPX), so those are read as `America/New_York`. DTE is the calendar-day gap from that ET date to the OCC expiry.

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

`FixtureProvider` reads the normalized JSON schema. The SPY, SPX-style, non-standard, and missing-IV chains are synthetic: the expected GEX numbers are hand-calculated from the formula in `docs/METHODOLOGY.md`.

`CboeDelayedProvider` reads the CDN shape. The two `cboe_*_delayed.json` files are the recorded slices described above. Point the offline script at one of them. Do not pass `--network` in a test.

## Logging and secrets

`WEBULL_APP_KEY`, `WEBULL_APP_SECRET`, `MASSIVE_API_KEY`, `THETADATA_USERNAME`, `THETADATA_PASSWORD`, `TRADIER_TOKEN`, and `ALERT_WEBHOOK_URL` are redacted out of log lines when they are set in the environment. Empty values are left alone. Do not print secrets. Do not commit `.env`, token caches, or raw dumps that might contain account ids (see `.gitignore`).
