# SPDX-License-Identifier: Apache-2.0
"""Pre-registered GEX checks. This module does not fetch or invent history.

Chris fixed the window at 2025-05-17 through 2026-11-17, America/Chicago.
The last six months, from 2026-05-17, are out of sample. A test can pass
only on that out-of-sample slice, and only after each arm has 60 sessions.
A smaller sample stays inconclusive. In-sample results are reported and
cannot grant a pass. Levels must be timestamped at or before the window
opens. There is no order placement.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
WINDOW_START = date(2025, 5, 17)
WINDOW_END = date(2026, 11, 17)
OOS_START = date(2026, 5, 17)
MIN_ARM = 60
MIN_EXCESS = 0.002
MIN_T = 2.0
MIN_HIT_RATE = 0.60
MIN_TOUCH_GAP = 0.10
MIN_ABS_CORR = 0.25
ZERO_DTE_HEAVY = 0.5
FOLLOW_THROUGH_MINUTES = 120
UNVALIDATED = "unvalidated hypothesis"
VALIDATED = "validated"
REPORT_NAME = "2026-11-17-validation"


class PeekError(ValueError):
    """A level is timestamped after the session window opened."""


@dataclass(frozen=True)
class Thresholds:
    min_arm: int = MIN_ARM
    min_excess: float = MIN_EXCESS
    min_t: float = MIN_T
    min_hit_rate: float = MIN_HIT_RATE
    min_touch_gap: float = MIN_TOUCH_GAP
    min_abs_corr: float = MIN_ABS_CORR


@dataclass(frozen=True)
class SessionRecord:
    """One session. Prices are the underlying or the mapped future, not a mix.

    ``follow_through`` is the signed return over the pre-registered 120
    minutes, measured from the same clock on cross days and no-cross days.
    ``cross_sign`` is +1 when price crosses the flip upward, -1 downward.
    """

    symbol: str
    session_date: date
    session_kind: str
    level_time: datetime
    window_start: datetime
    flip: float | None = None
    call_wall: float | None = None
    put_wall: float | None = None
    net_gex: float | None = None
    zero_dte_gross_share: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    crossed_flip: bool | None = None
    cross_sign: int | None = None
    follow_through: float | None = None
    vix_or_atm_iv: float | None = None
    mapped_flip: float | None = None
    future_start: float | None = None
    future_end: float | None = None

    def __post_init__(self) -> None:
        for stamp in (self.level_time, self.window_start):
            if stamp.tzinfo is None:
                raise ValueError("session timestamps must be timezone-aware")
        if self.level_time > self.window_start:
            raise PeekError(f"{self.symbol} {self.session_date} level is after the window opened")


@dataclass(frozen=True)
class TestResult:
    name: str
    verdict: str
    sample_size: int
    in_sample_size: int
    out_of_sample_size: int
    estimate: float | None
    baseline: float | None
    detail: str

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    center = mean(values)
    var = sum((item - center) ** 2 for item in values) / (len(values) - 1)
    return var**0.5


def _stderr(values: list[float]) -> float | None:
    sigma = _std(values)
    if sigma is None:
        return None
    return sigma / len(values) ** 0.5


def _t_diff(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(right) < 2:
        return None
    se_left = _stderr(left)
    se_right = _stderr(right)
    if se_left is None or se_right is None:
        return None
    denom = (se_left**2 + se_right**2) ** 0.5
    gap = mean(left) - mean(right)
    if denom == 0:
        return None if gap == 0 else float("inf")
    return gap / denom


def _corr(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or len(xs) != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _corr_t(r: float, n: int) -> float | None:
    if n < 3 or abs(r) >= 1:
        return None if abs(r) < 1 else float("inf")
    return r * (n - 2) ** 0.5 / (1 - r * r) ** 0.5


def _in_window(record: SessionRecord) -> bool:
    return WINDOW_START <= record.session_date <= WINDOW_END


def split_walk_forward(
    records: list[SessionRecord],
) -> tuple[list[SessionRecord], list[SessionRecord]]:
    """In-sample is before 2026-05-17. That date and after are out of sample."""

    inside = [record for record in records if _in_window(record)]
    ins = [record for record in inside if record.session_date < OOS_START]
    oos = [record for record in inside if record.session_date >= OOS_START]
    return ins, oos


def _short(n_left: int, n_right: int, thresholds: Thresholds) -> bool:
    return n_left < thresholds.min_arm or n_right < thresholds.min_arm


def flip_test(records: list[SessionRecord], thresholds: Thresholds | None = None) -> TestResult:
    """Cross days versus the same-clock unconditional follow-through."""

    thresholds = thresholds or Thresholds()
    usable = [
        record
        for record in records
        if record.session_kind == "us_rth"
        and record.crossed_flip is not None
        and record.follow_through is not None
        and _in_window(record)
    ]
    ins, oos = split_walk_forward(usable)
    crosses = [record for record in oos if record.crossed_flip]
    quiet = [record for record in oos if not record.crossed_flip]
    if _short(len(crosses), len(quiet), thresholds):
        return _result(
            "flip_rth",
            "inconclusive",
            usable,
            ins,
            oos,
            None,
            None,
            "out-of-sample arms are below 60 sessions",
        )
    cross_moves = [record.follow_through for record in crosses if record.follow_through is not None]
    all_moves = [record.follow_through for record in oos if record.follow_through is not None]
    baseline = mean(all_moves)
    estimate = mean(cross_moves)
    excess = estimate - baseline
    t_stat = _t_diff(cross_moves, [record.follow_through or 0.0 for record in quiet])
    directed = [
        record
        for record in crosses
        if record.cross_sign in (1, -1) and record.follow_through is not None
    ]
    if directed:
        hits = sum(
            1
            for record in directed
            if record.follow_through is not None
            and record.cross_sign is not None
            and record.follow_through * record.cross_sign > 0
        )
        hit_rate = hits / len(directed)
    else:
        hit_rate = None
    passed = (
        abs(excess) >= thresholds.min_excess
        and t_stat is not None
        and abs(t_stat) >= thresholds.min_t
        and hit_rate is not None
        and hit_rate >= thresholds.min_hit_rate
    )
    verdict = "pass" if passed else "fail"
    detail = (
        f"oos cross n={len(crosses)} quiet n={len(quiet)} "
        f"mean follow-through={estimate:.6f} unconditional={baseline:.6f} "
        f"hit_rate={hit_rate}"
    )
    return _result("flip_rth", verdict, usable, ins, oos, estimate, baseline, detail)


def _touched(wall: float, high: float, low: float) -> bool:
    return low <= wall <= high


def _broke(side: str, wall: float, close: float) -> bool:
    if side == "call":
        return close > wall
    return close < wall


def wall_test(records: list[SessionRecord], thresholds: Thresholds | None = None) -> TestResult:
    """How often RTH price touches a wall without closing through it."""

    thresholds = thresholds or Thresholds()
    rows: list[tuple[SessionRecord, str, float]] = []
    for record in records:
        if record.session_kind != "us_rth" or not _in_window(record):
            continue
        if None in (record.high, record.low, record.close, record.open):
            continue
        if record.call_wall is not None:
            rows.append((record, "call", record.call_wall))
        if record.put_wall is not None:
            rows.append((record, "put", record.put_wall))
    ins_rows = [item for item in rows if item[0].session_date < OOS_START]
    oos_rows = [item for item in rows if item[0].session_date >= OOS_START]
    if len(oos_rows) < thresholds.min_arm:
        return _result(
            "wall_magnetism",
            "inconclusive",
            rows,
            ins_rows,
            oos_rows,
            None,
            None,
            "out-of-sample wall observations are below 60",
        )
    touches = 0
    breaks = 0
    mfes: list[float] = []
    maes: list[float] = []
    for record, side, wall in oos_rows:
        assert record.high is not None and record.low is not None
        assert record.close is not None and record.open is not None
        touched = _touched(wall, record.high, record.low)
        broke = touched and _broke(side, wall, record.close)
        if touched and not broke:
            touches += 1
        if broke:
            breaks += 1
        if side == "call":
            mfes.append(record.high - record.open)
            maes.append(record.open - record.low)
        else:
            mfes.append(record.open - record.low)
            maes.append(record.high - record.open)
    n = len(oos_rows)
    touch_rate = touches / n
    break_rate = breaks / n
    gap = touch_rate - break_rate
    estimate = gap
    baseline = break_rate
    verdict = "pass" if gap >= thresholds.min_touch_gap else "fail"
    detail = (
        f"oos n={n} touch_without_break={touch_rate:.4f} "
        f"break={break_rate:.4f} mean_mfe={mean(mfes):.4f} mean_mae={mean(maes):.4f}"
    )
    return _result("wall_magnetism", verdict, rows, ins_rows, oos_rows, estimate, baseline, detail)


def regime_test(records: list[SessionRecord], thresholds: Thresholds | None = None) -> TestResult:
    """Session range on clearly positive versus clearly negative net GEX."""

    thresholds = thresholds or Thresholds()
    usable = [
        record
        for record in records
        if record.session_kind == "us_rth"
        and record.net_gex is not None
        and record.high is not None
        and record.low is not None
        and record.open not in (None, 0)
        and _in_window(record)
    ]
    ins, oos = split_walk_forward(usable)
    if len(oos) < thresholds.min_arm * 2:
        return _result(
            "regime_range",
            "inconclusive",
            usable,
            ins,
            oos,
            None,
            None,
            "out-of-sample regime sample is below 120 sessions",
        )
    scale = sorted(abs(record.net_gex or 0.0) for record in oos)
    cutoff = scale[len(scale) // 2]
    positive = [record for record in oos if (record.net_gex or 0) > cutoff]
    negative = [record for record in oos if (record.net_gex or 0) < -cutoff]
    if _short(len(positive), len(negative), thresholds):
        return _result(
            "regime_range",
            "inconclusive",
            usable,
            ins,
            oos,
            None,
            None,
            "clear positive and negative arms are below 60",
        )
    if any(record.vix_or_atm_iv is None for record in oos):
        return _result(
            "regime_range",
            "inconclusive",
            usable,
            ins,
            oos,
            None,
            None,
            "VIX or ATM IV is missing, so the range is not controlled",
        )

    def _range(record: SessionRecord) -> float:
        assert record.high is not None and record.low is not None and record.open
        return (record.high - record.low) / record.open

    pos_raw = [_range(record) for record in positive]
    neg_raw = [_range(record) for record in negative]
    pos_iv = [record.vix_or_atm_iv or 0.0 for record in positive]
    neg_iv = [record.vix_or_atm_iv or 0.0 for record in negative]
    # Fit the control on the in-sample rows only, then apply that line out of sample.
    fit_rows = [record for record in ins if record.vix_or_atm_iv is not None and record.open]
    if len(fit_rows) < 3:
        return _result(
            "regime_range",
            "inconclusive",
            usable,
            ins,
            oos,
            None,
            None,
            "in-sample control fit has fewer than 3 sessions",
        )
    fit_x = [record.vix_or_atm_iv or 0.0 for record in fit_rows]
    fit_y = [_range(record) for record in fit_rows]
    mx, my = mean(fit_x), mean(fit_y)
    var = sum((item - mx) ** 2 for item in fit_x)
    if var == 0:
        slope = 0.0
    else:
        slope = sum((x - mx) * (y - my) for x, y in zip(fit_x, fit_y, strict=True)) / var
    intercept = my - slope * mx
    pos = [y - (intercept + slope * x) for x, y in zip(pos_iv, pos_raw, strict=True)]
    neg = [y - (intercept + slope * x) for x, y in zip(neg_iv, neg_raw, strict=True)]
    # Positive GEX is hypothesized to dampen, so its residual range should be smaller.
    t_stat = _t_diff(neg, pos)
    estimate = mean(pos)
    baseline = mean(neg)
    heavy = [record for record in oos if (record.zero_dte_gross_share or 0) >= ZERO_DTE_HEAVY]
    light = [record for record in oos if (record.zero_dte_gross_share or 0) < ZERO_DTE_HEAVY]
    passed = (
        t_stat is not None
        and t_stat >= thresholds.min_t
        and len(heavy) >= thresholds.min_arm
        and len(light) >= thresholds.min_arm
    )
    verdict = "pass" if passed else "fail"
    detail = (
        f"oos positive n={len(positive)} negative n={len(negative)} "
        f"residual range pos={estimate:.6f} neg={baseline:.6f} "
        f"zero_dte_heavy n={len(heavy)} light n={len(light)}"
    )
    return _result("regime_range", verdict, usable, ins, oos, estimate, baseline, detail)


def overnight_test(
    records: list[SessionRecord],
    thresholds: Thresholds | None = None,
) -> TestResult:
    """Mapped flip versus the overnight future path, against the unconditional mean."""

    thresholds = thresholds or Thresholds()
    usable = [
        record
        for record in records
        if record.session_kind in {"asia_watch", "london_watch"}
        and record.mapped_flip is not None
        and record.future_start not in (None, 0)
        and record.future_end is not None
        and _in_window(record)
    ]
    ins, oos = split_walk_forward(usable)
    if len(oos) < thresholds.min_arm:
        return _result(
            "overnight",
            "inconclusive",
            usable,
            ins,
            oos,
            None,
            None,
            "out-of-sample overnight sessions are below 60",
        )
    distance = []
    for record in oos:
        start = record.future_start or 1.0
        distance.append(((record.future_start or 0.0) - (record.mapped_flip or 0.0)) / start)
    returns = [(record.future_end or 0) / (record.future_start or 1) - 1 for record in oos]
    baseline = mean(returns)
    corr = _corr(distance, returns)
    t_stat = None if corr is None else _corr_t(corr, len(oos))
    passed = (
        corr is not None
        and abs(corr) >= thresholds.min_abs_corr
        and t_stat is not None
        and abs(t_stat) >= thresholds.min_t
    )
    verdict = "pass" if passed else "fail"
    detail = (
        f"oos n={len(oos)} corr={corr} unconditional_mean={baseline:.6f} "
        "no-GEX baseline is that unconditional mean"
    )
    return _result("overnight", verdict, usable, ins, oos, corr, baseline, detail)


def walk_forward(records: list[SessionRecord], others: list[TestResult]) -> TestResult:
    """The split itself. A pass requires the other four to pass on no-peek data."""

    inside = [record for record in records if _in_window(record)]
    ins, oos = split_walk_forward(records)
    if not inside:
        return _result(
            "walk_forward",
            "inconclusive",
            inside,
            ins,
            oos,
            None,
            None,
            "no sessions in the registered window",
        )
    if all(item.passed for item in others):
        verdict = "pass"
        detail = "out-of-sample slice cleared the other four tests"
    elif any(item.verdict == "inconclusive" for item in others):
        verdict = "inconclusive"
        detail = "at least one test is inconclusive, so the split grants nothing"
    else:
        verdict = "fail"
        detail = "the out-of-sample slice did not clear every test"
    return _result("walk_forward", verdict, inside, ins, oos, None, None, detail)


def _result(
    name: str,
    verdict: str,
    usable: list,
    ins: list,
    oos: list,
    estimate: float | None,
    baseline: float | None,
    detail: str,
) -> TestResult:
    return TestResult(
        name=name,
        verdict=verdict,
        sample_size=len(usable),
        in_sample_size=len(ins),
        out_of_sample_size=len(oos),
        estimate=estimate,
        baseline=baseline,
        detail=detail,
    )


def run_preregistered(
    records: list[SessionRecord],
    thresholds: Thresholds | None = None,
) -> list[TestResult]:
    """Run the five checks. Records that peek are rejected by SessionRecord."""

    thresholds = thresholds or Thresholds()
    others = [
        flip_test(records, thresholds),
        wall_test(records, thresholds),
        regime_test(records, thresholds),
        overnight_test(records, thresholds),
    ]
    return [*others, walk_forward(records, others)]


def badge_for(results: list[TestResult]) -> str:
    if results and all(item.passed for item in results):
        return VALIDATED
    return UNVALIDATED


def _key_set(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def inventory_history(root: Path) -> dict:
    """Count real chain sessions. Synthetic fixtures and parser slices are not sessions."""

    recorded: list[dict[str, str]] = []
    recorded_dir = root / "tests" / "fixtures" / "recorded"
    if recorded_dir.is_dir():
        for path in sorted(recorded_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            name = path.name
            if name.startswith("cboe_"):
                reason = (
                    "One Cboe delayed quote saved for the parser. "
                    "The CDN is a current snapshot, not an archive, and this file "
                    "has no later session path."
                )
                stamp = str(payload.get("timestamp", ""))
            elif name.startswith("webull_"):
                reason = "Redacted field example. Not an account capture and not a session path."
                stamp = str(payload.get("as_of", ""))
            elif name.startswith("alpaca_"):
                reason = (
                    "Field example for the Alpaca parser. "
                    "Not a live capture and not a session path."
                )
                stamp = str(payload.get("as_of", ""))
            else:
                reason = "Recorded file is not a chain-session archive."
                stamp = ""
            recorded.append(
                {
                    "path": str(path.relative_to(root)),
                    "timestamp": stamp,
                    "usable_sessions": "0",
                    "reason": reason,
                }
            )
    synthetic = sorted(
        path.name for path in (root / "tests" / "fixtures").glob("*.json") if path.is_file()
    )
    archive = []
    data_root = root / "data"
    if data_root.is_dir():
        archive = [str(path.relative_to(root)) for path in data_root.rglob("*.json")]
    return {
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "timezone": "America/Chicago",
        "oos_start": OOS_START.isoformat(),
        "chain_sessions": 0,
        "paired_ohlc_sessions": 0,
        "recorded_slices": recorded,
        "synthetic_fixtures_excluded": synthetic,
        "local_archive_files": archive,
        "massive_key_set": _key_set("MASSIVE_API_KEY"),
        "thetadata_username_set": _key_set("THETADATA_USERNAME"),
        "thetadata_password_set": _key_set("THETADATA_PASSWORD"),
        "cboe_delayed": "current snapshot, not an archive",
        "orders": False,
    }


def build_report(root: Path, records: list[SessionRecord] | None = None) -> dict:
    """Run the checks on the sessions actually in hand. The default list is empty."""

    history = inventory_history(root)
    if records is None:
        records = []
    if history["chain_sessions"] == 0 and not records:
        results = run_preregistered([])
    else:
        results = run_preregistered(records)
    badge = badge_for(results)
    return {
        "as_of": "2026-11-17",
        "badge": badge,
        "history": history,
        "follow_through_minutes": FOLLOW_THROUGH_MINUTES,
        "min_arm": MIN_ARM,
        "tests": [
            {
                "name": item.name,
                "verdict": item.verdict,
                "passed": item.passed,
                "sample_size": item.sample_size,
                "in_sample_size": item.in_sample_size,
                "out_of_sample_size": item.out_of_sample_size,
                "estimate": item.estimate,
                "baseline": item.baseline,
                "detail": item.detail,
            }
            for item in results
        ],
        "passed_count": sum(1 for item in results if item.passed),
    }


def render_markdown(report: dict) -> str:
    history = report["history"]
    lines = [
        "# Validation report, 2026-11-17",
        "",
        "Window: 2025-05-17 through 2026-11-17, America/Chicago.",
        "Out of sample: 2026-05-17 through 2026-11-17.",
        "Follow-through clock: 120 minutes, same clock on cross days and other days.",
        "A test passes only when the out-of-sample arm has at least 60 sessions",
        "and clears the pre-registered margin. Otherwise the verdict is inconclusive",
        "or fail. In-sample numbers cannot grant a pass.",
        "",
        f"Badge: {report['badge']}.",
        "",
        "## History actually available",
        "",
        "Chain sessions with a level at time t and a later session path: "
        f"{history['chain_sessions']}.",
        f"Those sessions paired with OHLC: {history['paired_ohlc_sessions']}.",
        "",
        "Cboe delayed quotes are a current snapshot, not an archive. "
        "This run did not call the CDN and did not treat a live quote as 18 months.",
        "ThetaData and Massive were not called. "
        f"MASSIVE_API_KEY set: {history['massive_key_set']}. "
        f"THETADATA_USERNAME set: {history['thetadata_username_set']}. "
        f"THETADATA_PASSWORD set: {history['thetadata_password_set']}.",
        "No paid signup was started. No order was sent.",
        "",
        "Synthetic fixture chains were excluded. They are hand-built engine inputs.",
        "Excluded files: " + ", ".join(history["synthetic_fixtures_excluded"]) + ".",
        "",
        "Parser slices in the repo, and why each one is not a test session:",
        "",
    ]
    if not history["recorded_slices"]:
        lines.append("No recorded slices are in the tree.")
    for item in history["recorded_slices"]:
        lines.append(
            f"- `{item['path']}` timestamp `{item['timestamp']}` "
            f"usable sessions {item['usable_sessions']}. {item['reason']}"
        )
    if history["local_archive_files"]:
        lines.extend(["", "Local JSON under data/:", ""])
        lines.extend(f"- `{name}`" for name in history["local_archive_files"])
    else:
        lines.extend(["", "No chain archive is stored under data/.", ""])
    lines.extend(["## Tests", ""])
    lines.append("| Test | Verdict | Sample | In sample | Out of sample | Estimate | Baseline |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for item in report["tests"]:
        lines.append(
            f"| {item['name']} | {item['verdict']} | {item['sample_size']} | "
            f"{item['in_sample_size']} | {item['out_of_sample_size']} | "
            f"{item['estimate']} | {item['baseline']} |"
        )
        lines.append("")
        lines.append(item["detail"])
        lines.append("")
    lines.append(f"Tests passed: {report['passed_count']} of {len(report['tests'])}.")
    if report["passed_count"] == 0 and history["chain_sessions"] == 0:
        lines.append(
            "None of the five tests passed. The sample inside the window is zero, "
            "so the result is inconclusive, not a confirmation and not a rejection "
            "of the hypothesis."
        )
    lines.append("")
    lines.append(f"The dashboard badge matches this report: {report['badge']}.")
    lines.append("")
    return "\n".join(lines)


def report_dir(root: Path) -> Path:
    return root / "docs" / "backtests"


def write_report(root: Path) -> dict:
    report = build_report(root)
    folder = report_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{REPORT_NAME}.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    (folder / f"{REPORT_NAME}.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "gex_scanner").is_dir():
            return parent
    raise FileNotFoundError("gex-scanner repo root was not found")


def load_latest_verdict(root: Path | None = None) -> dict:
    """Read the dated report. A missing file keeps the unvalidated badge."""

    if root is None:
        root = repo_root()
    path = report_dir(root) / f"{REPORT_NAME}.json"
    if not path.is_file():
        return {"badge": UNVALIDATED, "passed_count": 0, "tests": []}
    return json.loads(path.read_text(encoding="utf-8"))


def current_badge(root: Path | None = None) -> str:
    verdict = load_latest_verdict(root)
    badge = str(verdict.get("badge", UNVALIDATED))
    if badge not in {UNVALIDATED, VALIDATED}:
        return UNVALIDATED
    return badge
