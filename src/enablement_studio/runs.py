from __future__ import annotations

from enablement_studio.engine import generate
from enablement_studio.models import (
    CallCoaching,
    EngineName,
    LessonCritique,
    Product,
    ProductOutput,
    RoleEnablement,
    SavedRun,
    artifact_map,
    call_from_dict,
    critic_from_dict,
    role_from_dict,
)
from enablement_studio.paths import default_db_path
from enablement_studio.store import Store


def title_of(output: ProductOutput) -> str:
    match output:
        case RoleEnablement():
            return output.role_title
        case CallCoaching():
            return output.call_title
        case LessonCritique():
            return output.lesson_title
        case _:
            never: ProductOutput = output
            raise TypeError(f"unsupported output: {type(never)!r}")


def output_from_run(run: SavedRun) -> ProductOutput:
    payload = run.artifacts.get("result")
    if not isinstance(payload, dict):
        raise ValueError(f"run {run.id} has no result artifact")
    match run.product:
        case Product.ROLE:
            return role_from_dict(payload)
        case Product.CALL:
            return call_from_dict(payload)
        case Product.CRITIC:
            return critic_from_dict(payload)
        case _:
            never = run.product
            raise ValueError(f"unsupported product: {never}")


def generate_and_save(
    product: Product,
    text: str,
    *,
    project: str,
    store: Store | None = None,
    force_offline: bool = False,
) -> tuple[ProductOutput, EngineName, SavedRun]:
    output, engine = generate(product, text, force_offline=force_offline)
    target = store if store is not None else Store(default_db_path())
    run = target.save_run(
        project=project,
        product=product,
        title=title_of(output),
        input_text=text,
        engine=engine,
        artifacts=artifact_map(output),
        invalid=bool(getattr(output, "invalid", False)),
    )
    return output, engine, run
