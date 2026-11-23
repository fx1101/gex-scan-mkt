# Third-party notices

Original code in this repository is under the Apache License 2.0 (`LICENSE`), copyright 2026 Chris.

No third-party source file was copied into this tree. The GEX formula, sign convention, wall rules, and session tables were implemented from the project specification and are documented in `docs/METHODOLOGY.md`, `docs/SESSIONS.md`, and `docs/DATA_SOURCES.md`. They were not transcribed from another engine's source.

Survey date for the rows below: **2026-11-16**. Details and star counts are in `docs/PRIOR_ART.md`.

| Project | URL | License observed | Date accessed | Files or ideas used |
| --- | --- | --- | --- | --- |
| Matteo-Ferrara/gex-tracker | https://github.com/Matteo-Ferrara/gex-tracker | No license file (GitHub `license: null`). Root directory listed; no source file read. | 2026-11-16 | None. |
| gammagrid/gammagrid | https://github.com/gammagrid/gammagrid | AGPL-3.0 (GitHub API). Source not opened. | 2026-11-16 | None. |
| zrack/gex-terminal | https://github.com/zrack/gex-terminal | MIT (GitHub API). Source not opened. | 2026-11-16 | None. |
| FlashAlpha-lab/gex-explained | https://github.com/FlashAlpha-lab/gex-explained | MIT (GitHub API). Source not opened. | 2026-11-16 | None. |
| GMestreM/gex_data | https://github.com/GMestreM/gex_data | MIT (GitHub API). Source not opened. | 2026-11-16 | None. |
| itsfabtrading/Gex-Multi | https://github.com/itsfabtrading/Gex-Multi | Apache-2.0 (GitHub API). Source not opened. | 2026-11-16 | None. |
| dhawalc/spx-gamma-levels | https://github.com/dhawalc/spx-gamma-levels | CC BY 4.0 text in that repo's `LICENSE` (GitHub SPDX field is `NOASSERTION`). Only `LICENSE` was read. | 2026-11-16 | None. The dataset was not imported. |
| eg-ethan/Gritli-Gamma-Exposure-Suite | https://github.com/eg-ethan/Gritli-Gamma-Exposure-Suite | MIT (GitHub API). Source not opened. | 2026-11-16 | None. |
| scottmcghee/gex-dashboard | https://github.com/scottmcghee/gex-dashboard | MIT (GitHub API). Source not opened. | 2026-11-16 | None. |
| ZeFadi/gex-strat | https://github.com/ZeFadi/gex-strat | Apache-2.0 (GitHub API). Source not opened. | 2026-11-16 | None. |
| sgdividends/spx-dealer-gamma | https://github.com/sgdividends/spx-dealer-gamma | No detected license. Source not opened. | 2026-11-16 | None. |
| NostroBenJ/gamma-research | https://github.com/NostroBenJ/gamma-research | No detected license. Source not opened. | 2026-11-16 | None. |
| webull-inc/webull-openapi-skills | https://github.com/webull-inc/webull-openapi-skills | Apache-2.0 (GitHub API). Source not opened. | 2026-11-16 | None. |
| webull-inc/webull-openapi-python-sdk | https://github.com/webull-inc/webull-openapi-python-sdk | Apache-2.0. Request classes and the US region table were read on 2026-11-16. No file was copied. | 2026-11-16 | The dry run imports the installed package when sandbox keys are set. Field names used by the parser are the SDK's. |
| webull-inc/webull-openapi-mcp | https://github.com/webull-inc/webull-openapi-mcp | Apache-2.0. The option-contract and snapshot formatters were read on 2026-11-16. No file was copied. | 2026-11-16 | Response field names only. |
| PatrickJS/awesome-cursorrules | https://github.com/PatrickJS/awesome-cursorrules | CC0-1.0 (GitHub API). Source not opened. | 2026-11-16 | None. |
| simonro/Edge-GEX-Lab | https://github.com/simonro/Edge-GEX-Lab | MIT. Copyright 2026 Tape to Edge. GitHub SPDX `MIT`. | 2026-11-22 | None copied. A survey read the public tree at `3d851e7` (and an earlier search on 2026-11-16 did not open source). The Alpaca adapter in this repo was written against Alpaca's public Market Data docs and this project's `ChainSnapshot` types. No Edge-GEX-Lab file was copied, so the MIT notice is recorded here and is not attached to a copied file. |
| Darthreign/gex-dashboard | https://github.com/Darthreign/gex-dashboard | MIT (GitHub API). Source not opened. | 2026-11-16 | None. Recorded only as a search hit. |
| manfromnowhere143/gex-engine | https://github.com/manfromnowhere143/gex-engine | Apache-2.0 (GitHub API). Source not opened. | 2026-11-16 | None. Recorded only as a search hit. |
| mervinj3546/gexkit | https://github.com/mervinj3546/gexkit | Apache-2.0 (GitHub API). Source not opened. | 2026-11-16 | None. Recorded only as a search hit. |

The Apache License 2.0 text in `LICENSE` is the standard license for this project's original code. It was not taken from `Gex-Multi` or from `gex-engine`.

Vendor documentation links in `docs/DATA_SOURCES.md` are citations. No vendor SDK is vendored in this release. The Webull dry run imports `webull-openapi-python-sdk` from the environment when sandbox keys are present. That package is not a dependency of `pytest`.
