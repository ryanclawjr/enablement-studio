from __future__ import annotations

from enablement_studio.models import (
    CallCoaching,
    LessonCritique,
    Product,
    ProductOutput,
    RoleEnablement,
    SavedRun,
)


def render_output(output: ProductOutput, run: SavedRun | None = None) -> str:
    header = _header(output, run)
    match output:
        case RoleEnablement():
            body = _render_role(output)
        case CallCoaching():
            body = _render_call(output)
        case LessonCritique():
            body = _render_critic(output)
        case _:
            never: ProductOutput = output
            raise TypeError(f"unsupported output: {type(never)!r}")
    return f"{header}\n\n{body}".rstrip() + "\n"


def render_run_list(runs: list[SavedRun]) -> str:
    if not runs:
        return "No runs stored.\n"
    lines = [
        f"{'ID':<5} {'PRODUCT':<8} {'VER':<4} {'ENGINE':<8} {'PROJECT':<12} TITLE",
        "-" * 72,
    ]
    for run in runs:
        title = f"[invalid] {run.title}" if run.invalid else run.title
        lines.append(
            f"{run.id:<5} {run.product.value:<8} {run.version:<4} "
            f"{run.engine.value:<8} {run.project:<12} {title}"
        )
    return "\n".join(lines) + "\n"


def render_compare(left: SavedRun, right: SavedRun) -> str:
    lines = [
        "Compare runs",
        f"A  run {left.id}  {left.product.value} v{left.version}  {left.title}",
        f"B  run {right.id}  {right.product.value} v{right.version}  {right.title}",
    ]
    if left.product != right.product:
        lines.append("Products differ; showing titles only.")
        return "\n".join(lines) + "\n"
    left_result = left.artifacts.get("result") or {}
    right_result = right.artifacts.get("result") or {}
    for key in sorted(set(left_result) | set(right_result)):
        if key in {"source_note", "example_data"}:
            continue
        a = left_result.get(key)
        b = right_result.get(key)
        if a == b:
            continue
        lines.append(f"\n[{key}]")
        lines.append(f"  A: {_brief(a)}")
        lines.append(f"  B: {_brief(b)}")
    if len(lines) == 3:
        lines.append("No field-level differences in stored results.")
    return "\n".join(lines) + "\n"


def product_label(product: Product) -> str:
    labels = {
        Product.ROLE: "Role → Enablement",
        Product.CALL: "Call → Coach",
        Product.CRITIC: "Lesson critic",
    }
    return labels[product]


def source_banner(output: ProductOutput) -> str:
    if output.example_data:
        return "EXAMPLE DATA — fictional sample. Not from a live employer or customer."
    return output.source_note


def _header(output: ProductOutput, run: SavedRun | None) -> str:
    if isinstance(output, RoleEnablement):
        product = Product.ROLE
        title = output.role_title
    elif isinstance(output, CallCoaching):
        product = Product.CALL
        title = output.call_title
    else:
        product = Product.CRITIC
        title = output.lesson_title
    banner = source_banner(output)
    lines = [f"Enablement Studio — {product_label(product)}", banner, title]
    if isinstance(output, RoleEnablement) and output.invalid:
        lines.append("INVALID — not a successful Role run.")
    if run is not None:
        lines.append(
            f"Run {run.id}  ·  project {run.project}  ·  v{run.version}  ·  {run.engine.value}"
        )
    return "\n".join(lines)


def _render_role(output: RoleEnablement) -> str:
    lines = ["SKILL GRAPH"]
    for node in output.skill_graph.nodes:
        lines.append(f"  [{node.level}] {node.name} — {node.detail}")
    if output.skill_graph.edges:
        lines.append("  edges:")
        for edge in output.skill_graph.edges:
            lines.append(f"    {edge.source} -{edge.relation}-> {edge.target}")
    lines.append("\nLEARNING OBJECTIVES")
    for item in output.objectives:
        lines.append(f"  {item.id}. {item.statement}")
        lines.append(f"     Measure: {item.measure}")
    lines.append("\n30-MINUTE MODULE")
    for block in output.outline:
        lines.append(f"  {block.minutes}  {block.title}")
        lines.append(f"      {block.description}")
    lines.append(f"\nPRACTICE — {output.practice.title}")
    lines.append(f"  Scenario: {output.practice.scenario}")
    for step in output.practice.instructions:
        lines.append(f"  - {step}")
    lines.append("  Success:")
    for item in output.practice.success_criteria:
        lines.append(f"  - {item}")
    lines.append("\nQUIZ")
    for index, item in enumerate(output.quiz, start=1):
        lines.append(f"  {index}. {item.question}")
        for choice in item.choices:
            mark = "*" if choice == item.answer else " "
            lines.append(f"     [{mark}] {choice}")
        lines.append(f"     Why: {item.rationale}")
    return "\n".join(lines)


def _render_call(output: CallCoaching) -> str:
    lines = ["SIGNALS"]
    for signal in output.signals:
        lines.append(f"  - {signal}")
    if output.speakers:
        lines.append("Speakers: " + ", ".join(output.speakers))
    lines.append("\nAGENT NOTES")
    for note in output.notes:
        lines.append(f"  [{note.audience}] {note.headline}")
        lines.append(f"      {note.body}")
    fix = output.enablement_fix
    lines.append("\nENABLEMENT FIX")
    lines.append(f"  {fix.title}")
    lines.append(f"  Problem: {fix.problem}")
    lines.append(f"  Fix: {fix.fix}")
    lines.append(f"  Measure: {fix.measure}")
    return "\n".join(lines)


def _render_critic(output: LessonCritique) -> str:
    scores = output.scores
    lines = [
        "ALIGNMENT SCORES (1–5)",
        f"  objective → clarity:     {scores.objective_clarity}",
        f"  objective → activity:    {scores.activity_alignment}",
        f"  objective → assessment:  {scores.assessment_alignment}",
        f"  overall:                 {scores.overall}",
        "\nFINDINGS",
    ]
    for finding in output.findings:
        lines.append(f"  [{finding.severity}] {finding.area}: {finding.detail}")
    rewrite = output.rewrite
    lines.append(f"\nREWRITE — weakest part: {rewrite.target}")
    lines.append(f"  {rewrite.reason}")
    lines.append(rewrite.replacement)
    return "\n".join(lines)


def _brief(value: object) -> str:
    text = repr(value)
    if len(text) > 160:
        return text[:157] + "..."
    return text
