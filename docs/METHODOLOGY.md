# Methodology

This file is the normative description of the GEX math. The implementation follows it. Where a later phase owns a section, that section is specified here and is not computed yet.

**Status of this release**

| Section | Status |
| --- | --- |
| Per-contract dollar GEX | Implemented |
| Dealer sign | Implemented |
| Strikes, walls, expiry filters, 0DTE share | Implemented |
| Quality rules | Implemented |
| Zero-gamma / flip by repricing | Specified only. Not implemented. |
| Vanna / charm | Specified only. `enable_second_order` defaults off and refuses `true`. |
| Pre-registered historical tests | Specified only. Not implemented. No history is fabricated. |

The engine is a pure function of a `ChainSnapshot` and an `EngineConfig`. It does not call a network, a vendor, or a language model.

Every result carries this sentence, with the active convention name filled in:

> Estimated dealer GEX under the [name] sign convention. Not actual market-maker positions.

The unit on every result is **USD of estimated dealer delta change per 1% move**. Charts and tables in later phases must keep that label. The engine does not switch to gamma-shares or per-$1 units.

## 1. Per-contract dollar GEX

For each contract with usable gamma and open interest:

```
gex_unsigned = abs(gamma) * OI * multiplier * spot^2 * 0.01
```

- `gamma` is the option's gamma per 1 currency unit of the underlying, per share (or per index point). If a vendor sends a signed put gamma, the engine takes `abs(gamma)` and applies the dealer sign separately.
- `OI` is open interest in contracts.
- `multiplier` is the contract field. The engine never replaces it with 100. Equity, ETF, and standard SPX contracts are often 100; XSP, minis, corporate-action deliverables, and futures options have to be confirmed from the contract record when a live adapter exists. Phase 1 fixtures set the multiplier explicitly.
- `spot` is the snapshot's official reference. Fixtures name the field in `spot_field` (the samples use `official_mark`). The same spot is used for every contract in that snapshot.
- `spot^2 * 0.01` turns a per-$1 delta change into dollars of delta per 1% move, because `spot^2 * 0.01 = spot * (0.01 * spot)`.

Acceptance tests compare engine output to expected numbers stored in the fixture JSON. The tolerance is 1 USD of this unit.

## 2. Dealer sign

Default public convention:

- Calls contribute `+gex_unsigned` (modeled as dealer-long call gamma).
- Puts contribute `-gex_unsigned` (modeled as dealer-short put gamma).

This is a modeling assumption, not observed inventory. Single-name books with heavy overwriting or structured-product flow can differ.

`dealer_sign` is one of:

| Value | Effect |
| --- | --- |
| `call_pos_put_neg` | Default. Calls positive, puts negative. |
| `dealers_short_both` | Both rights negative. Research only. |
| `flow_signed` | Uses the contract's `flow_sign` of `+1` (dealer long gamma) or `-1` (dealer short gamma). If that field is missing, the contract is excluded and flagged `missing_flow_sign`. Volume is never used as a sign. |

Net GEX at the snapshot spot is the sum of signed contract GEX inside the active expiry filter.

Switching a book of identical calls from `call_pos_put_neg` to `dealers_short_both` negates net GEX. A call and a put with equal unsigned GEX (a symmetric straddle) net to about zero under the default and to `-2 * unsigned` under `dealers_short_both`. Puts are negative under both of those conventions; only the call leg flips between them.

## 3. Aggregation, walls, and expiry filters

**Per-strike net GEX** is the sum of signed GEX of the contracts at that strike that passed quality rules and the active expiry filter.

Side totals used for walls are unsigned:

- **Call wall:** the strike with the largest unsigned call GEX. A zero call total is not a wall.
- **Put wall:** the strike with the largest unsigned put GEX (the absolute put contribution). A zero put total is not a wall.
- **Gross magnet:** the strike with the largest gross GEX, `unsigned call + unsigned put` at that strike. It is gross gamma, not a forecast.

Walls are not moved to sit on a chosen side of spot. If both walls are above spot, or both are below, the result says so. On an exact tie, the strike closer to spot wins; if the distances match, the lower strike wins.

`spot_side` on a wall is `above`, `below`, or `at`.

**Expiry filters**

| Filter | Rule |
| --- | --- |
| `all` | Every quality-eligible contract, including DTE 0. 0DTE is not dropped. |
| `0dte` | `dte == 0`, using the DTE on the contract. Phase 1 does not recompute DTE from a clock. |
| `lte_7d` | `dte <= 7`, which includes 0. |
| `lte_30d` | `dte <= 30`, which includes 0. |
| `monthly` | `expiry_kind == "monthly"` when that field is set. Otherwise the expiry date is the third Friday of its month. An explicit `weekly` stays weekly even on a third Friday. |
| `custom` | The configured expiry dates, the configured DTE bounds, or the intersection when both are set. |

The default aggregation is an unweighted sum. 0DTE is not scaled by `1/sqrt(T)` or any other decay.

**0DTE share** is a report, not a weight. It is computed on the quality-eligible book *before* the expiry filter, so the share does not change just because the view is already `0dte`.

- `zero_dte_abs_net_share = abs(signed net of DTE 0) / abs(signed net of the eligible book)`, or null when the eligible net is 0.
- `zero_dte_gross_share = unsigned GEX of DTE 0 / unsigned GEX of the eligible book`, or null when the eligible gross is 0.

`net_gex` on the result is the active view, after the filter.

## 4. Zero-gamma / flip (not implemented)

Do not define the flip as the listed strike whose net GEX is closest to zero.

When this is built, compute it by repricing:

1. For each included contract with a usable IV, recompute Black-Scholes / Merton gamma on a grid of hypothetical spots. Default band: document the chosen span inside ±10% to ±15% around the current spot, with a step fine enough to interpolate.
2. Hold each contract's IV, strike, rate, dividend or yield (or implied forward), and time-to-expiry fixed at the snapshot. Document the rate (a named convention such as SOFR, or a config constant) and the day-count for T. If vendor gamma at the current spot disagrees with Black-Scholes gamma by more than a stated tolerance, keep the vendor gamma at the current spot, use Black-Scholes only off spot, and record the residual.
3. At each hypothetical spot S, recompute signed GEX using that S both in gamma and in the `S^2 * 0.01` scale. Do not mix a gamma computed at S with a scale computed at the original spot.
4. The flip is the interpolated S where net GEX crosses zero. Return every in-band crossing. Mark the crossing nearest the snapshot spot as `primary_flip`. If net GEX does not cross inside the band, say so. Do not invent a flip.
5. At the observed spot, the curve must agree with current-spot net GEX within a documented tolerance.

No flip function is exported in this release.

## 5. Vanna and charm (not implemented)

`enable_second_order` defaults to false. Setting it true raises. A later phase may add closed-form Black-Scholes-Merton vanna and charm, scaled in the same module as GEX, under the same dealer-sign assumption, and only when tests exist. This release does not show vanna or charm levels.

## 6. Quality rules

Implemented flags:

| Flag | Effect |
| --- | --- |
| `missing_oi` | Excluded. Missing open interest is not treated as zero. |
| `invalid_oi` | Excluded. Negative open interest. |
| `zero_oi` | Excluded unless `include_zero_oi` is on. When included, the flag remains and GEX is arithmetically zero. |
| `missing_gamma` | Excluded. The contract is not inserted as a zero-gamma row. |
| `missing_iv` | Warning. The contract stays in the sum when gamma and OI are usable. IV is not filled with zero. |
| `zero_iv` | Warning. IV was supplied as 0. GEX still uses vendor gamma. |
| `non_standard_multiplier`, `non_standard_deliverable`, `non_standard` | Excluded from the default scan and listed in the quality appendix. `include_nonstandard` puts them back, still using the contract multiplier. |
| `missing_flow_sign` | Excluded, and only when `dealer_sign` is `flow_signed`. |
| `invalid_multiplier` | Excluded. Multiplier must be positive. It is not replaced. |
| `invalid_dte` | Excluded. Negative DTE. |
| `stale_quote` | Warning. Kept when the provider sets it. Also set when `stale_quote_seconds` is configured and the quote is older than that. The default config does not invent a staleness horizon. |

Official open interest is typically the prior session. A later logger should attribute intraday GEX changes to spot, IV, and greeks, not to a ticking OI print. This release does not have a live feed.

## 7. Pre-registered tests (not implemented)

These tests are the bar for trusting a level. They are not coded, and this release has no historical sample. Defaults, when they are written, should be conservative and should not pass on noise. Until a dated report exists, any later dashboard must keep an unvalidated-hypothesis badge.

Levels at time t may use only data available at t (prior official OI, then-current quotes). Out-of-sample results are reported separately. No peeking.

1. **Flip test (RTH).** When price starts the cash session on one side of the primary flip and then crosses it, compare realized range or directional follow-through over the next N minutes or hours with days that do not cross. Report hit rate, average move, and a same-time-of-day unconditional baseline.
2. **Wall magnetism vs break.** How often session price touches versus breaks the put wall and the call wall, with MFE/MAE.
3. **Regime vs realized range.** Absolute session range and realized vol on days with clearly positive versus clearly negative net GEX, and 0DTE-heavy versus not, controlling for VIX or ATM IV when that series exists.
4. **Overnight / session tests.** During `asia_watch` and `london_watch`, test whether prior-close (or last GTH) SPX levels, mapped to ES, have a statistical relationship with the overnight ES path. Compare with a no-GEX baseline.
5. **Walk-forward.** The split above.

Output, when it exists: sample size, period, and pass/fail against thresholds Chris sets. An inconclusive result stays inconclusive.

History has to be collected going forward from Cboe delayed snapshots, or imported later from a vendor Chris entitles (ThetaData and Massive are the realistic history sources named in the research note). This repository does not ship a fake history.
