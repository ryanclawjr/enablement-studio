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
from enablement_studio.render import product_label, source_banner

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "page.html"
RECENT_LIMIT = 20


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
) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return _fill(
        template,
        {
            "{{role_checked}}": "checked" if product is Product.ROLE else "",
            "{{call_checked}}": "checked" if product is Product.CALL else "",
            "{{critic_checked}}": "checked" if product is Product.CRITIC else "",
            "{{project}}": _e(project),
            "{{text}}": _e(text),
            "{{error_block}}": _error_block(error),
            "{{result_block}}": _result_block(output, run),
            "{{runs_block}}": _runs_block(runs),
        },
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


def _result_block(output: ProductOutput | None, run: SavedRun | None) -> str:
    if output is None:
        return ""
    match output:
        case RoleEnablement():
            product = Product.ROLE
            title = output.role_title
            body = _render_role(output)
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
    invalid = ""
    if isinstance(output, RoleEnablement) and output.invalid:
        invalid = '<p class="invalid"><strong>INVALID</strong> — not a successful Role run.</p>'
    meta = ""
    if run is not None:
        meta = (
            f'<p class="meta">Run {run.id}  ·  project {_e(run.project)}  ·  '
            f"v{run.version}  ·  engine {_e(run.engine.value)}</p>"
        )
    return (
        '<article class="result">'
        f"<h2>{_e(product_label(product))}</h2>"
        f'<p class="banner">{_e(source_banner(output))}</p>'
        f"<h3>{_e(title)}</h3>"
        f"{invalid}"
        f"{meta}"
        f"{body}"
        "</article>"
    )


def _runs_block(runs: list[SavedRun]) -> str:
    if not runs:
        return "<p class=\"hint\">No runs stored.</p>"
    recent = list(reversed(runs))[:RECENT_LIMIT]
    items = []
    for item in recent:
        title = f"[invalid] {item.title}" if item.invalid else item.title
        items.append(
            "<li>"
            f'<a href="/?run={item.id}">'
            f"{item.id} · {_e(item.product.value)} · v{item.version} · "
            f"{_e(item.engine.value)} · {_e(item.project)} — {_e(title)}"
            "</a></li>"
        )
    return '<ul class="runs">' + "".join(items) + "</ul>"


def _render_role(output: RoleEnablement) -> str:
    nodes = "".join(
        f"<li>[{_e(node.level)}] {_e(node.name)} — {_e(node.detail)}</li>"
        for node in output.skill_graph.nodes
    )
    edges = ""
    if output.skill_graph.edges:
        edge_items = "".join(
            f"<li>{_e(edge.source)} -{_e(edge.relation)}-&gt; {_e(edge.target)}</li>"
            for edge in output.skill_graph.edges
        )
        edges = f"<p>edges</p><ul>{edge_items}</ul>"
    objectives = "".join(
        f"<li>{_e(item.id)}. {_e(item.statement)}<br>Measure: {_e(item.measure)}</li>"
        for item in output.objectives
    )
    outline = "".join(
        f"<li>{_e(block.minutes)} {_e(block.title)} — {_e(block.description)}</li>"
        for block in output.outline
    )
    steps = "".join(f"<li>{_e(step)}</li>" for step in output.practice.instructions)
    success = "".join(f"<li>{_e(item)}</li>" for item in output.practice.success_criteria)
    quiz = []
    for index, item in enumerate(output.quiz, start=1):
        choices = "".join(
            f"<li>{'* ' if choice == item.answer else ''}{_e(choice)}</li>"
            for choice in item.choices
        )
        quiz.append(
            f"<li>{index}. {_e(item.question)}<ul>{choices}</ul>"
            f"Why: {_e(item.rationale)}</li>"
        )
    return (
        "<h3>SKILL GRAPH</h3>"
        f"<ul>{nodes}</ul>{edges}"
        "<h3>LEARNING OBJECTIVES</h3>"
        f"<ul>{objectives}</ul>"
        "<h3>30-MINUTE MODULE</h3>"
        f"<ul>{outline}</ul>"
        f"<h3>PRACTICE — {_e(output.practice.title)}</h3>"
        f"<p>Scenario: {_e(output.practice.scenario)}</p>"
        f"<ul>{steps}</ul>"
        "<p>Success:</p>"
        f"<ul>{success}</ul>"
        "<h3>QUIZ</h3>"
        f"<ol>{''.join(quiz)}</ol>"
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
        f"<li>objective → clarity: {scores.objective_clarity}</li>"
        f"<li>objective → activity: {scores.activity_alignment}</li>"
        f"<li>objective → assessment: {scores.assessment_alignment}</li>"
        f"<li>overall: {scores.overall}</li>"
        "</ul>"
        "<h3>FINDINGS</h3>"
        f"<ul>{findings}</ul>"
        f"<h3>REWRITE — weakest part: {_e(rewrite.target)}</h3>"
        f"<p>{_e(rewrite.reason)}</p>"
        f"<p>{_e(rewrite.replacement)}</p>"
    )
