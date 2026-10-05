"""Checks against the real curriculum at the pinned version. Skipped until `python -m roadmap fetch` has run."""

import pytest
from helpers import ROOT

from roadmap import Settings
from roadmap.source import CurriculumSource, load_curriculum

SETTINGS = Settings(config_dir=ROOT / "config", data_dir=ROOT / "data")

pytestmark = pytest.mark.skipif(
    not (SETTINGS.curriculum_checkout / ".git").exists(),
    reason="run `python -m roadmap fetch` first",
)


@pytest.fixture(scope="module")
def pinned_curriculum():
    return load_curriculum(
        CurriculumSource.from_file(SETTINGS.curriculum_file),
        SETTINGS.curriculum_checkout,
    )


def test_every_module_and_resource_is_found(pinned_curriculum):
    assert len(pinned_curriculum.modules) == 18
    assert sum(len(module.resources) for module in pinned_curriculum.modules) == 116


def test_the_modules_with_a_checklist_can_be_proved(pinned_curriculum):
    provable = [
        module.id for module in pinned_curriculum.modules if module.can_be_proved
    ]
    assert provable == [
        "engineering-fundamentals/terminal-algorithmic-basics",
        "engineering-fundamentals/linear-algebra",
        "engineering-fundamentals/probability-statistics",
        "engineering-fundamentals/data-manipulation",
        "softlanding/core-systems/networking",
        "softlanding/core-systems/infra-basics",
        "softlanding/specializations/software-engineering/resources",
    ]


def test_modules_are_in_course_order(pinned_curriculum):
    first, *_, last = pinned_curriculum.modules
    assert first.id == "engineering-fundamentals/terminal-algorithmic-basics"
    assert last.id == "softlanding/specializations/software-engineering/capstone"
    tracks = [
        module.section[-1]
        for module in pinned_curriculum.modules
        if module.title == "Capstone"
    ]
    assert tracks == [
        "Computer Vision",
        "Data Science",
        "Generative AI",
        "NLP & LLMs",
        "AI Software Engineering",
    ]


def test_urls_match_the_site(pinned_curriculum):
    urls = {module.id: module.url for module in pinned_curriculum.modules}
    site = "https://roadmap.humblebee.ai/docs"
    assert (
        urls["softlanding/core-systems/math-ml"]
        == f"{site}/softlanding/core-systems/01-math-ml"
    )
    assert (
        urls["softlanding/core-systems/networking"]
        == f"{site}/softlanding/core-systems/networking"
    )
