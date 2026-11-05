from pathlib import Path

import pytest
from helpers import ROOT, FakeLLM
from pydantic import ValidationError

from roadmap import Curriculum
from roadmap.checkpoints import (
    PASS_MARK,
    QUESTIONS_PER_ATTEMPT,
    Checkpoint,
    CheckpointGenerator,
    CheckpointQuestion,
    CheckpointStore,
    Status,
    module_brief,
)
from roadmap.llm import LLMUnavailable


def question(number: int, answer: int = 0) -> dict:
    return {
        "id": f"q{number}",
        "topic": "Shell Basics",
        "text": f"Question {number}?",
        "options": ["a", "b", "c", "d"],
        "answer": answer,
        "explanation": "Because.",
    }


def checkpoint(module_id: str = "basics/terminal", count: int = 10) -> Checkpoint:
    return Checkpoint(
        module_id=module_id,
        curriculum_version="test-version",
        generated_by="test",
        questions=[
            CheckpointQuestion.model_validate(question(n)) for n in range(1, count + 1)
        ],
    )


def test_the_parser_reads_a_modules_topics_and_their_outcomes(curriculum):
    terminal = next(m for m in curriculum.modules if m.id == "basics/terminal")

    assert [topic.title for topic in terminal.topics] == ["1. Shell Basics"]
    assert terminal.topics[0].outcomes == [
        "Move between directories with cd",
        "Find text in files with grep",
    ]


def test_each_attempt_asks_five_questions_and_a_retake_asks_others():
    found = checkpoint()

    first = [q.id for q in found.questions_for_attempt(0)]
    second = [q.id for q in found.questions_for_attempt(1)]

    assert len(first) == QUESTIONS_PER_ATTEMPT
    assert not set(first) & set(second)
    assert [q.id for q in found.questions_for_attempt(2)] == first


def test_four_of_five_pass_and_only_a_perfect_first_attempt_is_effortless():
    found = checkpoint()
    asked = [q.id for q in found.questions_for_attempt(0)]

    perfect = found.grade(0, {qid: 0 for qid in asked})
    one_wrong = found.grade(0, {qid: int(qid == asked[0]) for qid in asked})
    two_wrong = found.grade(0, {qid: int(qid in asked[:2]) for qid in asked})
    retake = found.grade(1, {q.id: 0 for q in found.questions_for_attempt(1)})

    assert (perfect.score, perfect.passed, perfect.effortless) == (5, True, True)
    assert (one_wrong.score, one_wrong.passed, one_wrong.effortless) == (4, True, False)
    assert one_wrong.score == PASS_MARK
    assert (two_wrong.passed, two_wrong.effortless) == (False, False)
    assert retake.passed and not retake.effortless
    assert [item.correct for item in one_wrong.feedback][0] is False


def test_an_attempt_must_answer_exactly_its_own_questions():
    found = checkpoint()

    with pytest.raises(ValueError):
        found.grade(0, {"q1": 0})
    with pytest.raises(ValueError):
        found.grade(0, {q.id: 0 for q in found.questions_for_attempt(1)})


@pytest.mark.parametrize(
    "broken",
    [
        {"options": ["a", "b", "c"]},
        {"options": ["a", "b", "c", "A"]},
        {"answer": 4},
    ],
)
def test_a_question_has_four_distinct_options_and_one_answer(broken):
    with pytest.raises(ValidationError):
        CheckpointQuestion.model_validate(question(1) | broken)


def test_a_checkpoint_needs_enough_distinct_questions():
    with pytest.raises(ValidationError):
        checkpoint(count=QUESTIONS_PER_ATTEMPT - 1)


def test_the_store_keeps_one_file_per_module_and_only_the_curriculum_version(
    tmp_path: Path, curriculum: Curriculum
):
    store = CheckpointStore(tmp_path)
    store.save(checkpoint("basics/terminal"))
    stale = checkpoint("basics/algebra").model_copy(
        update={"curriculum_version": "old"}
    )
    store.save(stale)

    assert (tmp_path / "basics" / "terminal.yaml").is_file()
    assert store.load("basics/terminal") == checkpoint("basics/terminal")
    assert store.load("tracks/notes") is None
    assert list(store.all_for(curriculum)) == ["basics/terminal"]


def test_generated_questions_are_numbered_and_kept_as_a_draft(curriculum):
    terminal = curriculum.modules[0]
    generated = [question(n, answer=n % 4) | {"id": "x"} for n in range(1, 11)]
    llm = FakeLLM({"questions": generated})

    found = CheckpointGenerator(llm, "some-model").generate(terminal, "v1")

    assert [q.id for q in found.questions] == [f"q{n}" for n in range(1, 11)]
    assert found.status is Status.DRAFT and found.generated_by == "some-model"
    assert "Move between directories with cd" in llm.prompts[0]
    assert "A short first look at the shell." in llm.prompts[0]  # the authors' note


def test_an_answer_with_the_wrong_number_of_questions_is_rejected(curriculum):
    llm = FakeLLM({"questions": [question(n) for n in range(1, 6)]})

    with pytest.raises(LLMUnavailable):
        CheckpointGenerator(llm, "some-model").generate(curriculum.modules[0], "v1")


def test_the_brief_names_what_the_module_teaches_and_no_resource_links(curriculum):
    brief = module_brief(curriculum.modules[0])

    assert "Shell Basics" in brief and "grep" in brief
    assert "https://" not in brief


def test_the_committed_checkpoints_fit_the_pinned_curriculum():
    """Every file in checkpoints/ loads and belongs to the version in config/curriculum.yaml."""
    from roadmap.source import CurriculumSource

    version = CurriculumSource.from_file(ROOT / "config" / "curriculum.yaml").version
    files = list((ROOT / "checkpoints").rglob("*.yaml"))
    assert files
    for file in files:
        module_id = file.relative_to(ROOT / "checkpoints").with_suffix("").as_posix()
        found = CheckpointStore(ROOT / "checkpoints").load(module_id)
        assert found is not None and found.module_id == module_id
        assert found.curriculum_version == version
