from __future__ import annotations

from html import escape
from pathlib import Path

from enablement_studio.models import (
    CallCoaching,
    LessonCritique,
    Product,
    ProductOutput,
    RoleEnablement,
    SavedRun,
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
    return _fill(
        template,
        {
            "{{body_class}}": _body_class(product),
            "{{role_checked}}": "checked" if product is Product.ROLE else "",
            "{{call_checked}}": "checked" if product is Product.CALL else "",
            "{{critic_checked}}": "checked" if product is Product.CRITIC else "",
            "{{role_bench}}": _bench_class(product, Product.ROLE),
            "{{call_bench}}": _bench_class(product, Product.CALL),
            "{{critic_bench}}": _bench_class(product, Product.CRITIC),
            "{{bench_project}}": _e(project),
            "{{source_heading}}": _e(source_heading),
            "{{source_label}}": _e(source_label),
            "{{project}}": _e(project),
            "{{text}}": _e(text),
            "{{error_block}}": _error_block(error),
            "{{result_block}}": (
                ""
                if compare_run is not None and compare_output is not None and run is not None
                else _result_block(product, output, run, text)
            ),
            "{{compare_block}}": _compare_block(
                run, output, compare_run, compare_output
            ),
            "{{runs_heading}}": _runs_heading(product, project),
            "{{runs_block}}": _runs_block(runs, run, product, project),
        },
    )


def _body_class(product: Product) -> str:
    return f"studio product-{product.value}"


def _bench_class(current: Product, product: Product) -> str:
    return "bench current" if current is product else "bench"


def _source_copy(product: Product) -> tuple[str, str]:
    if product is Product.ROLE:
        return "Source on the table", "Job, SOP, or policy"
    if product is Product.CALL:
        return "Transcript on the table", "Sales or training transcript"
    if product is Product.CRITIC:
        return "Outline on the table", "Lesson outline or storyboard"
    never: Product = product
    raise ValueError(f"unsupported product: {never}")


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
) -> str:
    if output is None:
        if product is Product.ROLE:
            empty = (
                "Nothing on the board yet. Sit a JD, SOP, or policy on the table "
                "and run Role, or load the Harborline example (EXAMPLE DATA)."
            )
        elif product is Product.CALL:
            empty = "Nothing on the board yet. Sit a transcript on the table and run Call."
        elif product is Product.CRITIC:
            empty = "Nothing on the board yet. Sit an outline on the table and run Critic."
        else:
            never: Product = product
            raise ValueError(f"unsupported product: {never}")
        return f'<div class="empty-board"><p>{_e(empty)}</p></div>'
    match output:
        case RoleEnablement():
            return _render_role_studio(output, run, source)
        case CallCoaching():
            product = Product.CALL
            title = output.call_title
            body = _render_call(output)
        case LessonCritique():
            product = Product.CRITIC
            title = output.lesson_title
            body = _render_critic(output)
        case _:
            never: ProductOutput = output
            raise TypeError(f"unsupported output: {type(never)!r}")
    meta = _run_meta(run)
    return (
        '<article class="result">'
        f"<h2>{_e(product_label(product))}</h2>"
        f'<p class="banner">{_e(source_banner(output))}</p>'
        f"<h3>{_e(title)}</h3>"
        f"{meta}"
        f"{body}"
        "</article>"
    )


def _run_meta(run: SavedRun | None) -> str:
    if run is None:
        return ""
    return (
        f'<p class="meta">Run {run.id}  ·  project {_e(run.project)}  ·  '
        f"v{run.version}  ·  engine {_e(run.engine.value)}</p>"
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


def _diagnosis_dl(family: JobFamily, frame: EnablementFrame | None) -> str:
    items = [
        "<div>"
        "<dt>Job family</dt>"
        f'<dd data-family="{_e(family.value)}">{_e(family.value)}</dd>'
        "</div>"
    ]
    if family is JobFamily.ENABLEMENT and frame is not None:
        voice = _FRAME_VOICE[frame]
        items.append(
            "<div>"
            "<dt>Enablement frame</dt>"
            f'<dd data-frame="{_e(frame.value)}">{_e(frame.value)} — {_e(voice)}</dd>'
            "</div>"
        )
    return f'<dl class="diagnosis">{"".join(items)}</dl>'


def _render_role_studio(
    output: RoleEnablement, run: SavedRun | None, source: str
) -> str:
    source_text = _role_source(run, source, output)
    family, frame = _role_diagnosis(output, source_text)
    objects = _render_role(output)
    banner = f'<p class="banner">{_e(source_banner(output))}</p>'
    meta = _run_meta(run)
    diagnosis = _diagnosis_dl(family, frame)
    if output.invalid:
        reasons = "".join(
            f"<li>{_e(reason)}</li>"
            for reason in role_invalid_reasons(output, source_text)
        )
        return (
            '<article class="result studio-failed failed">'
            "<h2>This is not a successful Role module</h2>"
            f"{banner}"
            f"<h3>{_e(output.role_title)}</h3>"
            f"{meta}"
            f"{diagnosis}"
            '<p class="invalid"><strong>Invalid</strong> — stored as a failed Role '
            "run so list, show, and eval can see the miss. It is not a successful "
            "module.</p>"
            f'<ul class="invalid-reasons">{reasons}</ul>'
            "<h3>What the engine produced (not accepted)</h3>"
            f'<div class="failed-artifacts">{objects}</div>'
            "</article>"
        )
    return (
        '<article class="result studio-ok">'
        f"<h2>{_e(output.role_title)}</h2>"
        f"{banner}"
        f"{meta}"
        f"{diagnosis}"
        f"{objects}"
        "</article>"
    )


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
            f'<p class="meta">A  run {run.id}  {run.product.value} v{run.version}  '
            f"{_e(run.title)}  ·  B  run {compare_run.id}  "
            f"{compare_run.product.value} v{compare_run.version}  "
            f"{_e(compare_run.title)}</p>"
            '<div class="compare-grid">'
            f"<div><h3>A · run {run.id}</h3>"
            f"{_render_role_studio(output, run, run.input_text)}</div>"
            f"<div><h3>B · run {compare_run.id}</h3>"
            f"{_render_role_studio(compare_output, compare_run, compare_run.input_text)}"
            "</div>"
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
    return f"This project · {_e(project)} · {product_label(product)}"


def _runs_block(
    runs: list[SavedRun],
    current: SavedRun | None,
    product: Product,
    project: str,
) -> str:
    if not runs:
        return "<p class=\"hint\">No runs stored for this project and product.</p>"
    recent = list(reversed(runs))[:RECENT_LIMIT]
    current_id = current.id if current is not None else None
    items = []
    for item in recent:
        title = f"[invalid] {item.title}" if item.invalid else item.title
        extra = ""
        if (
            current_id is not None
            and item.id != current_id
            and item.product is Product.ROLE
            and product is Product.ROLE
        ):
            extra = (
                f' <a class="compare-link" href="/?run={current_id}'
                f'&amp;compare={item.id}">Compare</a>'
            )
        items.append(
            "<li>"
            f'<a href="/?run={item.id}">'
            f"{item.id} · {_e(item.product.value)} · v{item.version} · "
            f"{_e(item.engine.value)} · {_e(item.project)} — {_e(title)}"
            f"</a>{extra}</li>"
        )
    form = _compare_form(runs, current, product, project)
    return '<ul class="runs">' + "".join(items) + "</ul>" + form


def _compare_form(
    runs: list[SavedRun],
    current: SavedRun | None,
    product: Product,
    project: str,
) -> str:
    if product is not Product.ROLE:
        return ""
    role_runs = [item for item in runs if item.product is Product.ROLE]
    if len(role_runs) < 2:
        return ""
    default_run = current.id if current is not None else role_runs[-1].id
    return (
        '<form class="compare-form" method="get" action="/">'
        f'<input type="hidden" name="project" value="{_e(project)}">'
        '<input type="hidden" name="product" value="role">'
        "<label>Compare"
        f'<select name="run">{_select_options(role_runs, default_run)}</select>'
        "</label>"
        "<label>with"
        f'<select name="compare">{_select_options(role_runs, None)}</select>'
        "</label>"
        '<button type="submit">Compare</button>'
        "</form>"
    )


def _select_options(runs: list[SavedRun], selected_id: int | None) -> str:
    pieces = []
    for item in reversed(runs):
        selected = " selected" if selected_id is not None and item.id == selected_id else ""
        label = f"{item.id} · v{item.version} — {item.title}"
        pieces.append(f'<option value="{item.id}"{selected}>{_e(label)}</option>')
    return "".join(pieces)


def _render_role(output: RoleEnablement) -> str:
    nodes = "".join(
        "<li>"
        f'<span class="level">{_e(node.level)}</span> '
        f"<strong>{_e(node.name)}</strong>"
        f"<p>{_e(node.detail)}</p>"
        "</li>"
        for node in output.skill_graph.nodes
    )
    if not nodes:
        nodes = "<li>No skill nodes.</li>"
    edges = ""
    if output.skill_graph.edges:
        edge_items = "".join(
            f"<li>{_e(edge.source)} {_e(edge.relation)} {_e(edge.target)}</li>"
            for edge in output.skill_graph.edges
        )
        edges = f'<p class="edges-label">Sequence</p><ul class="edges">{edge_items}</ul>'
    objectives = "".join(
        "<li>"
        f"<strong>{_e(item.id)}</strong> {_e(item.statement)}"
        f'<p class="measure">Measure: {_e(item.measure)}</p>'
        "</li>"
        for item in output.objectives
    )
    if not objectives:
        objectives = "<li>No objectives.</li>"
    outline = "".join(
        "<li>"
        f'<span class="minutes">{_e(block.minutes)}</span> '
        f"<strong>{_e(block.title)}</strong>"
        f"<p>{_e(block.description)}</p>"
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
            f"<li><p class=\"prompt\">{index}. {_e(item.question)}</p>"
            f'<ul class="choices">{choices}</ul>'
            f'<p class="why">Why: {_e(item.rationale)}</p></li>'
        )
    return (
        '<section class="skill-graph object">'
        "<h3>SKILL GRAPH</h3>"
        f'<ol class="nodes">{nodes}</ol>{edges}'
        "</section>"
        '<section class="objectives object">'
        "<h3>LEARNING OBJECTIVES</h3>"
        f"<ol>{objectives}</ol>"
        "</section>"
        '<section class="outline object">'
        "<h3>30-MINUTE MODULE</h3>"
        f'<ol class="timeline">{outline}</ol>'
        "</section>"
        f'<section class="practice object">'
        f"<h3>PRACTICE — {_e(output.practice.title)}</h3>"
        f"<p class=\"scenario\">Scenario: {_e(output.practice.scenario)}</p>"
        f"<ol>{steps}</ol>"
        "<p>Success:</p>"
        f"<ul>{success}</ul>"
        "</section>"
        '<section class="quiz object">'
        "<h3>APPLICATION QUIZ</h3>"
        f"<ol>{''.join(quiz)}</ol>"
        "</section>"
    )


def _render_call(output: CallCoaching) -> str:
    signals = "".join(f"<li>{_e(signal)}</li>" for signal in output.signals)
    speakers = ""
    if output.speakers:
        speakers = f"<p>Speakers: {_e(', '.join(output.speakers))}</p>"
    notes = "".join(
        f"<li>[{_e(note.audience)}] {_e(note.headline)}<br>{_e(note.body)}</li>"
        for note in output.notes
    )
    fix = output.enablement_fix
    return (
        "<h3>SIGNALS</h3>"
        f"<ul>{signals}</ul>"
        f"{speakers}"
        "<h3>AGENT NOTES</h3>"
        f"<ul>{notes}</ul>"
        "<h3>ENABLEMENT FIX</h3>"
        f"<p><strong>{_e(fix.title)}</strong></p>"
        f"<p>Problem: {_e(fix.problem)}</p>"
        f"<p>Fix: {_e(fix.fix)}</p>"
        f"<p>Measure: {_e(fix.measure)}</p>"
    )


def _render_critic(output: LessonCritique) -> str:
    scores = output.scores
    findings = "".join(
        f"<li>[{_e(finding.severity)}] {_e(finding.area)}: {_e(finding.detail)}</li>"
        for finding in output.findings
    )
    rewrite = output.rewrite
    return (
        "<h3>ALIGNMENT SCORES (1–5)</h3>"
        "<ul>"
        f"<li>objective → clarity: {_e(scores.objective_clarity)}</li>"
        f"<li>objective → activity: {_e(scores.activity_alignment)}</li>"
        f"<li>objective → assessment: {_e(scores.assessment_alignment)}</li>"
        f"<li>overall: {_e(scores.overall)}</li>"
        "</ul>"
        "<h3>FINDINGS</h3>"
        f"<ul>{findings}</ul>"
        f"<h3>REWRITE — weakest part: {_e(rewrite.target)}</h3>"
        f"<p>{_e(rewrite.reason)}</p>"
        f"<p>{_e(rewrite.replacement)}</p>"
    )
