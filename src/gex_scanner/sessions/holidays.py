# SPDX-License-Identifier: Apache-2.0
"""US market closes used by the session clock.

Source: NYSE "Holidays & Trading Hours" page
https://www.nyse.com/markets/hours-calendars
fetched 2026-11-16. Columns used are 2026 and 2027. The page's early-close
footnotes say the cash markets close at 1:00 p.m. ET and eligible options
close at 1:15 p.m. ET on the dated days below.

Refresh this table from that page. Do not extend it from memory. Dates after
2027 are not in this table, so the clock does not treat them as holidays.
"""

from __future__ import annotations

from datetime import date

# Full closes. The ET calendar date is shut for RTH, curb, equity pre-market,
# and GTH. An evening that is still the previous ET date is not a holiday.
FULL_CLOSES: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 3, 26),
        date(2027, 5, 31),
        date(2027, 6, 18),
        date(2027, 7, 5),
        date(2027, 9, 6),
        date(2027, 11, 25),
        date(2027, 12, 24),
    }
)

# Early closes. Options stop at 1:15 p.m. ET. The NYSE footnotes do not list
# a curb session on these dates, so the clock does not open one.
EARLY_CLOSES: frozenset[date] = frozenset(
    {
        date(2026, 11, 27),
        date(2026, 12, 24),
        date(2027, 11, 26),
    }
)

# Eligible-options early close from the NYSE footnotes, in ET.
EARLY_OPTIONS_CLOSE_ET = (13, 15)
