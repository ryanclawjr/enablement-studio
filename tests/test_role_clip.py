from __future__ import annotations

import math
import re
from html import escape
from pathlib import Path

from enablement_studio.engine import generate
from enablement_studio.html_render import TEMPLATE_PATH, render_page
from enablement_studio.models import Product

REPO = Path(__file__).resolve().parents[1]
PRODUCT_MD = REPO / "PRODUCT.md"


def _page_css() -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    start = html.index("<style>")
    end = html.index("</style>", start)
    return html[start:end]


def _css_rule(css: str, selector: str) -> str | None:
    pattern = rf"{re.escape(selector)}\s*\{{([^}}]*)\}}"
    match = re.search(pattern, css)
    if match is None:
        return None
    return match.group(1)


def _decl_px(rule: str, prop: str) -> list[float]:
    match = re.search(rf"{re.escape(prop)}:\s*([^;]+)", rule)
    if match is None:
        return []
    return [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)px", match.group(1))]


def _padding_block_px(rule: str) -> tuple[float, float]:
    values = _decl_px(rule, "padding")
    if values:
        if len(values) == 1:
            return values[0], values[0]
        if len(values) == 2:
            return values[0], values[0]
        if len(values) == 3:
            return values[0], values[2]
        return values[0], values[2]
    top = _decl_px(rule, "padding-top")
    bottom = _decl_px(rule, "padding-bottom")
    return (top[0] if top else 0.0), (bottom[0] if bottom else 0.0)


def _has_nowrap(rule: str) -> bool:
    return bool(re.search(r"white-space:\s*nowrap", rule))


def _has_overflow_hidden(rule: str) -> bool:
    return bool(re.search(r"overflow:\s*hidden", rule))


def _has_fixed_px_height(rule: str) -> bool:
    return bool(re.search(r"(?<![\w-])height:\s*\d+(?:\.\d+)?px", rule))


def _harborline_graph_html(job_text: str) -> str:
    output, _engine = generate(Product.ROLE, job_text, force_offline=True)
    return render_page(
        product=Product.ROLE,
        project="default",
        text=job_text,
        runs=[],
        output=output,
        step="graph",
    )


def _inline_styles(html: str, class_name: str) -> list[str]:
    return re.findall(
        rf'class="[^"]*{re.escape(class_name)}[^"]*"[^>]*style="([^"]*)"',
        html,
    )


def _style_px(style: str, prop: str) -> float | None:
    match = re.search(rf"(?<![\w-]){re.escape(prop)}:\s*(\d+(?:\.\d+)?)px", style)
    if match is None:
        return None
    return float(match.group(1))


def test_graph_node_titles_are_not_css_clipped(job_text: str) -> None:
    css = _page_css()
    node = _css_rule(css, ".graph-node") or ""
    strong = _css_rule(css, ".graph-node strong") or ""
    html = _harborline_graph_html(job_text)
    inline = _inline_styles(html, "graph-node")
    assert inline
    nowrap = _has_nowrap(node) or _has_nowrap(strong)
    overflow_hidden = _has_overflow_hidden(node) or _has_overflow_hidden(strong)
    fixed_height = _has_fixed_px_height(node) or any(
        _has_fixed_px_height(style) for style in inline
    )
    assert not (nowrap and overflow_hidden and fixed_height)
    assert not nowrap
    assert not overflow_hidden
    assert not fixed_height
    assert "Run first conversations with small-business owners" in html
    assert (
        escape(
            "Map Harborline's (example) value to the buyer's weekend cash-flow",
            quote=True,
        )
        in html
    )
    assert "Close on a dated next step and log evidence in the CRM" in html
    assert "height:56px" not in html


def test_sheet_stepper_cannot_be_overflow_clipped() -> None:
    css = _page_css()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    sheet = _css_rule(css, ".object-sheet")
    assert sheet is not None
    assert not re.search(r"overflow:\s*auto", sheet)
    assert re.search(r"max-height:", sheet)
    scroll = _css_rule(css, ".sheet-scroll")
    assert scroll is not None
    assert re.search(r"overflow:\s*auto", scroll)
    assert re.search(
        r'class="sheet-scroll"[\s\S]+</div>\s*\{\{step_nav\}\}',
        template,
    )
    assert "{{step_nav}}" not in template.split('class="sheet-scroll"', 1)[1].split(
        "</div>", 1
    )[0]


def test_source_textarea_does_not_clip_mid_glyph() -> None:
    css = _page_css()
    rule = _css_rule(css, "textarea")
    assert rule is not None
    min_heights = _decl_px(rule, "min-height")
    line_heights = _decl_px(rule, "line-height")
    assert min_heights
    assert line_heights
    top, bottom = _padding_block_px(rule)
    inner = min_heights[0] - top - bottom
    assert inner > 0
    assert inner % line_heights[0] == 0
    assert not _has_overflow_hidden(rule)


def test_graph_edge_labels_do_not_sit_on_strokes(job_text: str) -> None:
    html = _harborline_graph_html(job_text)
    lines = re.findall(
        r'<line class="graph-edge" x1="([^"]+)" y1="([^"]+)" '
        r'x2="([^"]+)" y2="([^"]+)"',
        html,
    )
    labels = re.findall(
        r'<text class="graph-edge-label" x="([^"]+)" y="([^"]+)"',
        html,
    )
    assert lines
    assert len(labels) == len(lines)
    for (x1, y1, x2, y2), (lx, ly) in zip(lines, labels, strict=True):
        px1, py1, px2, py2 = map(float, (x1, y1, x2, y2))
        x, y = float(lx), float(ly)
        dx = px2 - px1
        dy = py2 - py1
        length = math.hypot(dx, dy) or 1.0
        distance = abs((y - py1) * dx - (x - px1) * dy) / length
        assert distance >= 12


def test_harborline_graph_stage_covers_seven_nodes(job_text: str) -> None:
    html = _harborline_graph_html(job_text)
    assert html.count('class="graph-node"') == 7
    stage = _inline_styles(html, "graph-stage")
    assert stage
    stage_h = _style_px(stage[0], "min-height") or _style_px(stage[0], "height")
    assert stage_h is not None
    bottoms: list[float] = []
    for style in _inline_styles(html, "graph-node"):
        top = _style_px(style, "top")
        card_h = _style_px(style, "min-height") or _style_px(style, "height")
        assert top is not None
        assert card_h is not None
        bottoms.append(top + card_h)
    assert stage_h >= max(bottoms)
    assert 'data-graph="relations"' in html
    assert "prerequisite" in html
    assert ">then<" in html


def test_object_row_and_sheet_stay_one_table() -> None:
    css = _page_css()
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    product = PRODUCT_MD.read_text(encoding="utf-8")
    assert "position: fixed" not in css
    assert "position:fixed" not in css
    assert 'class="object-table"' in template
    assert "{{object_row}}" in template
    assert 'class="object-sheet"' in template
    assert (
        "The object row and the current sheet share one table. "
        "Nothing is `position: fixed` against the other. "
        "They must not overlap or clip at 1280×800 or 1024×588."
    ) in product
