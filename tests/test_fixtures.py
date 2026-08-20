from __future__ import annotations

from pathlib import Path

from enablement_studio.paths import find_fixture


def test_fixtures_are_marked_example() -> None:
    names = (
        "example_account_executive_job.txt",
        "example_sales_call.txt",
        "example_new_hire_lesson.md",
    )
    for name in names:
        text = find_fixture(name).read_text(encoding="utf-8")
        assert "EXAMPLE DATA" in text
        assert "fictional" in text.lower()


def test_repo_and_package_fixtures_match() -> None:
    repo = Path(__file__).resolve().parents[1]
    packaged = repo / "src/enablement_studio/fixtures"
    public = repo / "fixtures"
    for name in public.iterdir():
        if name.is_file():
            assert (packaged / name.name).read_text(encoding="utf-8") == name.read_text(
                encoding="utf-8"
            )
