# Sessions

Display timezone and the question "what session is it now?" use `America/Chicago`. Exchange hours below are the ET hours from the project research note dated 2026-11-15, which cited Cboe's published GTH table and the 2026-10-19 extended-hours launch. This file does not add hours that note did not record.

DST does not change the ET-to-CT offset (ET is always one hour ahead of CT). It does change London and Asia local labels. Do not hardcode London or Tokyo clock times; compute session membership from the ET schedule in `America/Chicago`.

The session clock, early-close calendar, and futures basis are not implemented in this release. `gex_scanner.sessions` only holds the key list and the equity pre-market seed so the names stay stable. `local_asia` and `local_london` stay disabled until a non-US options adapter exists.

A later clock should label every snapshot and alert with the session key, local CT time, and ET time, and should carry a tested US equity/index early-close table for 2026–2027 taken from the published exchange calendar. This file does not invent that holiday list.

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

4. **Index versus futures.** A flip at a cash index level is not at that same number on the future. `futures_level = index_level + basis`. Basis is last RTH close basis, or live future minus cash when both exist. A later phase must persist the basis it used. Multipliers for ES and NQ (research note: ES is $50/point and NQ is $20/point) have to be checked against the current contract specs before a futures-options book is built. This release does not map futures.

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
