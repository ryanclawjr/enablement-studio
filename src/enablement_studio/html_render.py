from __future__ import annotations

import math
from html import escape
from pathlib import Path
from urllib.parse import urlencode

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
from enablement_studio.render import render_compare, source_banner
from enablement_studio.role.family import (
    EnablementFrame,
    JobFamily,
    classify_enablement_frame,
    classify_job_family,
)
from enablement_studio.role.title_swap import role_invalid_reasons
from enablement_studio.textutil import extract_title

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATE_PATH = TEMPLATE_DIR / "page.html"
RECENT_LIMIT = 20
LOCAL_STATUS_LINE = "this machine · 127.0.0.1 · offline"

ROLE_STEPS = ("source", "graph", "objectives", "outline", "practice", "quiz")
STEP_LABELS = {
    "source": "Source",
    "graph": "Graph",
    "objectives": "Objectives",
    "outline": "Outline",
    "practice": "Practice",
    "quiz": "Quiz",
}

_FRAME_VOICE = {
    EnablementFrame.DESIGNER: "the learner designs instruction",
    EnablementFrame.EDUCATOR: "the learner teaches or coaches practitioners",
    EnablementFrame.PARTNER: "the learner enables a field team",
}


def _e(text: object) -> str:
    return escape(str(text), quote=True)


def role_path(
    run_id: int | str | None = None,
    step: str | None = None,
    *,
    compare: int | str | None = None,
    project: str | None = None,
    demo: bool = False,
) -> str:
    params: dict[str, str] = {}
    if run_id is not None:
        params["run"] = str(run_id)
    if step:
        params["step"] = step
    if compare is not None:
        params["compare"] = str(compare)
    if project:
        params["project"] = project
    if demo:
        params["demo"] = "1"
    if not params:
        return "/role"
    return "/role?" + urlencode(params)


def resolve_role_step(
    step: str | None,
    *,
    run: SavedRun | None,
    output: ProductOutput | None,
) -> str:
    requested = (step or "").strip().lower()
    has_module = isinstance(output, RoleEnablement)
    if requested not in ROLE_STEPS:
        return "graph" if has_module else "source"
    if has_module and output.invalid and requested not in {"source", "graph"}:
        return "graph"
    return requested


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
    step: str | None = None,
    notice: str | None = None,
    status_line: str = LOCAL_STATUS_LINE,
    public: bool = False,
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    resolved = resolve_role_step(step, run=run, output=output)
    has_key = llm_configured()
    comparing = compare_run is not None and compare_output is not None and run is not None
    body_class = f"product-role step-{resolved}"
    if comparing:
        body_class += " comparing"
    if public:
        body_class += " public"
    return _fill(
        template,
        {
            "{{page_title}}": _e(_page_title(resolved)),
            "{{body_class}}": _e(body_class),
            "{{project}}": _e(project),
            "{{notice_block}}": _notice_block(notice),
            "{{error_block}}": _error_block(error),
            "{{step_board}}": (
                ""
                if comparing
                else _step_board(
                    resolved, text, project, output, run, has_key, public=public
                )
            ),
            "{{compare_block}}": _compare_block(
                run, output, compare_run, compare_output
            ),
            "{{step_nav}}": "" if comparing else _step_nav(resolved, run, output),
            "{{version_dots}}": _version_dots(runs, run, product, project),
            "{{object_row}}": _object_row(resolved, run, output),
            "{{status_pill}}": _status_pill(status_line, public=public),
        },
    )


def _page_title(step: str) -> str:
    if step == "source":
        return "Role"
    return f"Role · {STEP_LABELS[step]}"


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _status_pill(status_line: str, *, public: bool) -> str:
    if public or not status_line.strip():
        return ""
    return f'<p class="status-pill">{_e(status_line)}</p>'


def _object_brief(
    name: str,
    run: SavedRun | None,
    output: ProductOutput | None,
) -> str:
    if not isinstance(output, RoleEnablement):
        return ""
    if output.invalid and name not in {"source", "graph"}:
        return ""
    if name == "source":
        raw = ""
        if run is not None and run.input_text.strip():
            raw = run.input_text
        elif output.role_title.strip():
            raw = output.role_title
        return _clip(raw, 42)
    if name == "graph":
        count = len(output.skill_graph.nodes)
        return f"{count} skills" if count else ""
    if name == "objectives":
        if not output.objectives:
            return ""
        return _clip(output.objectives[0].statement, 42)
    if name == "outline":
        if not output.outline:
            return ""
        block = output.outline[0]
        return _clip(f"{block.minutes} · {block.title}", 42)
    if name == "practice":
        if not output.practice.scenario.strip():
            return ""
        return _clip(output.practice.scenario, 42)
    if name == "quiz":
        count = len(output.quiz)
        return f"{count} items" if count else ""
    never: str = name
    raise ValueError(f"unsupported Role step: {never}")


def _object_row(step: str, run: SavedRun | None, output: ProductOutput | None) -> str:
    current_idx = ROLE_STEPS.index(step)
    cells: list[str] = []
    for index, name in enumerate(ROLE_STEPS):
        label = STEP_LABELS[name]
        if index == current_idx:
            state = "current"
        elif index < current_idx:
            state = "past"
        else:
            state = "future"
        current_attr = ' aria-current="step"' if state == "current" else ""
        brief = _object_brief(name, run, output)
        brief_html = (
            f'<span class="object-brief">{_e(brief)}</span>' if brief else ""
        )
        inner = f'<span class="object-name">{_e(label)}</span>{brief_html}'
        href = _e(role_path(None if run is None else run.id, name))
        cells.append(
            f'<th scope="col">'
            f'<a class="object-cell {state}" href="{href}"{current_attr}>{inner}</a>'
            "</th>"
        )
    return f"<tr>{''.join(cells)}</tr>"


def _source_form(text: str, project: str, has_key: bool, *, public: bool) -> str:
    llm = ""
    if not public:
        llm_disabled = "" if has_key else " disabled"
        llm = (
            f'<button class="llm" type="submit" name="action" value="llm"'
            f"{llm_disabled}>LLM</button>"
        )
    return (
        '<form method="post" action="/" class="role-form">'
        '<input type="hidden" name="product" value="role">'
        f'<input type="hidden" name="project" value="{_e(project)}" autocomplete="off">'
        f'<textarea name="text" spellcheck="false" aria-label="Job, SOP, or policy" '
        f'placeholder="Paste a job or SOP...">{_e(text)}</textarea>'
        '<div class="actions">'
        '<button class="run" type="submit" name="action" value="run">Run</button>'
        '<button class="example" type="submit" name="action" value="demo">'
        'Harborline <span class="example-tag">EXAMPLE DATA</span></button>'
        f"{llm}"
        "</div>"
        "</form>"
    )


def _object_class(step: str) -> str:
    if step == "graph":
        return "skill-graph"
    if step in ROLE_STEPS:
        return step
    never: str = step
    raise ValueError(f"unsupported Role step: {never}")


def _empty_object(step: str) -> str:
    label = STEP_LABELS[step]
    return (
        f'<div class="step-view" data-step="{_e(step)}">'
        f'<section class="{_object_class(step)} object is-empty">'
        f"<h3>{_e(label)}</h3>"
        "</section>"
        "</div>"
    )


def _step_board(
    step: str,
    text: str,
    project: str,
    output: ProductOutput | None,
    run: SavedRun | None,
    has_key: bool,
    *,
    public: bool,
) -> str:
    if step == "source":
        return (
            f'<div class="step-view" data-step="source">'
            f"{_source_form(text, project, has_key, public=public)}"
            "</div>"
        )
    if not isinstance(output, RoleEnablement):
        return _empty_object(step)
    inner = _role_step_inner(step, output, run, text)
    return f'<div class="step-view" data-step="{_e(step)}">{inner}</div>'


def _role_step_inner(
    step: str, output: RoleEnablement, run: SavedRun | None, source: str
) -> str:
    if output.invalid:
        return _render_invalid_graph(output, run, source)
    header = _role_meta_header(output, run, source, heading=output.role_title)
    body = _role_step_object(step, output)
    return header + body


def _role_step_object(step: str, output: RoleEnablement) -> str:
    if step == "graph":
        return _render_role_graph(output)
    if step == "objectives":
        return _render_role_objectives(output)
    if step == "outline":
        return _render_role_outline(output)
    if step == "practice":
        return _render_role_practice(output)
    if step == "quiz":
        return _render_role_quiz(output)
    if step == "source":
        return ""
    never: str = step
    raise ValueError(f"unsupported Role step: {never}")


def _step_nav(step: str, run: SavedRun | None, output: ProductOutput | None) -> str:
    current_idx = ROLE_STEPS.index(step)
    parts: list[str] = []
    if step != "source" and run is not None and current_idx > 0:
        prev = ROLE_STEPS[current_idx - 1]
        parts.append(
            f'<a class="btn-action back" href="{_e(role_path(run.id, prev))}">Back</a>'
        )
    invalid = isinstance(output, RoleEnablement) and output.invalid
    if run is not None and not invalid and current_idx + 1 < len(ROLE_STEPS):
        nxt = ROLE_STEPS[current_idx + 1]
        parts.append(
            f'<a class="btn-action continue" href="{_e(role_path(run.id, nxt))}">Continue</a>'
        )
    elif step == "quiz":
        parts.append('<a class="btn-action versions-link" href="#versions">Versions</a>')
    if not parts:
        return ""
    return f'<nav class="step-nav">{"".join(parts)}</nav>'


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


def _notice_block(notice: str | None) -> str:
    if not notice:
        return ""
    return f'<p class="notice" role="status">{_e(notice)}</p>'


def _error_block(error: str | None) -> str:
    if not error:
        return ""
    return f'<p class="error" role="alert">{_e(error)}</p>'


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


def _role_meta_header(
    output: RoleEnablement,
    run: SavedRun | None,
    source: str,
    *,
    heading: str,
) -> str:
    source_text = _role_source(run, source, output)
    family, frame = _role_diagnosis(output, source_text)
    banner_text = source_banner(output)
    meta_chips = [
        f'<span class="meta-chip"><span class="meta-chip-label">Family</span> '
        f'<strong data-family="{_e(family.value)}">{_e(family.value)}</strong></span>'
    ]
    if family is JobFamily.ENABLEMENT and frame is not None:
        voice = _FRAME_VOICE[frame]
        meta_chips.append(
            f'<span class="meta-chip"><span class="meta-chip-label">Frame</span> '
            f'<strong data-frame="{_e(frame.value)}">{_e(frame.value)}</strong> — {_e(voice)}</span>'
        )
    return (
        '<header class="module-header">'
        f"<h2>{_e(heading)}</h2>"
        f'<div class="meta-row">{" ".join(meta_chips)}</div>'
        f'<p class="source-note-banner">{_e(banner_text)}</p>'
        "</header>"
    )


def _render_invalid_graph(
    output: RoleEnablement, run: SavedRun | None, source: str
) -> str:
    source_text = _role_source(run, source, output)
    reasons = "".join(
        f"<li>{_e(reason)}</li>" for reason in role_invalid_reasons(output, source_text)
    )
    header = _role_meta_header(output, run, source, heading="Invalid module")
    return (
        '<article class="result studio-failed">'
        f"{header}"
        f"<h3>{_e(output.role_title)}</h3>"
        '<div class="invalid-banner">'
        "<strong>Not accepted</strong> — stored as a failed Role run so list, show, and eval can see the miss. "
        "It is not a successful module."
        f'<ul class="invalid-reasons">{reasons}</ul>'
        "</div>"
        '<p class="hint">What the engine produced (not accepted)</p>'
        f'<div class="failed-artifacts">{_render_role_graph(output)}</div>'
        "</article>"
    )


def _render_role_studio(
    output: RoleEnablement, run: SavedRun | None, source: str
) -> str:
    if output.invalid:
        return _render_invalid_graph(output, run, source)
    header = _role_meta_header(output, run, source, heading=output.role_title)
    return (
        '<article class="result studio-ok">'
        f"{header}"
        f"{_render_role_objects(output)}"
        "</article>"
    )


def _render_call_studio(output: CallCoaching, run: SavedRun | None) -> str:
    version_str = f"v{run.version}" if run is not None else "v1"
    engine_str = run.engine.value if run is not None else "offline"
    run_id_str = f"run {run.id} · " if run is not None else ""
    project_str = f"project {_e(run.project)} · " if run is not None else ""
    meta_html = (
        '<div class="meta-row">'
        f'<span class="meta-chip">{_e(run_id_str)}{project_str}{_e(version_str)} · engine {_e(engine_str)}</span>'
        "</div>"
    )
    banner_html = f'<p class="source-note-banner">{_e(source_banner(output))}</p>'
    return (
        '<article class="result studio-ok">'
        '<header class="module-header">'
        f"<h2>{_e(output.call_title)}</h2>"
        f"{meta_html}"
        f"{banner_html}"
        "</header>"
        f"{_render_call_objects(output)}"
        "</article>"
    )


def _render_critic_studio(output: LessonCritique, run: SavedRun | None) -> str:
    version_str = f"v{run.version}" if run is not None else "v1"
    engine_str = run.engine.value if run is not None else "offline"
    run_id_str = f"run {run.id} · " if run is not None else ""
    project_str = f"project {_e(run.project)} · " if run is not None else ""
    meta_html = (
        '<div class="meta-row">'
        f'<span class="meta-chip">{_e(run_id_str)}{project_str}{_e(version_str)} · engine {_e(engine_str)}</span>'
        "</div>"
    )
    banner_html = f'<p class="source-note-banner">{_e(source_banner(output))}</p>'
    return (
        '<article class="result studio-ok">'
        '<header class="module-header">'
        f"<h2>{_e(output.lesson_title)}</h2>"
        f"{meta_html}"
        f"{banner_html}"
        "</header>"
        f"{_render_critic_objects(output)}"
        "</article>"
    )


def _level_abbr(level: str) -> str:
    if level == "foundation":
        return "L1"
    if level == "core":
        return "L2"
    return "L3"


def _edge_label_point(
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
    width: float,
    height: float,
) -> tuple[float, float]:
    dx = end_x - start_x
    dy = end_y - start_y
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    if ny > 0:
        nx = -nx
        ny = -ny
    mid_x = (start_x + end_x) / 2 + nx * 16
    mid_y = (start_y + end_y) / 2 + ny * 16
    return (
        min(max(mid_x, 18.0), width - 18.0),
        min(max(mid_y, 14.0), height - 8.0),
    )


def _graph_figure(nodes: list[SkillNode], edges: list[SkillEdge]) -> str:
    if not nodes:
        return '<p class="empty-object">No skill nodes.</p>'
    cols = 3 if len(nodes) > 2 else max(1, len(nodes))
    node_w = 252
    node_h = 88
    gap_x = 44
    gap_y = 80
    pad_x = 28
    pad_y = 36
    positions: dict[str, tuple[float, float]] = {}
    for index, node in enumerate(nodes):
        row, col = divmod(index, cols)
        positions[node.id] = (
            pad_x + col * (node_w + gap_x),
            pad_y + row * (node_h + gap_y),
        )
    rows = (len(nodes) + cols - 1) // cols
    width = pad_x * 2 + cols * node_w + max(0, cols - 1) * gap_x
    height = pad_y * 2 + rows * node_h + max(0, rows - 1) * gap_y
    parts = [
        f'<div class="graph-stage" data-graph="relations" style="width:{width}px;min-height:{height}px">',
        f'<svg class="graph-svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">',
        '<defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">',
        '<path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#757575"/></marker></defs>',
    ]
    for edge in edges:
        if edge.source not in positions or edge.target not in positions:
            continue
        x1, y1 = positions[edge.source]
        x2, y2 = positions[edge.target]
        start_x = x1 + node_w / 2
        start_y = y1 + node_h / 2
        end_x = x2 + node_w / 2
        end_y = y2 + node_h / 2
        parts.append(
            f'<line class="graph-edge" x1="{start_x:.1f}" y1="{start_y:.1f}" '
            f'x2="{end_x:.1f}" y2="{end_y:.1f}" stroke="#757575" stroke-width="1.5" '
            'marker-end="url(#graph-arrow)" />'
        )
        mid_x, mid_y = _edge_label_point(
            start_x, start_y, end_x, end_y, width, height
        )
        parts.append(
            f'<text class="graph-edge-label" x="{mid_x:.1f}" y="{mid_y:.1f}" '
            'text-anchor="middle" fill="#757575" font-size="11" '
            'stroke="#1d1d25" stroke-width="4" paint-order="stroke" '
            f'font-family="Instrument Sans, ui-sans-serif, sans-serif">{_e(edge.relation)}</text>'
        )
    parts.append("</svg><ul class=\"graph-nodes\">")
    for node in nodes:
        x, y = positions[node.id]
        parts.append(
            f'<li class="graph-node" data-node="{_e(node.id)}" '
            f'style="left:{x:.0f}px;top:{y:.0f}px;width:{node_w}px;min-height:{node_h}px" '
            f'title="{_e(node.detail)}">'
            f'<span class="mono-caption">{_level_abbr(node.level)}</span>'
            f"<strong>{_e(node.name)}</strong>"
            "</li>"
        )
    parts.append("</ul></div>")
    return "".join(parts)


def _render_role_graph(output: RoleEnablement) -> str:
    return (
        '<section class="skill-graph object">'
        "<h3>Graph</h3>"
        f"{_graph_figure(output.skill_graph.nodes, output.skill_graph.edges)}"
        "</section>"
    )


def _render_role_objectives(output: RoleEnablement) -> str:
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
    return (
        '<section class="objectives object">'
        '<h3>Objectives <span class="object-tag">Measurable</span></h3>'
        f'<ol class="objectives-list">{objectives}</ol>'
        "</section>"
    )


def _render_role_outline(output: RoleEnablement) -> str:
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
    return (
        '<section class="outline object">'
        '<h3>Outline <span class="object-tag">30 Min</span></h3>'
        f'<ol class="timeline">{outline}</ol>'
        "</section>"
    )


def _render_role_practice(output: RoleEnablement) -> str:
    steps = "".join(f"<li>{_e(step)}</li>" for step in output.practice.instructions)
    success = "".join(f"<li>{_e(item)}</li>" for item in output.practice.success_criteria)
    return (
        '<section class="practice object">'
        f'<h3>Practice <span class="object-tag">{_e(output.practice.title)}</span></h3>'
        '<div class="scenario-card">'
        f'<div class="scenario-section"><span class="scenario-label">Situation</span><p class="scenario-text">{_e(output.practice.scenario)}</p></div>'
        f'<div class="scenario-section"><span class="scenario-label">Steps</span><ol class="practice-steps">{steps}</ol></div>'
        f'<div class="scenario-section"><span class="scenario-label">Success</span><ul class="practice-success">{success}</ul></div>'
        "</div>"
        "</section>"
    )


def _render_role_quiz(output: RoleEnablement) -> str:
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
            "<summary>Answer &amp; rationale</summary>"
            f'<div class="quiz-details-content"><strong>Answer:</strong> {_e(item.answer)}<br><strong>Why:</strong> {_e(item.rationale)}</div>'
            "</details>"
            "</li>"
        )
    return (
        '<section class="quiz object">'
        '<h3>Quiz <span class="object-tag">Application</span></h3>'
        f'<ol class="quiz-list">{"".join(quiz)}</ol>'
        "</section>"
    )


def _render_role_objects(output: RoleEnablement) -> str:
    return (
        _render_role_graph(output)
        + _render_role_objectives(output)
        + _render_role_outline(output)
        + _render_role_practice(output)
        + _render_role_quiz(output)
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
        "</div>"
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
        f"<p><strong>Fix:</strong> {_e(fix.fix)}</p>"
        f'<p class="mono-caption">Measure: {_e(fix.measure)}</p>'
        "</section>"
    )


def _render_critic_objects(output: LessonCritique) -> str:
    scores = output.scores
    findings = "".join(
        f'<li><span class="mono-caption">[{_e(finding.severity)}]</span> <strong>{_e(finding.area)}:</strong> {_e(finding.detail)}</li>'
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
        "</div>"
        "</section>"
        '<section class="object">'
        '<h3>Findings <span class="object-tag">Review</span></h3>'
        f'<ul class="practice-steps">{findings}</ul>'
        "</section>"
        '<section class="object">'
        f'<h3>Rewrite <span class="object-tag">Weakest: {_e(rewrite.target)}</span></h3>'
        f'<div class="practice-scenario"><strong>Reason:</strong> {_e(rewrite.reason)}</div>'
        f"<p>{_e(rewrite.replacement)}</p>"
        "</section>"
    )


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
            '<div class="meta-row" style="margin-bottom: 0.85rem;">'
            f'<span class="meta-chip">A · run {run.id} · {run.product.value} v{run.version} · {_e(run.title)}</span>'
            f'<span class="meta-chip">B · run {compare_run.id} · {compare_run.product.value} v{compare_run.version} · {_e(compare_run.title)}</span>'
            "</div>"
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


def _version_dots(
    runs: list[SavedRun],
    current: SavedRun | None,
    product: Product,
    project: str,
) -> str:
    recent = list(reversed(runs))[:RECENT_LIMIT]
    current_id = current.id if current is not None else None
    items = []
    for item in recent:
        is_current = current_id is not None and item.id == current_id
        cls = "version-dot current" if is_current else "version-dot"
        current_attr = ' aria-current="true"' if is_current else ""
        mark = " Invalid" if item.invalid else ""
        title = f"v{item.version} {_e(item.title)} · {_e(item.engine.value)}{mark}"
        items.append(
            f'<a class="{cls}" href="{_e(role_path(item.id))}"{current_attr} title="{title}">'
            f"{item.version}"
            "</a>"
        )
    return (
        f'<nav class="version-dots" id="versions" aria-label="Versions">'
        f"{''.join(items)}"
        "</nav>"
    )
