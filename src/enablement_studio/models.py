from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SOURCE_NOTE = (
    "Generated locally. Example or user-supplied text only. "
    "Not sourced from a live employer or customer."
)

PUBLIC_SOURCE_NOTE = (
    "Generated locally from a sanitized public job posting. "
    "Not an application. No pay ranges, apply buttons, or application materials."
)


class Product(str, Enum):
    ROLE = "role"
    CALL = "call"
    CRITIC = "critic"


class EngineName(str, Enum):
    OFFLINE = "offline"
    LLM = "llm"


@dataclass(frozen=True)
class SkillNode:
    id: str
    name: str
    level: str
    detail: str


@dataclass(frozen=True)
class SkillEdge:
    source: str
    target: str
    relation: str


@dataclass(frozen=True)
class SkillGraph:
    nodes: list[SkillNode]
    edges: list[SkillEdge]


@dataclass(frozen=True)
class LearningObjective:
    id: str
    statement: str
    skill_id: str
    measure: str


@dataclass(frozen=True)
class ModuleBlock:
    minutes: str
    title: str
    description: str


@dataclass(frozen=True)
class PracticeActivity:
    title: str
    scenario: str
    instructions: list[str]
    success_criteria: list[str]


@dataclass(frozen=True)
class QuizItem:
    question: str
    choices: list[str]
    answer: str
    rationale: str


@dataclass(frozen=True)
class RoleEnablement:
    example_data: bool
    source_note: str
    role_title: str
    skill_graph: SkillGraph
    objectives: list[LearningObjective]
    outline: list[ModuleBlock]
    practice: PracticeActivity
    quiz: list[QuizItem]
    invalid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentNote:
    audience: str
    headline: str
    body: str


@dataclass(frozen=True)
class EnablementFix:
    title: str
    problem: str
    fix: str
    measure: str


@dataclass(frozen=True)
class CallCoaching:
    example_data: bool
    source_note: str
    call_title: str
    speakers: list[str]
    signals: list[str]
    notes: list[AgentNote]
    enablement_fix: EnablementFix

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AlignmentScores:
    objective_clarity: int
    activity_alignment: int
    assessment_alignment: int
    overall: int


@dataclass(frozen=True)
class CritiqueFinding:
    area: str
    severity: str
    detail: str


@dataclass(frozen=True)
class Rewrite:
    target: str
    reason: str
    replacement: str


@dataclass(frozen=True)
class LessonCritique:
    example_data: bool
    source_note: str
    lesson_title: str
    scores: AlignmentScores
    findings: list[CritiqueFinding]
    rewrite: Rewrite

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProductOutput = RoleEnablement | CallCoaching | LessonCritique


@dataclass
class SavedRun:
    id: int
    project: str
    product: Product
    version: int
    title: str
    input_text: str
    engine: EngineName
    created_at: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    invalid: bool = False


def _require(data: dict[str, Any], *keys: str) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"missing keys: {missing}")


def role_from_dict(data: dict[str, Any]) -> RoleEnablement:
    _require(data, "role_title", "skill_graph", "objectives", "outline", "practice", "quiz")
    graph = data["skill_graph"]
    practice = data["practice"]
    return RoleEnablement(
        example_data=bool(data.get("example_data", False)),
        source_note=str(data.get("source_note", SOURCE_NOTE)),
        role_title=str(data["role_title"]),
        skill_graph=SkillGraph(
            nodes=[SkillNode(**node) for node in graph["nodes"]],
            edges=[SkillEdge(**edge) for edge in graph["edges"]],
        ),
        objectives=[LearningObjective(**item) for item in data["objectives"]],
        outline=[ModuleBlock(**item) for item in data["outline"]],
        practice=PracticeActivity(**practice),
        quiz=[QuizItem(**item) for item in data["quiz"]],
        invalid=bool(data.get("invalid", False)),
    )


def call_from_dict(data: dict[str, Any]) -> CallCoaching:
    _require(data, "call_title", "notes", "enablement_fix")
    return CallCoaching(
        example_data=bool(data.get("example_data", False)),
        source_note=str(data.get("source_note", SOURCE_NOTE)),
        call_title=str(data["call_title"]),
        speakers=[str(item) for item in data.get("speakers", [])],
        signals=[str(item) for item in data.get("signals", [])],
        notes=[AgentNote(**item) for item in data["notes"]],
        enablement_fix=EnablementFix(**data["enablement_fix"]),
    )


def critic_from_dict(data: dict[str, Any]) -> LessonCritique:
    _require(data, "lesson_title", "scores", "rewrite")
    return LessonCritique(
        example_data=bool(data.get("example_data", False)),
        source_note=str(data.get("source_note", SOURCE_NOTE)),
        lesson_title=str(data["lesson_title"]),
        scores=AlignmentScores(**data["scores"]),
        findings=[CritiqueFinding(**item) for item in data.get("findings", [])],
        rewrite=Rewrite(**data["rewrite"]),
    )


def artifact_map(output: ProductOutput) -> dict[str, Any]:
    payload = output.to_dict()
    if isinstance(output, RoleEnablement):
        return {
            "result": payload,
            "skill_graph": payload["skill_graph"],
            "learning_objectives": payload["objectives"],
            "module_outline": payload["outline"],
            "practice_activity": payload["practice"],
            "quiz": payload["quiz"],
        }
    if isinstance(output, CallCoaching):
        notes = {note.audience: asdict(note) for note in output.notes}
        return {
            "result": payload,
            "learner_note": notes.get("learner", {}),
            "customer_note": notes.get("customer", {}),
            "coach_note": notes.get("coach", {}),
            "enablement_fix": payload["enablement_fix"],
        }
    if isinstance(output, LessonCritique):
        return {
            "result": payload,
            "scores": payload["scores"],
            "findings": payload["findings"],
            "rewrite": payload["rewrite"],
        }
    never: ProductOutput = output
    raise TypeError(f"unsupported product output: {type(never)!r}")
