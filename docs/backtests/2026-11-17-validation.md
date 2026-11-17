# Validation report, 2026-11-17

Window: 2025-05-17 through 2026-11-17, America/Chicago.
Out of sample: 2026-05-17 through 2026-11-17.
Follow-through clock: 120 minutes, same clock on cross days and other days.
A test passes only when the out-of-sample arm has at least 60 sessions
and clears the pre-registered margin. Otherwise the verdict is inconclusive
or fail. In-sample numbers cannot grant a pass.

Badge: unvalidated hypothesis.

## History actually available

Chain sessions with a level at time t and a later session path: 0.
Those sessions paired with OHLC: 0.

Cboe delayed quotes are a current snapshot, not an archive. This run did not call the CDN and did not treat a live quote as 18 months.
ThetaData and Massive were not called. MASSIVE_API_KEY set: False. THETADATA_USERNAME set: False. THETADATA_PASSWORD set: False.
No paid signup was started. No order was sent.

Synthetic fixture chains were excluded. They are hand-built engine inputs.
Excluded files: missing_iv.json, nonstandard_multiplier.json, spx_chain.json, spy_chain.json.

Parser slices in the repo, and why each one is not a test session:

- `tests/fixtures/recorded/cboe_nok_delayed.json` timestamp `2026-11-16 00:29:44` usable sessions 0. One Cboe delayed quote saved for the parser. The CDN is a current snapshot, not an archive, and this file has no later session path.
- `tests/fixtures/recorded/cboe_spx_delayed.json` timestamp `2026-11-15 22:25:08` usable sessions 0. One Cboe delayed quote saved for the parser. The CDN is a current snapshot, not an archive, and this file has no later session path.
- `tests/fixtures/recorded/webull_spy_chain.json` timestamp `2026-11-16T15:00:00Z` usable sessions 0. Redacted field example. Not an account capture and not a session path.

No chain archive is stored under data/.

## Tests

| Test | Verdict | Sample | In sample | Out of sample | Estimate | Baseline |
| --- | --- | --- | --- | --- | --- | --- |
| flip_rth | inconclusive | 0 | 0 | 0 | None | None |

out-of-sample arms are below 60 sessions

| wall_magnetism | inconclusive | 0 | 0 | 0 | None | None |

out-of-sample wall observations are below 60

| regime_range | inconclusive | 0 | 0 | 0 | None | None |

out-of-sample regime sample is below 120 sessions

| overnight | inconclusive | 0 | 0 | 0 | None | None |

out-of-sample overnight sessions are below 60

| walk_forward | inconclusive | 0 | 0 | 0 | None | None |

no sessions in the registered window

Tests passed: 0 of 5.
None of the five tests passed. The sample inside the window is zero, so the result is inconclusive, not a confirmation and not a rejection of the hypothesis.

The dashboard badge matches this report: unvalidated hypothesis.
