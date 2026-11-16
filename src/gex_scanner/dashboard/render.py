# SPDX-License-Identifier: Apache-2.0
"""Local HTML for the ranked table and one symbol. No remote assets."""

from __future__ import annotations

from html import escape

from gex_scanner.scanner.scan import RankRow

_STYLE = """
body { font-family: sans-serif; margin: 1.5rem; color: #1b1b1b; }
table { border-collapse: collapse; width: 100%; }
th, td { border-bottom: 1px solid #ccc; text-align: left; padding: 0.35rem; }
.badge { border: 1px solid #8a5a00; color: #8a5a00; padding: 0.2rem 0.4rem; }
.bar-row { display: grid; grid-template-columns: 6rem 1fr 8rem; gap: 0.5rem; margin: 0.2rem 0; }
.track { background: #eee; height: 0.8rem; }
.bar { height: 0.8rem; }
.pos { background: #1f7a4d; }
.neg { background: #9b2c2c; }
"""


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return escape(f"{value:.4g}")
    return escape(str(value))


def render_index(rows: list[RankRow]) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr>"
            f'<td><a href="/symbol/{escape(row.underlying)}">{escape(row.underlying)}</a></td>'
            f"<td>{_cell(row.score)}</td>"
            f"<td>{escape(row.regime_sign)}</td>"
            f"<td>{_cell(row.flip)}</td>"
            f"<td>{_cell(row.call_wall)}</td>"
            f"<td>{_cell(row.put_wall)}</td>"
            f"<td>{_cell(row.futures_flip)}</td>"
            f"<td>{escape(row.active_session_key)}</td>"
            f"<td>{escape(row.session_ct)}</td>"
            f"<td>{_cell(row.data_age_seconds)}</td>"
            f"<td>{escape(', '.join(row.quality_flags))}</td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr>"
        "<th>Symbol</th><th>Score</th><th>Regime</th><th>Flip</th>"
        "<th>Call wall</th><th>Put wall</th><th>Futures flip</th>"
        "<th>Session</th><th>CT</th><th>Age seconds</th><th>Quality</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        "<title>Ranked setups</title><style>" + _STYLE + "</style></head><body>"
        "<h1>Ranked setups</h1>"
        '<p class="badge">unvalidated hypothesis</p>'
        "<p>Research rank from visible components. Not a profit forecast.</p>"
        + table
        + "</body></html>"
    )


def render_symbol(row: RankRow) -> str:
    peak = max((abs(bar.net_gex) for bar in row.strikes), default=0.0)
    bars = []
    for bar in row.strikes:
        width = 0.0 if peak == 0 else abs(bar.net_gex) / peak * 100.0
        kind = "pos" if bar.net_gex >= 0 else "neg"
        bars.append(
            '<div class="bar-row">'
            f"<span>{_cell(bar.strike)}</span>"
            f'<div class="track"><div class="bar {kind}" '
            f'style="width: {width:.2f}%"></div></div>'
            f"<span>{_cell(bar.net_gex)}</span>"
            "</div>"
        )
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
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        f"<title>{escape(row.underlying)} GEX</title><style>" + _STYLE + "</style></head><body>"
        f'<p><a href="/">Ranked setups</a></p>'
        f"<h1>{escape(row.underlying)}</h1>"
        '<p class="badge">unvalidated hypothesis</p>'
        f"<p>{escape(row.disclaimer)}</p>"
        f"<p>Unit: {escape(row.unit)}</p>"
        f"<p>Session {escape(row.snapshot_session_key)} "
        f"CT {escape(row.session_ct)} ET {escape(row.session_et)}. "
        f"Age {_cell(row.data_age_seconds)} seconds. "
        f"Quality {row.contracts_included}/{row.contracts_seen}.</p>"
        f"<p>Flip {_cell(row.flip)}. Call wall {_cell(row.call_wall)}. "
        f"Put wall {_cell(row.put_wall)}. "
        f"0DTE call {_cell(row.dte_call_wall)}. 0DTE put {_cell(row.dte_put_wall)}.</p>"
        + futures
        + note
        + "<h2>Components</h2><ul>"
        + components
        + "</ul><h2>Expiry breakdown</h2><ul>"
        + expiries
        + "</ul><h2>GEX by strike</h2>"
        + "".join(bars)
        + "</body></html>"
    )
