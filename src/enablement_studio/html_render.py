from __future__ import annotations

from html import escape
from pathlib import Path

from enablement_studio.engine import llm_configured
from enablement_studio.models import (
    CallCoaching,
    LessonCritique,
    Product,
    ProductOutput,
    RoleEnablement,
    SavedRun,
    SkillEdge,
    SkillNode,
)
from enablement_studio.render import product_label, render_compare, source_banner
from enablement_studio.role.family import (
    EnablementFrame,
    JobFamily,
    classify_enablement_frame,
    classify_job_family,
)
from enablement_studio.role.title_swap import role_invalid_reasons
from enablement_studio.textutil import extract_title

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "page.html"
RECENT_LIMIT = 20

_FRAME_VOICE = {
    EnablementFrame.DESIGNER: "the learner designs instruction",
    EnablementFrame.EDUCATOR: "the learner teaches or coaches practitioners",
    EnablementFrame.PARTNER: "the learner enables a field team",
}


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def render_page(
    *,
    product: Product,
    project: str,
    text: str,
    runs: list[SavedRun],
    error: str | None = None,
    output: ProductOutput | None = None,
    run: SavedRun | None = None,
    compare_output: ProductOutput | None = None,
    compare_run: SavedRun | None = None,
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    source_heading, source_label = _source_copy(product)
    page_title = _page_title(product)
    has_key = llm_configured()
    llm_disabled = "" if has_key else " disabled"
    llm_caption = "" if has_key else ' <span class="no-key-caption">(no key)</span>'

    return _fill(
        template,
        {
            "{{page_title}}": _e(page_title),
            "{{product_h1}}": _e(page_title),
            "{{body_class}}": _body_class(product),
            "{{product_value}}": _e(product.value),
            "{{role_bench}}": _bench_class(product, Product.ROLE),
            "{{call_bench}}": _bench_class(product, Product.CALL),
            "{{critic_bench}}": _bench_class(product, Product.CRITIC),
            "{{bench_project}}": _e(project),
            "{{source_heading}}": _e(source_heading),
            "{{source_label}}": _e(source_label),
            "{{source_input_block}}": _source_input_block(text, has_output=output is not None),
            "{{llm_disabled_attr}}": llm_disabled,
            "{{llm_caption}}": llm_caption,
            "{{project}}": _e(project),
            "{{error_block}}": _error_block(error),
            "{{result_block}}": (
                ""
                if compare_run is not None and compare_output is not None and run is not None
                else _result_block(product, output, run, text, project)
            ),
            "{{compare_block}}": _compare_block(
                run, output, compare_run, compare_output
            ),
            "{{runs_heading}}": _runs_heading(product, project),
            "{{runs_block}}": _runs_block(runs, run, product, project),
        },
    )


def _page_title(product: Product) -> str:
    if product is Product.ROLE:
        return "Role"
    if product is Product.CALL:
        return "Call"
    if product is Product.CRITIC:
        return "Critic"
    never: Product = product
    raise ValueError(f"unsupported product: {never}")


def _body_class(product: Product) -> str:
    return f"product-{product.value}"


def _bench_class(current: Product, product: Product) -> str:
    return "bench current" if current is product else "bench"


def _source_copy(product: Product) -> tuple[str, str]:
    if product is Product.ROLE:
        return "Source", "Job, SOP, or policy"
    if product is Product.CALL:
        return "Source", "Sales or training transcript"
    if product is Product.CRITIC:
        return "Source", "Lesson outline or storyboard"
    never: Product = product
    raise ValueError(f"unsupported product: {never}")


def _source_input_block(text: str, has_output: bool) -> str:
    escaped_text = _e(text)
    if not has_output or not text.strip():
        return f'<textarea name="text" spellcheck="false" placeholder="Paste source text...">{escaped_text}</textarea>'
    
    # After a run: show collapsed source preview + expand
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    preview_lines = lines[:4]
    preview_text = "\n".join(preview_lines)
    return (
        '<div class="source-preview-box">'
        f'{_e(preview_text)}'
        '</div>'
        '<details class="source-details">'
        '<summary>Edit source text</summary>'
        f'<textarea name="text" spellcheck="false">{escaped_text}</textarea>'
        '</details>'
    )


def _fill(template: str, mapping: dict[str, str]) -> str:
    pieces: list[str] = []
    cursor = 0
    while True:
        found_at: int | None = None
        found_token: str | None = None
        for token in mapping:
            pos = template.find(token, cursor)
            if pos != -1 and (found_at is None or pos < found_at):
                found_at = pos
                found_token = token
        if found_token is None or found_at is None:
            pieces.append(template[cursor:])
            return "".join(pieces)
        pieces.append(template[cursor:found_at])
        pieces.append(mapping[found_token])
        cursor = found_at + len(found_token)


def _error_block(error: str | None) -> str:
    if not error:
        return ""
    return f'<p class="error" role="alert">{_e(error)}</p>'


def _result_block(
    product: Product,
    output: ProductOutput | None,
    run: SavedRun | None,
    source: str,
    project: str,
) -> str:
    if output is None:
        return _empty_board(product, project)
    match output:
        case RoleEnablement():
            return _render_role_studio(output, run, source)
        case CallCoaching():
            return _render_call_studio(output, run)
        case LessonCritique():
            return _render_critic_studio(output, run)
        case _:
            never: ProductOutput = output
            raise TypeError(f"unsupported output: {type(never)!r}")


def _empty_board(product: Product, project: str) -> str:
    if product is Product.ROLE:
        empty = "Board is empty. Paste a job or SOP, or Run Harborline."
        label = "Run Harborline · EXAMPLE DATA"
        frames = (
            '<div class="empty-frames">'
            '<div class="empty-frame-box">Graph</div>'
            '<div class="empty-frame-box">Objectives</div>'
            '<div class="empty-frame-box">Outline</div>'
            '<div class="empty-frame-box">Practice</div>'
            '<div class="empty-frame-box">Quiz</div>'
            '</div>'
        )
    elif product is Product.CALL:
        empty = "Board is empty. Paste a transcript, or Run Harborline."
        label = "Run Harborline · EXAMPLE DATA"
        frames = (
            '<div class="empty-frames">'
            '<div class="empty-frame-box">Signals</div>'
            '<div class="empty-frame-box">Notes</div>'
            '<div class="empty-frame-box">Fix</div>'
            '</div>'
        )
    elif product is Product.CRITIC:
        empty = "Board is empty. Paste an outline or storyboard, or Run Harborline."
        label = "Run Harborline · EXAMPLE DATA"
        frames = (
            '<div class="empty-frames">'
            '<div class="empty-frame-box">Scores</div>'
            '<div class="empty-frame-box">Findings</div>'
            '<div class="empty-frame-box">Rewrite</div>'
            '</div>'
        )
    else:
        never: Product = product
        raise ValueError(f"unsupported product: {never}")
    return (
        '<div class="empty-board">'
        f"<p>{_e(empty)}</p>"
        f'<form method="post" action="/" class="demo-run">'
        f'<input type="hidden" name="product" value="{_e(product.value)}">'
        f'<input type="hidden" name="project" value="{_e(project)}">'
        f'<input type="hidden" name="action" value="demo">'
        f'<button class="run" type="submit">{_e(label)}</button>'
        "</form>"
        f"{frames}"
        "</div>"
    )


def _role_source(run: SavedRun | None, fallback: str, output: RoleEnablement) -> str:
    if run is not None and run.input_text.strip():
        return run.input_text
    if fallback.strip():
        return fallback
    return output.role_title


def _role_diagnosis(output: RoleEnablement, source: str) -> tuple[JobFamily, EnablementFrame | None]:
    heading = extract_title(source, output.role_title)
    family = classify_job_family(source, heading)
    frame = classify_enablement_frame(source, heading)
    return family, frame


def _render_role_studio(
    output: RoleEnablement, run: SavedRun | None, source: str
) -> str:
    source_text = _role_source(run, source, output)
    family, frame = _role_diagnosis(output, source_text)
    objects = _render_role_objects(output)
    banner_text = source_banner(output)
    
    # Combined single meta row: title + Family/Frame as one meta row + vN · offline
    version_str = f"v{run.version}" if run is not None else "v1"
    engine_str = run.engine.value if run is not None else "offline"
    run_id_str = f"run {run.id} · " if run is not None else ""
    project_str = f"project {_e(run.project)} · " if run is not None else ""
    
    meta_chips = [
        f'<span class="meta-chip"><span class="meta-chip-label">Family</span> <strong data-family="{_e(family.value)}">{_e(family.value)}</strong></span>'
    ]
    if family is JobFamily.ENABLEMENT and frame is not None:
        voice = _FRAME_VOICE[frame]
        meta_chips.append(
            f'<span class="meta-chip"><span class="meta-chip-label">Frame</span> <strong data-frame="{_e(frame.value)}">{_e(frame.value)}</strong> — {_e(voice)}</span>'
        )
    meta_chips.append(f'<span class="meta-chip">{_e(run_id_str)}{_e(project_str)}{_e(version_str)} · engine {_e(engine_str)}</span>')
    
    meta_html = f'<div class="meta-row">{" ".join(meta_chips)}</div>'
    banner_html = f'<p class="source-note-banner">{_e(banner_text)}</p>'

    if output.invalid:
        reasons = "".join(
            f"<li>{_e(reason)}</li>"
            for reason in role_invalid_reasons(output, source_text)
        )
        return (
            '<article class="result studio-failed">'
            '<header class="module-header">'
            "<h2>Invalid module</h2>"
            f"<h3>{_e(output.role_title)}</h3>"
            f"{meta_html}"
            f"{banner_html}"
            "</header>"
            '<div class="invalid-banner">'
            "<strong>Not accepted</strong> — stored as a failed Role run so list, show, and eval can see the miss. "
            "It is not a successful module."
            f'<ul class="invalid-reasons">{reasons}</ul>'
            "</div>"
            "<h3>What the engine produced (not accepted)</h3>"
            f'<div class="failed-artifacts">{objects}</div>'
            "</article>"
        )
    return (
        '<article class="result studio-ok">'
        '<header class="module-header">'
        f"<h2>{_e(output.role_title)}</h2>"
        f"{meta_html}"
        f"{banner_html}"
        "</header>"
        f"{objects}"
        "</article>"
    )


def _render_call_studio(output: CallCoaching, run: SavedRun | None) -> str:
    version_str = f"v{run.version}" if run is not None else "v1"
    engine_str = run.engine.value if run is not None else "offline"
    run_id_str = f"run {run.id} · " if run is not None else ""
    project_str = f"project {_e(run.project)} · " if run is not None else ""
    meta_html = (
        '<div class="meta-row">'
        f'<span class="meta-chip">{_e(run_id_str)}{_e(project_str)}{_e(version_str)} · engine {_e(engine_str)}</span>'
        '</div>'
    )
    banner_html = f'<p class="source-note-banner">{_e(source_banner(output))}</p>'
    body = _render_call_objects(output)
    return (
        '<article class="result studio-ok">'
        '<header class="module-header">'
        f"<h2>{_e(output.call_title)}</h2>"
        f"{meta_html}"
        f"{banner_html}"
        "</header>"
        f"{body}"
        "</article>"
    )


def _render_critic_studio(output: LessonCritique, run: SavedRun | None) -> str:
    version_str = f"v{run.version}" if run is not None else "v1"
    engine_str = run.engine.value if run is not None else "offline"
    run_id_str = f"run {run.id} · " if run is not None else ""
    project_str = f"project {_e(run.project)} · " if run is not None else ""
    meta_html = (
        '<div class="meta-row">'
        f'<span class="meta-chip">{_e(run_id_str)}{_e(project_str)}{_e(version_str)} · engine {_e(engine_str)}</span>'
        '</div>'
    )
    banner_html = f'<p class="source-note-banner">{_e(source_banner(output))}</p>'
    body = _render_critic_objects(output)
    return (
        '<article class="result studio-ok">'
        '<header class="module-header">'
        f"<h2>{_e(output.lesson_title)}</h2>"
        f"{meta_html}"
        f"{banner_html}"
        "</header>"
        f"{body}"
        "</article>"
    )


def _generate_inline_svg_graph(nodes: list[SkillNode], edges: list[SkillEdge]) -> str:
    if not nodes:
        return ""
    count = len(nodes)
    node_width = 130
    node_height = 36
    gap = 40
    total_width = count * node_width + (count - 1) * gap + 40
    total_height = 80
    
    # Map edges by source
    edge_label_map: dict[str, str] = {}
    for edge in edges:
        edge_label_map[edge.source] = edge.relation

    svg_parts = [
        f'<div class="graph-svg-wrap">',
        f'<svg class="graph-svg" viewBox="0 0 {total_width} {total_height}" width="{total_width}" height="{total_height}" xmlns="http://www.w3.org/2000/svg">',
        '<defs>',
        '  <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        '    <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#6b6860"/>',
        '  </marker>',
        '</defs>',
    ]
    
    for i in range(count - 1):
        x1 = 20 + (i + 1) * node_width + i * gap
        x2 = x1 + gap
        y = 35
        rel = edge_label_map.get(nodes[i].id, "then")
        svg_parts.append(
            f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#e4e2dc" stroke-width="2" marker-end="url(#arrow)" />'
        )
        # Relation text on the line
        mid_x = (x1 + x2) / 2
        svg_parts.append(
            f'<text x="{mid_x}" y="{y - 6}" font-family="ui-sans-serif, system-ui, sans-serif" font-size="10" fill="#6b6860" text-anchor="middle">{_e(rel)}</text>'
        )

    for i, node in enumerate(nodes):
        x = 20 + i * (node_width + gap)
        y = 17
        label = node.name
        if len(label) > 16:
            label = label[:15] + "…"
        level_abbr = "L1" if node.level == "foundation" else ("L2" if node.level == "core" else "L3")
        svg_parts.append(
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="6" fill="#ffffff" stroke="#e4e2dc" stroke-width="1.5"/>'
        )
        svg_parts.append(
            f'<text x="{x + 8}" y="{y + 16}" font-family="ui-monospace, monospace" font-size="10" fill="#6b6860">{level_abbr}</text>'
        )
        svg_parts.append(
            f'<text x="{x + 8}" y="{y + 28}" font-family="ui-sans-serif, system-ui, sans-serif" font-size="11" font-weight="600" fill="#1a1916">{_e(label)}</text>'
        )

    svg_parts.append('</svg></div>')
    return "".join(svg_parts)


def _render_role_objects(output: RoleEnablement) -> str:
    # Target map for sequence captions
    edge_target_map: dict[str, tuple[str, str]] = {}
    for edge in output.skill_graph.edges:
        edge_target_map[edge.source] = (edge.target, edge.relation)
        
    nodes_items = []
    for node in output.skill_graph.nodes:
        level_abbr = "L1" if node.level == "foundation" else ("L2" if node.level == "core" else "L3")
        target_info = edge_target_map.get(node.id)
        target_html = f'<span class="graph-node-target">→ {escape(target_info[0])} ({escape(target_info[1])})</span>' if target_info else ''
        nodes_items.append(
            "<li>"
            '<div class="graph-node-head">'
            f'<span class="mono-caption">{level_abbr}</span> '
            f'<span class="graph-node-name">{_e(node.name)}</span>'
            f"{target_html}"
            "</div>"
            f'<p class="graph-node-detail">{_e(node.detail)}</p>'
            "</li>"
        )
    nodes_html = "".join(nodes_items) if nodes_items else "<li>No skill nodes.</li>"
    svg_graph = _generate_inline_svg_graph(output.skill_graph.nodes, output.skill_graph.edges)

    objectives = "".join(
        "<li>"
        f'<span class="mono-caption">{_e(item.id)}</span> '
        f'<span class="obj-statement">{_e(item.statement)}</span>'
        f'<p class="obj-measure">Measure: {_e(item.measure)}</p>'
        "</li>"
        for item in output.objectives
    )
    if not objectives:
        objectives = "<li>No objectives.</li>"

    outline = "".join(
        '<li class="timeline-item">'
        f'<span class="timeline-time mono-caption">{_e(block.minutes)} min</span> '
        '<div class="timeline-content">'
        f"<strong>{_e(block.title)}</strong>"
        f"<p>{_e(block.description)}</p>"
        "</div>"
        "</li>"
        for block in output.outline
    )

    steps = "".join(f"<li>{_e(step)}</li>" for step in output.practice.instructions)
    success = "".join(f"<li>{_e(item)}</li>" for item in output.practice.success_criteria)

    quiz = []
    for index, item in enumerate(output.quiz, start=1):
        choices = "".join(
            "<li{mark}>{choice}</li>".format(
                mark=' class="answer"' if choice == item.answer else "",
                choice=_e(choice),
            )
            for choice in item.choices
        )
        quiz.append(
            '<li class="quiz-item">'
            f'<p class="quiz-prompt">{index}. {_e(item.question)}</p>'
            f'<ul class="quiz-choices">{choices}</ul>'
            '<details class="quiz-details">'
            '<summary>Answer &amp; rationale</summary>'
            f'<div class="quiz-details-content"><strong>Answer:</strong> {_e(item.answer)}<br><strong>Why:</strong> {_e(item.rationale)}</div>'
            '</details>'
            "</li>"
        )

    return (
        '<section class="skill-graph object">'
        '<h3>Graph <span class="object-tag">Skills</span></h3>'
        f"{svg_graph}"
        f'<ol class="graph-list">{nodes_html}</ol>'
        "</section>"
        '<section class="objectives object">'
        '<h3>Objectives <span class="object-tag">Measurable</span></h3>'
        f'<ol class="objectives-list">{objectives}</ol>'
        "</section>"
        '<section class="outline object">'
        '<h3>Outline <span class="object-tag">30 Min</span></h3>'
        f'<ol class="timeline">{outline}</ol>'
        "</section>"
        f'<section class="practice object">'
        f'<h3>Practice <span class="object-tag">{_e(output.practice.title)}</span></h3>'
        f'<div class="practice-scenario"><strong>Scenario:</strong> {_e(output.practice.scenario)}</div>'
        f'<ol class="practice-steps">{steps}</ol>'
        '<div class="practice-success-title">Success criteria:</div>'
        f'<ul class="practice-success">{success}</ul>'
        "</section>"
        '<section class="quiz object">'
        '<h3>Quiz <span class="object-tag">Application</span></h3>'
        f'<ol class="quiz-list">{"".join(quiz)}</ol>'
        "</section>"
    )


def _render_call_objects(output: CallCoaching) -> str:
    signals = "".join(f"<li>{_e(signal)}</li>" for signal in output.signals)
    speakers = ""
    if output.speakers:
        speakers = f'<p class="mono-caption">Speakers: {_e(", ".join(output.speakers))}</p>'
    
    note_cards = "".join(
        '<div class="note-card">'
        f'<div class="note-audience">{_e(note.audience)}</div>'
        f'<div class="note-headline">{_e(note.headline)}</div>'
        f'<div class="note-body">{_e(note.body)}</div>'
        '</div>'
        for note in output.notes
    )
    fix = output.enablement_fix
    return (
        '<section class="object">'
        '<h3>Signals <span class="object-tag">Transcript</span></h3>'
        f"{speakers}"
        f'<ul class="practice-steps">{signals}</ul>'
        "</section>"
        '<section class="object">'
        '<h3>Notes <span class="object-tag">Coaching</span></h3>'
        f'<div class="coaching-notes-grid">{note_cards}</div>'
        "</section>"
        '<section class="object">'
        f'<h3>Fix <span class="object-tag">{_e(fix.title)}</span></h3>'
        f'<div class="practice-scenario"><strong>Problem:</strong> {_e(fix.problem)}</div>'
        f'<p><strong>Fix:</strong> {_e(fix.fix)}</p>'
        f'<p class="mono-caption">Measure: {_e(fix.measure)}</p>'
        "</section>"
    )


def _render_critic_objects(output: LessonCritique) -> str:
    scores = output.scores
    findings = "".join(
        f"<li><span class=\"mono-caption\">[{_e(finding.severity)}]</span> <strong>{_e(finding.area)}:</strong> {_e(finding.detail)}</li>"
        for finding in output.findings
    )
    rewrite = output.rewrite
    return (
        '<section class="object">'
        '<h3>Scores <span class="object-tag">Alignment 1–5</span></h3>'
        '<div class="scores-grid">'
        f'<div class="score-card"><div class="score-num">{_e(scores.objective_clarity)}</div><div class="score-label">Objective Clarity</div></div>'
        f'<div class="score-card"><div class="score-num">{_e(scores.activity_alignment)}</div><div class="score-label">Activity Alignment</div></div>'
        f'<div class="score-card"><div class="score-num">{_e(scores.assessment_alignment)}</div><div class="score-label">Assessment Alignment</div></div>'
        f'<div class="score-card"><div class="score-num">{_e(scores.overall)}</div><div class="score-label">Overall Alignment</div></div>'
        '</div>'
        "</section>"
        '<section class="object">'
        '<h3>Findings <span class="object-tag">Review</span></h3>'
        f'<ul class="practice-steps">{findings}</ul>'
        "</section>"
        '<section class="object">'
        f'<h3>Rewrite <span class="object-tag">Weakest: {_e(rewrite.target)}</span></h3>'
        f'<div class="practice-scenario"><strong>Reason:</strong> {_e(rewrite.reason)}</div>'
        f'<p>{_e(rewrite.replacement)}</p>'
        "</section>"
    )


# Kept for backward-compatibility if imported elsewhere
def _render_role(output: RoleEnablement) -> str:
    return _render_role_objects(output)


def _render_call(output: CallCoaching) -> str:
    return _render_call_objects(output)


def _render_critic(output: LessonCritique) -> str:
    return _render_critic_objects(output)


def _compare_block(
    run: SavedRun | None,
    output: ProductOutput | None,
    compare_run: SavedRun | None,
    compare_output: ProductOutput | None,
) -> str:
    if compare_run is None or compare_output is None:
        return ""
    if run is None or output is None:
        return (
            '<section class="compare">'
            "<h2>Compare</h2>"
            "<p>Open a run, then compare it with another Role run in this project.</p>"
            "</section>"
        )
    if (
        isinstance(output, RoleEnablement)
        and isinstance(compare_output, RoleEnablement)
        and run.product is Product.ROLE
        and compare_run.product is Product.ROLE
    ):
        return (
            '<section class="compare">'
            "<h2>Compare Role runs</h2>"
            f'<div class="meta-row" style="margin-bottom: 0.85rem;">'
            f'<span class="meta-chip">A · run {run.id} · {run.product.value} v{run.version} · {_e(run.title)}</span>'
            f'<span class="meta-chip">B · run {compare_run.id} · {compare_run.product.value} v{compare_run.version} · {_e(compare_run.title)}</span>'
            '</div>'
            '<div class="compare-grid">'
            f'<div class="compare-col"><div class="compare-col-head">A · run {run.id} (v{run.version})</div>'
            f"{_render_role_studio(output, run, run.input_text)}</div>"
            f'<div class="compare-col"><div class="compare-col-head">B · run {compare_run.id} (v{compare_run.version})</div>'
            f"{_render_role_studio(compare_output, compare_run, compare_run.input_text)}</div>"
            "</div>"
            "</section>"
        )
    text = render_compare(run, compare_run)
    return (
        '<section class="compare">'
        "<h2>Compare</h2>"
        f"<pre>{_e(text)}</pre>"
        "</section>"
    )


def _runs_heading(product: Product, project: str) -> str:
    return f"Versions · {_e(project)}"


def _runs_block(
    runs: list[SavedRun],
    current: SavedRun | None,
    product: Product,
    project: str,
) -> str:
    if not runs:
        return '<p class="hint">No runs stored for this project and product.</p>'
    recent = list(reversed(runs))[:RECENT_LIMIT]
    current_id = current.id if current is not None else None
    items = []
    for item in recent:
        is_current = current_id is not None and item.id == current_id
        version_tag_class = "run-version-tag current-version" if is_current else "run-version-tag"
        invalid_chip = '<span class="invalid-chip">Invalid</span> ' if item.invalid else ""
        
        extra = ""
        if (
            current_id is not None
            and item.id != current_id
            and item.product is Product.ROLE
            and product is Product.ROLE
        ):
            extra = (
                f'<a class="compare-btn" href="/?run={current_id}'
                f'&amp;compare={item.id}">Compare</a>'
            )
        items.append(
            "<li>"
            f'<a class="run-link" href="/?run={item.id}">'
            f'<span class="{version_tag_class}">v{item.version}</span> '
            f'{invalid_chip}'
            f'<span>{_e(item.title)}</span> '
            f'<span class="mono-caption">{_e(item.engine.value)}</span>'
            f'</a>'
            f"{extra}"
            "</li>"
        )
    return '<ul class="runs">' + "".join(items) + "</ul>"
