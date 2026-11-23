# SPDX-License-Identifier: Apache-2.0
"""Local HTML for the ranked table and one symbol. No remote assets."""

from __future__ import annotations

from html import escape

from gex_scanner.backtest.preregistered import current_badge
from gex_scanner.scanner.scan import CHIP_FILTERS, ExpiryView, RankRow, StrikeBar

_STYLE = """
body { font-family: sans-serif; margin: 1.5rem; color: #1b1b1b; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid #ccc; text-align: left; padding: 0.35rem; }
.badge { border: 1px solid #8a5a00; color: #8a5a00; padding: 0.2rem 0.4rem; }
.provenance { background: #f6f3ea; padding: 0.4rem 0.6rem; }
.refresh-note { max-width: 46rem; }
.chips { display: flex; gap: 0.4rem; margin: 0.6rem 0; }
.chip { border: 1px solid #888; padding: 0.15rem 0.45rem; text-decoration: none; color: inherit; }
.chip.on { background: #1b1b1b; color: #fff; }
svg { width: 100%; max-width: 48rem; height: auto; background: #fafafa; }
.bar.pos { fill: #1f7a4d; }
.bar.neg { fill: #9b2c2c; }
.legend { display: flex; gap: 1rem; flex-wrap: wrap; }
"""

REFRESH_NOTE = (
    "Refresh reloads the newest snapshot already in this SQLite file. "
    "It does not call Alpaca or Webull and it does not place an order. "
    "python scripts/scan_fixtures.py writes the fixture universe into data/scanner.sqlite. "
    "python scripts/alpaca_snapshot.py SYMBOL and python scripts/webull_snapshot.py SYMBOL "
    "save one raw cache when keys are set. Those cache files are not rows in this database "
    "until a scan stores them. Restart with python scripts/dashboard.py on 127.0.0.1:8765 "
    "if this process is still an older server. A server from this version reads the file "
    "again on Refresh."
)

_CHIP_NAMES = tuple(item.value for item in CHIP_FILTERS)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return escape(f"{value:.4g}")
    return escape(str(value))


def _seconds(value: float) -> str:
    return escape(f"{value:.0f}")


def _refresh(action: str, expiry: str | None = None) -> str:
    hidden = ""
    if expiry:
        hidden = f'<input type="hidden" name="expiry" value="{escape(expiry)}">'
    return (
        f'<form method="get" action="{escape(action)}">'
        f'{hidden}<button type="submit">Refresh</button></form>'
        f'<p class="refresh-note">{escape(REFRESH_NOTE)}</p>'
    )


def _provenance(row: RankRow) -> str:
    return (
        f'<p class="provenance">Vendor {escape(row.vendor)}. '
        f"Captured {escape(row.captured_at_utc)}. "
        f"Session {escape(row.snapshot_session_key)}. "
        f"Data age {_seconds(row.data_age_seconds)} seconds.</p>"
    )


def render_index(rows: list[RankRow], badge: str | None = None) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f'<td><a href="/symbol/{escape(row.underlying)}">{escape(row.underlying)}</a></td>'
            f"<td>{escape(row.vendor)}</td>"
            f"<td>{escape(row.captured_at_utc)}</td>"
            f"<td>{_cell(row.score)}</td>"
            f"<td>{escape(row.regime_sign)}</td>"
            f"<td>{_cell(row.flip)}</td>"
            f"<td>{_cell(row.call_wall)}</td>"
            f"<td>{_cell(row.put_wall)}</td>"
            f"<td>{_cell(row.futures_flip)}</td>"
            f"<td>{escape(row.active_session_key)}</td>"
            f"<td>{escape(row.session_ct)}</td>"
            f"<td>{_seconds(row.data_age_seconds)}</td>"
            f"<td>{escape(', '.join(row.quality_flags))}</td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr>"
        "<th>Symbol</th><th>Vendor</th><th>Captured</th><th>Score</th><th>Regime</th>"
        "<th>Flip</th><th>Call wall</th><th>Put wall</th><th>Futures flip</th>"
        "<th>Session</th><th>CT</th><th>Age seconds</th><th>Quality</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        "<title>Ranked setups</title><style>" + _STYLE + "</style></head><body>"
        "<h1>Ranked setups</h1>"
        f'<p class="badge">{escape(badge or current_badge())}</p>'
        "<p>Research rank from visible components. Not a profit forecast.</p>"
        + _refresh("/")
        + table
        + "</body></html>"
    )


def _view_for(row: RankRow, expiry: str) -> ExpiryView | None:
    for view in row.views:
        if view.expiry_filter == expiry:
            return view
    return None


def _chips(underlying: str, selected: str) -> str:
    links = []
    for name in _CHIP_NAMES:
        kind = "chip on" if name == selected else "chip"
        href = f"/symbol/{escape(underlying)}?expiry={escape(name)}"
        links.append(f'<a class="{kind}" href="{href}">{escape(name)}</a>')
    return '<nav class="chips">' + "".join(links) + "</nav>"


def _scale(values: list[float]) -> tuple[float, float]:
    low = min(values)
    high = max(values)
    if high == low:
        high = low + 1.0
    return low, high


def _strike_chart(
    strikes: tuple[StrikeBar, ...],
    *,
    spot: float,
    call_wall: float | None,
    put_wall: float | None,
    flip: float | None,
) -> str:
    marks = [("Spot", spot)]
    if call_wall is not None:
        marks.append(("Call wall", call_wall))
    if put_wall is not None:
        marks.append(("Put wall", put_wall))
    if flip is not None:
        marks.append(("Flip", flip))
    if not strikes and not marks:
        return "<p>No strikes in this filter.</p>"
    domain = [bar.strike for bar in strikes] + [level for _label, level in marks]
    low, high = _scale(domain)
    nets = [bar.net_gex for bar in strikes] or [0.0]
    peak = max(abs(value) for value in nets) or 1.0
    width, height = 720, 280
    pad_l, pad_r, pad_t, pad_b = 16, 16, 22, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    mid = pad_t + plot_h / 2

    def x_of(level: float) -> float:
        return pad_l + (level - low) / (high - low) * plot_w

    def y_of(net: float) -> float:
        return mid - (net / peak) * (plot_h / 2)

    gap = plot_w / max(len(strikes), 1)
    bar_w = max(2.0, min(14.0, gap * 0.6))
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img">',
        "<title>Net GEX by strike with spot, walls, and flip</title>",
        f'<line x1="{pad_l}" y1="{mid:.1f}" x2="{width - pad_r}" y2="{mid:.1f}" stroke="#ccc"/>',
    ]
    for bar in strikes:
        x = x_of(bar.strike) - bar_w / 2
        y = y_of(bar.net_gex)
        top = min(y, mid)
        kind = "pos" if bar.net_gex >= 0 else "neg"
        parts.append(
            f'<rect class="bar {kind}" x="{x:.2f}" y="{top:.2f}" '
            f'width="{bar_w:.2f}" height="{abs(mid - y):.2f}"/>'
        )
    colors = {
        "Spot": "#1b1b1b",
        "Call wall": "#1f7a4d",
        "Put wall": "#9b2c2c",
        "Flip": "#8a5a00",
    }
    for label, level in marks:
        x = x_of(level)
        parts.append(
            f'<line x1="{x:.2f}" y1="{pad_t}" x2="{x:.2f}" y2="{height - pad_b}" '
            f'stroke="{colors[label]}" stroke-dasharray="4 3"/>'
        )
    parts.append("</svg>")
    legend = "".join(
        f'<span style="color: {colors[label]}">{escape(label)} {_cell(level)}</span>'
        for label, level in marks
    )
    return "".join(parts) + f'<p class="legend">{legend}</p>'


def _curve_chart(view: ExpiryView | None, spot: float) -> str:
    if view is None or not view.curve:
        return "<p>No repriced curve is stored with this snapshot.</p>"
    spots = [point.spot for point in view.curve]
    nets = [point.net_gex for point in view.curve]
    low, high = _scale(spots)
    peak = max(abs(value) for value in nets) or 1.0
    width, height = 720, 220
    pad_l, pad_r, pad_t, pad_b = 16, 16, 16, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    mid = pad_t + plot_h / 2

    def x_of(level: float) -> float:
        return pad_l + (level - low) / (high - low) * plot_w

    def y_of(net: float) -> float:
        return mid - (net / peak) * (plot_h / 2)

    points = " ".join(f"{x_of(point.spot):.2f},{y_of(point.net_gex):.2f}" for point in view.curve)
    note = "No crossing in band." if view.no_crossing_in_band else f"Flip {_cell(view.flip)}."
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img">'
        "<title>Repriced net GEX curve</title>"
        f'<line x1="{pad_l}" y1="{mid:.1f}" x2="{width - pad_r}" y2="{mid:.1f}" stroke="#ccc"/>'
        f'<polyline fill="none" stroke="#1b1b1b" stroke-width="1.5" points="{points}"/>'
        f'<line x1="{x_of(spot):.2f}" y1="{pad_t}" x2="{x_of(spot):.2f}" '
        f'y2="{height - pad_b}" stroke="#1b1b1b" stroke-dasharray="4 3"/>'
        "</svg>"
        f"<p>{escape(note)}</p>"
    )


def render_symbol(
    row: RankRow,
    badge: str | None = None,
    expiry: str | None = None,
) -> str:
    selected = expiry if expiry in _CHIP_NAMES else "all"
    view = _view_for(row, selected)
    strikes = view.strikes if view is not None else row.strikes
    flip = view.flip if view is not None else row.flip
    call_wall = view.call_wall if view is not None else row.call_wall
    put_wall = view.put_wall if view is not None else row.put_wall
    expiries = "".join(
        f"<li>{escape(item.expiry)}: {_cell(item.net_gex)}</li>" for item in row.expiries
    )
    components = "".join(
        f"<li>{escape(name)}: {_cell(value)}</li>" for name, value in sorted(row.components.items())
    )
    note = f"<p>{escape(row.note)}</p>" if row.note else ""
    if row.futures_symbol:
        futures = (
            f"<p>Futures {escape(row.futures_symbol)} flip {_cell(row.futures_flip)} "
            f"basis {_cell(row.basis)} {escape(row.basis_method or '')}.</p>"
        )
    else:
        futures = ""
    missing = ""
    if view is None:
        missing = (
            "<p>This snapshot has no stored view for that filter. The chart is the saved scan.</p>"
        )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{escape(row.underlying)} GEX</title><style>" + _STYLE + "</style></head><body>"
        f'<p><a href="/">Ranked setups</a></p>'
        f"<h1>{escape(row.underlying)}</h1>"
        f'<p class="badge">{escape(badge or current_badge())}</p>'
        + _provenance(row)
        + _refresh(f"/symbol/{row.underlying}", selected)
        + _chips(row.underlying, selected)
        + missing
        + f"<p>{escape(row.disclaimer)}</p>"
        + f"<p>Unit: {escape(row.unit)}</p>"
        + f"<p>Filter {escape(selected)}. "
        + f"Session {escape(row.snapshot_session_key)} "
        + f"CT {escape(row.session_ct)} ET {escape(row.session_et)}. "
        + f"Quality {row.contracts_included}/{row.contracts_seen}.</p>"
        + f"<p>Flip {_cell(flip)}. Call wall {_cell(call_wall)}. "
        + f"Put wall {_cell(put_wall)}. "
        + f"0DTE call {_cell(row.dte_call_wall)}. 0DTE put {_cell(row.dte_put_wall)}.</p>"
        + futures
        + note
        + "<h2>Components</h2><ul>"
        + components
        + "</ul><h2>Expiry breakdown</h2><ul>"
        + expiries
        + "</ul><h2>GEX by strike</h2>"
        + _strike_chart(
            strikes,
            spot=row.spot,
            call_wall=call_wall,
            put_wall=put_wall,
            flip=flip,
        )
        + "<h2>Repriced net GEX</h2>"
        + _curve_chart(view, row.spot)
        + "</body></html>"
    )
