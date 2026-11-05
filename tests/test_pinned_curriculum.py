"""Checks against the real curriculum at the pinned versions. Skipped until `python -m roadmap fetch` has run."""

import pytest
from helpers import ROOT

from roadmap import Settings
from roadmap.source import CurriculumSource, load_curriculum

SETTINGS = Settings(config_dir=ROOT / "config", data_dir=ROOT / "data")
SOURCE = CurriculumSource.from_file(SETTINGS.curriculum_file)

pytestmark = pytest.mark.skipif(
    not all(
        (SETTINGS.curricula_dir / v.name / ".git").exists() for v in SOURCE.versions
    ),
    reason="run `python -m roadmap fetch` first",
)


@pytest.fixture(scope="module")
def october():
    """The version of the model runs of 21 October: it must read exactly as it did then."""
    return load_curriculum(SOURCE, SOURCE.version("2026-10-06"), SETTINGS.curricula_dir)


@pytest.fixture(scope="module")
def current():
    return load_curriculum(SOURCE, SOURCE.default, SETTINGS.curricula_dir)


def test_every_module_and_resource_is_found(october):
    assert len(october.modules) == 18
    assert sum(len(module.resources) for module in october.modules) == 116


def test_the_modules_with_a_checklist_can_be_proved(october):
    provable = [module.id for module in october.modules if module.can_be_proved]
    assert provable == [
        "engineering-fundamentals/terminal-algorithmic-basics",
        "engineering-fundamentals/linear-algebra",
        "engineering-fundamentals/probability-statistics",
        "engineering-fundamentals/data-manipulation",
        "softlanding/core-systems/networking",
        "softlanding/core-systems/infra-basics",
        "softlanding/specializations/software-engineering/resources",
    ]


def test_modules_are_in_course_order(october):
    first, *_, last = october.modules
    assert first.id == "engineering-fundamentals/terminal-algorithmic-basics"
    assert last.id == "softlanding/specializations/software-engineering/capstone"
    tracks = [
        module.section[-1] for module in october.modules if module.title == "Capstone"
    ]
    assert tracks == [
        "Computer Vision",
        "Data Science",
        "Generative AI",
        "NLP & LLMs",
        "AI Software Engineering",
    ]


def test_old_versions_link_to_their_own_pages(october):
    assert october.modules[0].url == (
        "https://roadmap.humblebee.ai/docs/2026-10-06/engineering-fundamentals/terminal-algorithmic-basics"
    )
    assert october.site_version == "2026-10-06"


def test_the_current_curriculum_leaves_out_retired_unlisted_pages(current):
    ids = [module.id for module in current.modules]
    assert len(ids) == 20
    assert "softlanding/core-systems/r1-software-engineering" not in ids  # unlisted
    assert "softlanding/core-systems/math-ml" not in ids  # a former module
    assert ids[:3] == [
        "engineering-fundamentals/terminal-algorithmic-basics",
        "engineering-fundamentals/math-for-ai",
        "engineering-fundamentals/data-manipulation",
    ]
    assert current.modules[0].url == (
        "https://roadmap.humblebee.ai/docs/engineering-fundamentals/terminal-algorithmic-basics"
    )


def test_the_current_curriculum_states_completion_under_headings(current):
    software = next(
        m
        for m in current.modules
        if m.id == "softlanding/core-systems/software-engineering"
    )
    assert software.checklist[0].startswith("A small working project")
    assert all(module.title for module in current.modules)
    # Its resource cards mostly leave out difficulty and duration; they still parse.
    assert sum(len(module.resources) for module in current.modules) > 100


@pytest.mark.parametrize("version_name", [v.name for v in SOURCE.versions])
def test_checkpoint_questions_name_topics_of_their_module(version_name):
    """A failed attempt sends the learner to review these topics, so they must exist in the module."""
    from roadmap.checkpoints import CheckpointStore

    curriculum = load_curriculum(
        SOURCE, SOURCE.version(version_name), SETTINGS.curricula_dir
    )
    store = CheckpointStore(ROOT / "checkpoints" / version_name)
    for module in curriculum.modules:
        checkpoint = store.load(module.id)
        if checkpoint is None:
            continue
        topics = {topic.title for topic in module.topics}
        assert {
            question.topic for question in checkpoint.questions
        } <= topics, module.id
