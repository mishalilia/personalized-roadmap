import pytest
from helpers import FakeLLM, StreamingFakeLLM, planner_response, study_all
from pydantic import ValidationError

from roadmap import Choice, Level
from roadmap.llm import LLMUnavailable
from roadmap.path import PathItem
from roadmap.planner import (
    CourseOrderPlanner,
    Plan,
    LLMPlanner,
    ModuleDecision,
    prompt_ids,
)


def plan(curriculum, questions, response, level=None):
    return LLMPlanner(FakeLLM(response), curriculum, questions).plan({}, level)


def test_path_follows_course_order_whatever_order_the_model_answers_in(
    curriculum, questions, module_ids
):
    response = study_all(curriculum)
    response["decisions"].reverse()

    items = plan(curriculum, questions, response)

    assert [item.module.id for item in items] == module_ids


def test_a_streamed_plan_gives_modules_as_the_model_decides_them_then_the_plan_in_course_order(
    curriculum, questions, module_ids
):
    response = study_all(curriculum)
    response["decisions"].reverse()
    response["title"] = "Computer vision"
    planner = LLMPlanner(StreamingFakeLLM(response), curriculum, questions)

    *items, plan = planner.plan_streaming({}, None)

    assert all(isinstance(item, PathItem) for item in items)
    assert [item.module.id for item in items if isinstance(item, PathItem)] == (
        module_ids[::-1]
    )
    assert isinstance(plan, Plan) and plan.title == "Computer vision"
    assert [item.module.id for item in plan.items] == module_ids


def test_a_planner_whose_model_cannot_stream_gives_the_whole_plan_at_once(
    curriculum, questions, module_ids
):
    planner = LLMPlanner(FakeLLM(study_all(curriculum)), curriculum, questions)

    [plan] = planner.plan_streaming({}, None)

    assert isinstance(plan, Plan)
    assert [item.module.id for item in plan.items] == module_ids


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


def test_a_module_to_study_may_name_topics_to_skim_and_only_its_own(
    curriculum, questions
):
    from roadmap.curriculum import Topic

    three = [Topic(title=f"{n}. Part {n}") for n in (1, 2, 3)]
    module = curriculum.modules[0].model_copy(update={"topics": three})
    course = curriculum.model_copy(
        update={"modules": [module, *curriculum.modules[1:]]}
    )
    response = study_all(course)
    response["decisions"][0]["skim"] = [
        "Part 2",  # named without its number
        "Something else",  # not in the module
    ]
    response["decisions"][1]["choice"] = "skip"
    response["decisions"][1]["skim"] = ["Anything"]

    items = plan(course, questions, response)

    assert [(s.topic, s.reason) for s in items[0].skim] == [("2. Part 2", None)]
    assert items[1].skim == []


def test_a_module_to_study_may_skip_topics_but_keeps_one_to_study(
    curriculum, questions
):
    from roadmap.curriculum import Topic
    from roadmap.planner import ModuleDecision, _topics_for

    three = [Topic(title=f"{n}. Part {n}") for n in (1, 2, 3)]
    module = curriculum.modules[0].model_copy(update={"topics": three})

    def decide(skip, skim=()):
        return ModuleDecision(
            module_id="m1",
            choice=Choice.STUDY,
            reason="Study it.",
            skip_topics=list(skip),
            skim=list(skim),
        )

    skim, skip = _topics_for(module, decide(["Part 1"], ["Part 1", "2. Part 2"]))
    assert [s.topic for s in skip] == ["1. Part 1"] and [s.topic for s in skim] == [
        "2. Part 2"
    ]
    _, everything = _topics_for(module, decide(["Part 1", "Part 2", "Part 3"]))
    assert (
        everything == []
    )  # the whole module known: that is prove or skip, not three skipped topics
    skim, skip = _topics_for(module, decide(["Part 1", "Part 2"], ["Part 3"]))
    assert len(skip) == 2 and skim == []  # one topic is always left to study in full


def test_a_module_to_prove_keeps_its_topics_for_studying_it_instead(
    curriculum, questions
):
    from roadmap.curriculum import Topic
    from roadmap.planner import ModuleDecision, _topics_for

    three = [Topic(title=f"{n}. Part {n}") for n in (1, 2, 3)]
    module = curriculum.modules[0].model_copy(update={"topics": three})
    decision = ModuleDecision(
        module_id="m1",
        choice=Choice.PROVE,
        reason="You use it at work.",
        skip_topics=["Part 1"],
        skim=["Part 2"],
    )
    skim, skip = _topics_for(module, decision)
    assert [s.topic for s in skip] == ["1. Part 1"]
    assert [s.topic for s in skim] == ["2. Part 2"]
    skipped = decision.model_copy(update={"choice": Choice.SKIP})
    assert _topics_for(module, skipped) == ([], [])
