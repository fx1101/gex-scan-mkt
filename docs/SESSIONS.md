# Sessions

Display timezone and the question "what session is it now?" use `America/Chicago`. The session windows below are the ET hours from the project research note dated 2026-11-15, which cited Cboe's published GTH table and the 2026-10-19 extended-hours launch. The 2026–2027 holiday and early-close table is the only schedule added after that note, and it is sourced to the NYSE page dated in the clock section.

DST does not change the ET-to-CT offset (ET is always one hour ahead of CT). It does change London and Asia local labels. Do not hardcode London or Tokyo clock times; compute session membership from the ET schedule in `America/Chicago`.

`gex_scanner.sessions.session_at` is the clock. It converts the ET windows below with `zoneinfo` (`America/Chicago` for the label, `America/New_York` for the exchange schedule). A trading session outranks a watch session. `local_asia` and `local_london` stay disabled until a non-US options adapter exists.

Ends are exclusive. The open instant is inside the session; the published end instant is not.

On an early-close date the options session ends at 1:15 p.m. ET. That time, and the full-close dates, come from the NYSE Holidays & Trading Hours page fetched 2026-11-16 (https://www.nyse.com/markets/hours-calendars), not from the 2026-11-15 research note. The footnotes on that page give 1:00 p.m. ET for the cash markets and 1:15 p.m. ET for eligible options. They do not list a curb on those dates, so this clock does not open `us_curb` then. A full-close ET date suppresses RTH, curb, equity pre-market, and GTH. Refresh `src/gex_scanner/sessions/holidays.py` from that page when the next calendar is published. Do not extend it from memory. Dates after 2027 are not in the table.

`asia_watch` is 09:00–15:00 `Asia/Tokyo` on a Tokyo weekday. `london_watch` is 08:00–16:30 `Europe/London` on a London weekday. Those are clock hours. This tree has no JPX or LSE holiday calendar. During either watch the label says to reuse the last valid US GEX map. It does not call that a live options book.

SPY and QQQ use the 4:15 p.m. ET RTH close named in the research note. Other names on the 2026-10-19 list use a 4:00 p.m. ET RTH close and a 4:00–4:15 p.m. ET post window (`us_curb`). NDX uses the index RTH close and is not treated as GTH.

Cash/futures basis is `futures_level = index_level + basis`, with `basis = future - cash`. The stored record keeps the method (`last_rth_close` or `live_future_minus_cash`). Pairs are SPX/ES, NDX/NQ, and RUT/RTY. No other pair is mapped.

## Sample labels

| Instant (America/Chicago) | Underlying | Key |
| --- | --- | --- |
| 2026-11-16 08:30 | SPX | `us_rth` |
| 2026-11-15 19:15 | SPX | `us_gth_index` |
| 2026-11-15 19:15 | SPY | `asia_watch` |
| 2026-11-16 06:30 | SPY | `us_equity_pre` |
| 2026-01-15 00:00 | SPY | none (CST midnight is 15:00 JST, the end of the Tokyo window) |
| 2026-07-15 00:00 | SPY | `asia_watch` (CDT midnight is 14:00 JST) |
| 2026-03-08 01:30 and 03:30 | SPX | none (Sunday morning; 02:30 CT is the same instant as 03:30 CDT) |
| 2026-03-08 19:15 | SPX | `us_gth_index` (Sunday open after the spring-forward) |
| 2026-03-16 02:30 | SPY | not `london_watch` (US is on CDT, UK is still on GMT) |
| 2026-03-16 03:00 | SPY | `london_watch` |
| 2026-11-01 01:30, both folds | SPX | none (Sunday morning; the folds are one hour apart and share a label) |
| 2026-11-01 19:15 | SPX | `us_gth_index` |
| 2026-11-27 12:14 | SPX | `us_rth` (early close still open) |
| 2026-11-27 12:15 | SPX | not `us_rth` (1:15 p.m. ET options close) |

## What actually trades

US equity and ETF options are not a 24-hour book. "Asia" and "London" in v1 mean: keep the last valid US GEX map and compare overnight futures with it. They do not mean a live SPY options book during the Tokyo or London cash session.

1. **US index options with GTH (nearly 24×5).** The Cboe Global Trading Hours product list opened for the 2026-11-15 research lists **SPX, XSP, VIX, and RUT**. That list did not include NDX. Treat NDX options as RTH-primary unless a later official Cboe page says otherwise. Overnight Nasdaq exposure can still be watched with NQ futures, mapped from NDX or QQQ.

   | Session | New York (ET) | Chicago (CT) |
   | --- | --- | --- |
   | Global Trading Hours (GTH) | 8:15 PM – 9:25 AM | 7:15 PM – 8:25 AM |
   | Regular Trading Hours (RTH) | 9:30 AM – 4:15 PM | 8:30 AM – 3:15 PM |
   | Curb | 4:15 PM – 5:00 PM | 3:15 PM – 4:00 PM |

   GTH opens Sunday evening (8:15 PM ET / 7:15 PM CT), which is Monday morning in Asia-Pacific.

2. **Equity and ETF options.** The same research note records ordinary equity RTH as 9:30 AM–4:00 PM ET, and RTH until 4:15 PM ET for select designated ETFs/ETNs, including names such as SPY and QQQ. On 2026-10-19, Cboe launched pre-market and post-market sessions for a published list of 24 single stocks and 5 ETFs, not the whole options universe. Hours from that note: **7:30 AM – 9:25 AM ET pre-market (6:30–8:25 AM CT)** and **4:00–4:15 PM ET post-market (3:00–3:15 PM CT)**. That pre-market window does not cover the Asia overnight session.

3. **Open interest** is mostly a once-a-day official number (OCC / prior session). Intraday and overnight GEX changes come from spot, IV, and greeks, plus GTH trading in products that actually trade. Do not treat OI as ticking with every print.

4. **Index versus futures.** A flip at a cash index level is not at that same number on the future. `futures_level = index_level + basis`. Basis is last RTH close basis, or live future minus cash when both exist. The scanner stores that basis with the snapshot, and replay uses the stored number. Pairs are SPX/ES, NDX/NQ, and RUT/RTY. Multipliers for ES and NQ (research note: ES is $50/point and NQ is $20/point) have to be checked against the current contract specs before a futures-options book is built. This release does not build that futures-options book.

## Session keys

| Key | Window to implement (CT) | What the scanner should use |
| --- | --- | --- |
| `us_rth` | 8:30 AM – 3:15 PM CT for the index / designated-ETF close in the research table | Live or delayed US chains. Full GEX, walls, flip, 0DTE, once those pieces exist. |
| `us_curb` | Index 3:15–4:00 PM CT. Equity/ETF 3:00–3:15 PM CT where that post-market window applies. | Same book. Mark the session as curb. Names that are not in GTH are done. |
| `us_gth_index` | 7:15 PM – 8:25 AM CT, including the Sunday-evening open | SPX, XSP, VIX, RUT when the data entitlement covers them. Map levels onto ES, NQ, and RTY only after basis exists. |
| `us_equity_pre` | 6:30–8:25 AM CT, and only the names in the 2026-10-19 list | Optional pre-market refresh for that list. |
| `asia_watch` | About Tokyo cash 6:00 PM–12:00 AM CT while the US is on CST, and 7:00 PM–1:00 AM CT while the US is on CDT (9:00–15:00 JST). Recompute the local label when DST changes. | Watch ES, NQ, and RTY against the last valid US GEX map. Do not describe this as a live SPY options book. |
| `london_watch` | About 2:00–10:30 AM CT when LSE 8:00–16:30 UK lines up in winter. Recompute around DST changes. | Same idea: futures versus the US GEX map. The window overlaps US GTH and then the US cash open. |
| `local_asia` | Exchange hours of JPX / OSE once an adapter exists | Disabled. |
| `local_london` | Exchange hours of LSE/ICE and Eurex once an adapter exists | Disabled. |

During `asia_watch` and `london_watch` the intended default is: reuse the last valid US GEX map, update the futures mark (ES, NQ, RTY), re-express walls and the flip in futures points with the stored basis, and score distance from the future to those levels. Optionally refresh SPX, XSP, VIX, or RUT greeks when a GTH-capable live adapter is entitled. Never describe a stale SPY regular-hours chain as live Asia options GEX.

Do not build an "Asia GEX" book from SPY open interest. A separate CME futures-options book, or a local Nikkei / FTSE / DAX book, is a later adapter and is not this map.

## Equity pre-market seed (Cboe list dated 2026-10-19)

AAPL, AMD, AMZN, AVGO, BABA, BAC, F, GLD, GOOG, GOOGL, HOOD, INTC, IWM, META, MRVL, MSFT, MU, NFLX, NOK, NVDA, ORCL, PFE, PLTR, QQQ, SNDK, SPY, TSLA, TSM, XLF.

The research note calls this 24 single stocks and 5 ETFs. The five ETF/ETN names in that list are GLD, IWM, QQQ, SPY, and XLF. The code constant `EQUITY_PREMARKET_UNDERLYINGS` is this list and nothing else.
