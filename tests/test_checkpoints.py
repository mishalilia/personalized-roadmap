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
    CodingProblem,
    Status,
    module_brief,
    verify_problem,
)
from roadmap.llm import LLMUnavailable


def question(number: int, answer: int = 0) -> dict:
    return {
        "id": f"q{number}",
        "topic": "1. Shell Basics",
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


def answers_for(found: Checkpoint, attempt: int, wrong: int = 0) -> dict[str, int]:
    """Answers as the learner gives them: positions of options as shown; the first `wrong` are wrong."""
    answers = {}
    for index, question in enumerate(found.questions_for_attempt(attempt)):
        right = found.order_of(attempt, question.id).index(question.answer)
        answers[question.id] = (right + 1) % 4 if index < wrong else right
    return answers


def test_four_of_five_pass_and_only_a_perfect_first_attempt_is_effortless():
    found = checkpoint()

    perfect = found.grade(0, answers_for(found, 0))
    one_wrong = found.grade(0, answers_for(found, 0, wrong=1))
    two_wrong = found.grade(0, answers_for(found, 0, wrong=2))
    retake = found.grade(1, answers_for(found, 1))

    assert (perfect.score, perfect.passed, perfect.effortless) == (5, True, True)
    assert (one_wrong.score, one_wrong.passed, one_wrong.effortless) == (4, True, False)
    assert one_wrong.score == PASS_MARK
    assert (two_wrong.passed, two_wrong.effortless) == (False, False)
    assert retake.passed and not retake.effortless
    assert [item.correct for item in one_wrong.feedback][0] is False


def test_options_are_shuffled_the_same_way_within_an_attempt_and_differently_across_attempts():
    found = checkpoint()

    shown = [found.asked(attempt)[0].options for attempt in (0, 0, 2, 4)]

    assert shown[0] == shown[1]
    assert sorted(shown[0]) == ["a", "b", "c", "d"]
    assert len({tuple(options) for options in shown}) > 1


def test_a_failed_attempt_names_topics_to_review_but_not_the_answers():
    found = checkpoint()

    failed = found.grade(0, answers_for(found, 0, wrong=3))
    passed = found.grade(0, answers_for(found, 0, wrong=1))

    assert all(
        item.answer is None and item.explanation is None for item in failed.feedback
    )
    assert failed.review_topics == ["1. Shell Basics"]
    assert all(item.answer is not None and item.explanation for item in passed.feedback)


def test_a_coding_problem_must_be_python_and_its_solution_must_pass_its_tests():
    good = CodingProblem(
        title="Add",
        prompt="Write `add`.",
        starter_code="def add(a, b):\n    ...",
        tests="assert add(1, 2) == 3",
        solution="def add(a, b):\n    return a + b",
    )
    wrong = good.model_copy(update={"solution": "def add(a, b):\n    return a - b"})

    assert verify_problem(good) is None
    assert "AssertionError" in (verify_problem(wrong) or "")
    with pytest.raises(ValidationError):
        CodingProblem.model_validate(
            good.model_dump() | {"tests": "assert add(1, 2) =="}
        )


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
    generated = [question(n, answer=n % 4) | {"id": "x"} for n in range(1, 16)]
    llm = FakeLLM({"questions": generated})

    found = CheckpointGenerator(llm, "some-model").generate(terminal, "v1")

    assert [q.id for q in found.questions] == [f"q{n}" for n in range(1, 16)]
    assert found.problem is None
    assert found.status is Status.DRAFT and found.generated_by == "some-model"
    assert "Move between directories with cd" in llm.prompts[0]
    assert "A short first look at the shell." in llm.prompts[0]  # the authors' note


def test_generated_questions_must_name_the_modules_own_topics(curriculum):
    generated = [question(n) | {"topic": "Something else"} for n in range(1, 16)]
    llm = FakeLLM({"questions": generated})

    with pytest.raises(LLMUnavailable):
        CheckpointGenerator(llm, "some-model").generate(curriculum.modules[0], "v1")


def test_a_topic_named_without_its_heading_number_is_the_modules_own(curriculum):
    generated = [question(n) | {"topic": "shell basics"} for n in range(1, 16)]
    llm = FakeLLM({"questions": generated})

    found = CheckpointGenerator(llm, "some-model").generate(curriculum.modules[0], "v1")

    assert {q.topic for q in found.questions} == {"1. Shell Basics"}


def test_an_answer_with_the_wrong_number_of_questions_is_rejected(curriculum):
    llm = FakeLLM({"questions": [question(n) for n in range(1, 6)]})

    with pytest.raises(LLMUnavailable):
        CheckpointGenerator(llm, "some-model").generate(curriculum.modules[0], "v1")


def test_the_brief_names_what_the_module_teaches_and_no_resource_links(curriculum):
    brief = module_brief(curriculum.modules[0])

    assert "Shell Basics" in brief and "grep" in brief
    assert "https://" not in brief


def test_the_committed_checkpoints_fit_their_curriculum_versions():
    """Every file in checkpoints/<version>/ loads, belongs to that version's commit, and its coding
    problem's reference solution passes its tests."""
    from roadmap.source import CurriculumSource

    source = CurriculumSource.from_file(ROOT / "config" / "curriculum.yaml")
    files = list((ROOT / "checkpoints").rglob("*.yaml"))
    assert files
    for file in files:
        version_name, *parts = (
            file.relative_to(ROOT / "checkpoints").with_suffix("").parts
        )
        module_id = "/".join(parts)
        found = CheckpointStore(ROOT / "checkpoints" / version_name).load(module_id)
        assert found is not None and found.module_id == module_id
        assert found.curriculum_version == source.version(version_name).ref
        if found.problem is not None and not found.problem.packages:
            assert verify_problem(found.problem) is None, file


def test_a_saved_checkpoint_marks_its_commit_hash_for_the_secret_scanner(
    tmp_path: Path,
):
    store = CheckpointStore(tmp_path)
    commit = "9fc5573ddbd7be5d5da997a26c49afeafbfe6210"  # pragma: allowlist secret
    found = checkpoint().model_copy(update={"curriculum_version": commit})

    file = store.save(found)

    assert "# pragma: allowlist secret" in file.read_text().splitlines()[1]
    assert store.load(found.module_id) == found


def test_verify_names_a_missing_package_instead_of_running(monkeypatch):
    problem = CodingProblem(
        title="t",
        prompt="p",
        starter_code="def f():\n    ...",
        tests="assert f() == 1",
        solution="def f():\n    return 1",
        packages=["surely_not_installed_pkg"],
    )
    assert verify_problem(problem) == (
        "needs surely_not_installed_pkg: pip install surely_not_installed_pkg"
    )
