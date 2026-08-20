from __future__ import annotations

from enablement_studio.engine import generate, llm_configured
from enablement_studio.models import EngineName, Product, role_from_dict


def test_generate_is_offline_without_keys(job_text: str) -> None:
    assert llm_configured() is False
    output, engine = generate(Product.ROLE, job_text)
    assert engine is EngineName.OFFLINE
    assert output.example_data is True


def test_role_round_trip_dict(job_text: str) -> None:
    output, _engine = generate(Product.ROLE, job_text)
    clone = role_from_dict(output.to_dict())
    assert clone.role_title == output.role_title
    assert len(clone.quiz) == len(output.quiz)
