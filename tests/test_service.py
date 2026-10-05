from helpers import FakeLLM, planner_response, study_all

from roadmap import Choice, LearningPath, Level, Roadmap
from roadmap.llm import LLMUnavailable


def test_fallback_planner_no_llm(curriculum, questions, module_ids):
    path = Roadmap(curriculum, questions, llm=None).build_path(
        {"goal": "Computer vision"}, level=None
    )

    assert path.personalization_unavailable
    assert [item.module.id for item in path.included] == module_ids


def test_an_unreachable_model_falls_back_to_the_course_order(
    curriculum, questions, module_ids
):
    roadmap = Roadmap(curriculum, questions, FakeLLM(LLMUnavailable("rate limited")))

    path = roadmap.build_path({}, Level.BEGINNER)

    assert path.personalization_unavailable
    assert [item.module.id for item in path.included] == module_ids


def test_no_level_is_suggested_when_no_model_answers(curriculum, questions):
    roadmap = Roadmap(curriculum, questions, FakeLLM(LLMUnavailable("rate limited")))

    assert roadmap.assess_level({"programming": "None"}) is None


def test_learner_override_replaces_model_level(curriculum, questions, module_ids):
    llm = FakeLLM(
        {
            "level": "beginner",
            "evidence": ["Has not mentioned any projects"],
            "confidence": "low",
        },
        study_all(curriculum),
    )
    roadmap = Roadmap(curriculum, questions, llm)
    answers = {"programming": "Five years of Python"}

    assessment = roadmap.assess_level(answers)
    path = roadmap.build_path(answers, Level.ADVANCED, assessment)

    assert path.assessment is not None and path.assessment.level == Level.BEGINNER
    assert path.level == Level.ADVANCED
    assert "Learner's level: advanced" in llm.prompts[-1]
    assert not path.personalization_unavailable


def test_every_module_in_a_path_carries_its_source(curriculum, questions):
    path = Roadmap(curriculum, questions, llm=None).build_path({}, None)

    assert path.attribution == curriculum.attribution
    assert path.curriculum_version == curriculum.version
    assert path.changes
    for item in path.items:
        assert item.module.title and item.module.url.startswith("https://")
        assert all(
            resource.title and resource.url.startswith("https://")
            for resource in item.module.resources
        )


def test_a_path_survives_the_round_trip_through_json(curriculum, questions):
    path = Roadmap(curriculum, questions, llm=None).build_path({}, Level.INTERMEDIATE)

    assert LearningPath.model_validate_json(path.model_dump_json()) == path


def test_an_incomplete_plan_falls_back_to_the_course_order(curriculum, questions):
    incomplete = planner_response(
        curriculum, {"basics/terminal": (Choice.SKIP, "Known.")}
    )
    roadmap = Roadmap(curriculum, questions, FakeLLM(incomplete))

    path = roadmap.build_path({}, Level.BEGINNER)

    assert path.personalization_unavailable
    assert all(item.choice is Choice.STUDY for item in path.items)
