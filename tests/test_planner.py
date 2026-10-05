import pytest
from helpers import FakeLLM, planner_response, study_all
from pydantic import ValidationError

from roadmap import Choice, Level
from roadmap.llm import LLMUnavailable
from roadmap.planner import CourseOrderPlanner, LLMPlanner, ModuleDecision, prompt_ids


def plan(curriculum, questions, response, level=None):
    return LLMPlanner(FakeLLM(response), curriculum, questions).plan({}, level)


def test_path_follows_course_order_whatever_order_the_model_answers_in(
    curriculum, questions, module_ids
):
    response = study_all(curriculum)
    response["decisions"].reverse()

    items = plan(curriculum, questions, response)

    assert [item.module.id for item in items] == module_ids


def test_skipped_nodes_have_justification(curriculum, questions, module_ids):
    skips = {
        "basics/terminal": "You use the shell every day at work.",
        "tracks/speech/resources": "Your goal is vision, not speech.",
    }
    decisions = {
        module_id: (
            (Choice.SKIP, skips[module_id])
            if module_id in skips
            else (Choice.STUDY, "Needed.")
        )
        for module_id in module_ids
    }

    items = plan(curriculum, questions, planner_response(curriculum, decisions))

    assert {item.module.id: item.reason for item in items if not item.included} == skips
    assert [item.module.id for item in items] == module_ids  # nothing left out silently


def test_a_decision_without_a_reason_is_rejected():
    with pytest.raises(ValidationError):
        ModuleDecision.model_validate(
            {"module_id": "m1", "choice": "skip", "reason": " "}
        )


def test_a_module_with_a_checklist_can_be_proved(curriculum, questions):
    reason = "You use the shell daily; show it with the checklist."
    response = study_all(
        curriculum, except_for={"basics/terminal": (Choice.PROVE, reason)}
    )

    terminal = plan(curriculum, questions, response)[0]

    assert (terminal.choice, terminal.reason) == (Choice.PROVE, reason)
    assert terminal.included


def test_a_module_without_a_checklist_is_studied_instead_of_proved(
    curriculum, questions
):
    response = study_all(
        curriculum, except_for={"basics/algebra": (Choice.PROVE, "You know matrices.")}
    )

    algebra = plan(curriculum, questions, response)[1]

    assert (algebra.choice, algebra.reason) == (Choice.STUDY, LLMPlanner.NO_CHECKLIST)


def test_a_plan_that_leaves_out_modules_is_not_used(curriculum, questions):
    response = planner_response(
        curriculum, {"basics/terminal": (Choice.SKIP, "You use the shell at work.")}
    )

    with pytest.raises(LLMUnavailable):
        plan(curriculum, questions, response)


def test_modules_the_course_does_not_have_are_ignored(
    curriculum, questions, module_ids
):
    response = study_all(curriculum)
    response["decisions"].append(
        {"module_id": "m99", "choice": "skip", "reason": "Not a real module."}
    )

    items = plan(curriculum, questions, response)

    assert [item.module.id for item in items] == module_ids
    assert all(item.choice is Choice.STUDY for item in items)


def test_the_prompt_gives_the_level_every_module_and_the_checklists(
    curriculum, questions
):
    llm = FakeLLM(study_all(curriculum))

    LLMPlanner(llm, curriculum, questions).plan(
        {"goal": "Computer vision"}, Level.ADVANCED
    )

    [prompt] = llm.prompts
    assert "Learner's level: advanced" in prompt
    assert "A: Computer vision" in prompt
    for prompt_id, module in prompt_ids(curriculum.modules).items():
        assert f"id: {prompt_id}\n  title: {module.full_title}" in prompt
    assert "Search across files with **grep**." in prompt


def test_course_order_planner_keeps_every_module_to_study(curriculum, module_ids):
    items = CourseOrderPlanner(curriculum).plan({}, None)

    assert [item.module.id for item in items] == module_ids
    assert all(item.choice is Choice.STUDY and item.reason for item in items)
