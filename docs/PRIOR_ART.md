# Prior art

Survey date: **2026-11-16**. Source: GitHub repository API (`GET /repos/{owner}/{repo}`) and repository search, via the connected GitHub account. Star counts and `pushed_at` are from that response, not from the 2026-11-15 research note. Push times are converted with `zoneinfo` `America/Chicago` (CDT, UTC−5, before 2026-11-01 07:00 UTC; CST, UTC−6, after that).

Searches, sorted by stars:

- `"gamma exposure" license:mit` (52 repositories; first page read)
- `gamma exposure GEX license:apache-2.0` (4 repositories; all read)
- `gex OR "gamma exposure" OR "dealer gamma" in:name license:mit` (272 hits; first page read, mostly unrelated "gex" name collisions)

No repository's source was copied. License files were opened only where noted. AGPL and unlicensed trees were not used as code.

## Decision

Reimplement the formulas in `docs/METHODOLOGY.md`. Do not vendor an existing engine in this phase.

The permissive projects below are useful as references for a later reader. They were not imported. `gammagrid` is AGPL-3.0 and stays read-only; its tree was not opened for this survey beyond the API license field. Repositories with no detected license were not opened for code.

`simonro/Edge-GEX-Lab` is the highest-star MIT project the `"gamma exposure"` search returned (67). Its description includes trade guidance. This product does not take trading instructions from another repo, and that tree was not read. `manfromnowhere143/gex-engine` (Apache-2.0, 0 stars) and `mervinj3546/gexkit` (Apache-2.0, 0 stars, Rust) showed up in the Apache search. Neither replaces the spec's Python engine. The gex-engine description claims 6,759 tests; that count was **not** checked by cloning or running the suite.

## Candidate repos from the product spec

| Repo | Stars | License (API) | Language | `pushed_at` (UTC) | America/Chicago | Use here |
| --- | --- | --- | --- | --- | --- | --- |
| [Matteo-Ferrara/gex-tracker](https://github.com/Matteo-Ferrara/gex-tracker) | 224 | none (`license: null`). Root listing has no `LICENSE` file (README, `_config.yml`, `data/`, `img/`, `main.py`, `requirements.txt`). | Python | 2023-04-08T11:29:42Z | 2023-04-08 6:29 AM CDT | Ideas only. No code copied. `main.py` was not read. |
| [gammagrid/gammagrid](https://github.com/gammagrid/gammagrid) | 102 | AGPL-3.0 | Python | 2026-11-15T11:29:08Z | 2026-11-15 5:29 AM CST | Not copied. |
| [zrack/gex-terminal](https://github.com/zrack/gex-terminal) | 27 | MIT | Python | 2026-11-15T18:24:00Z | 2026-11-15 12:24 PM CST | Not copied. |
| [FlashAlpha-lab/gex-explained](https://github.com/FlashAlpha-lab/gex-explained) | 18 | MIT | Python | 2026-11-06T14:59:18Z | 2026-11-06 8:59 AM CST | Not copied. |
| [GMestreM/gex_data](https://github.com/GMestreM/gex_data) | 12 | MIT | Python | 2026-08-03T08:38:49Z | 2026-08-03 3:38 AM CDT | Not copied. |
| [itsfabtrading/Gex-Multi](https://github.com/itsfabtrading/Gex-Multi) | 8 | Apache-2.0 | Python | 2026-08-04T23:35:12Z | 2026-08-04 6:35 PM CDT | Not copied. |
| [dhawalc/spx-gamma-levels](https://github.com/dhawalc/spx-gamma-levels) | 5 | GitHub SPDX `NOASSERTION` (`key: other`). The `LICENSE` file in the repo is **CC BY 4.0**, copyright 2026 SquawkFlow. That file was read to check the claim. | none reported | 2026-11-13T14:30:03Z | 2026-11-13 8:30 AM CST | Not copied. External level series, not an engine. |
| [eg-ethan/Gritli-Gamma-Exposure-Suite](https://github.com/eg-ethan/Gritli-Gamma-Exposure-Suite) | 3 | MIT | Go | 2026-10-15T21:29:12Z | 2026-10-15 4:29 PM CDT | Not copied. |
| [scottmcghee/gex-dashboard](https://github.com/scottmcghee/gex-dashboard) | 0 | MIT | Python | 2026-11-01T03:29:02Z | 2026-10-31 10:29 PM CDT | Not copied. The 2026-11-15 note converted this same UTC timestamp as Nov 1, 2026, 10:29 PM CT. `zoneinfo` places it on Oct 31. |
| [ZeFadi/gex-strat](https://github.com/ZeFadi/gex-strat) | 0 | Apache-2.0 | Python | 2026-10-20T19:16:16Z | 2026-10-20 2:16 PM CDT | Not copied. |

Star counts and licenses for these ten match the 2026-11-15 note, except the calendar-day conversion for `scottmcghee/gex-dashboard` above. No star count on this list moved between that note and this API read.

## Other repos the spec named

| Repo | Stars | License (API) | `pushed_at` in America/Chicago | Note |
| --- | --- | --- | --- | --- |
| [sgdividends/spx-dealer-gamma](https://github.com/sgdividends/spx-dealer-gamma) | 0 | none (`license: null`) | 2026-08-06 2:03 AM CDT | No license detected. Not opened. Not copied. |
| [NostroBenJ/gamma-research](https://github.com/NostroBenJ/gamma-research) | 0 | none (`license: null`) | 2026-09-16 12:31 PM CDT | No license detected. Not opened. Not copied. |
| [webull-inc/webull-openapi-skills](https://github.com/webull-inc/webull-openapi-skills) | 13 | Apache-2.0 | 2026-11-10 3:54 AM CST | Official skills repo. Not vendored. No Webull client in this phase. |
| [PatrickJS/awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules) | 41162 | CC0-1.0 | 2026-05-30 1:01 PM CDT | Cursor rules catalog, not a GEX engine. Not copied into this repo. |

## Permissive GEX projects the search added

These were not in the spec's short list. Metadata only. No source read. Not vendored.

| Repo | Stars | License | Language | America/Chicago push | Why it is listed |
| --- | --- | --- | --- | --- | --- |
| [simonro/Edge-GEX-Lab](https://github.com/simonro/Edge-GEX-Lab) | 67 | MIT | Python | 2026-11-09 2:46 AM CST | Highest-star MIT hit for `"gamma exposure"`. Description: local GEX map for SPY, QQQ, SPX, NDX, and stocks, including trade guidance. |
| [Darthreign/gex-dashboard](https://github.com/Darthreign/gex-dashboard) | 19 | MIT | Python | 2026-11-14 6:29 PM CST | Description: SPX/NDX gamma and delta dashboard on free Cboe delayed data. Distinct from `scottmcghee/gex-dashboard`. |
| [manfromnowhere143/gex-engine](https://github.com/manfromnowhere143/gex-engine) | 0 | Apache-2.0 | Python | 2026-08-01 6:26 AM CDT | Apache GEX library. Description claims 6,759 tests (unverified). One push on the creation day. |
| [mervinj3546/gexkit](https://github.com/mervinj3546/gexkit) | 0 | Apache-2.0 | Rust | 2026-10-25 5:37 PM CDT | Rust greeks and GEX library. This project stays on Python. |

`davidalmeida90/GEX-scalping-tradingbot` (MIT, 19 stars, pushed 2026-11-03T15:28:23Z) appeared in the name search. It is a trading bot. It is out of scope. Its source was not read.

Name collisions on the MIT name search (graph GEXF, Go expect libraries, game-engine exchange, and similar) are not GEX engines and are not listed row by row.
