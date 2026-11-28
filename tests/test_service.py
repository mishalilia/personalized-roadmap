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


def test_a_perfect_first_checkpoint_brings_lighter_suggestions_for_later_modules(
    curriculum, questions
):
    from roadmap.checkpoints import Grade, QuestionFeedback

    terminal, algebra = "basics/terminal", "basics/algebra"
    llm = FakeLLM(
        study_all(curriculum),
        study_all(
            curriculum,
            except_for={
                terminal: (Choice.SKIP, "Earlier than the checkpoint."),
                algebra: (Choice.SKIP, "The checkpoint showed you know it."),
            },
        ),
    )
    roadmap = Roadmap(curriculum, questions, llm)
    path = roadmap.build_path(
        {"programming": "Bash every day"}, Level.BEGINNER
    ).confirm()
    grade = Grade(
        attempt=0,
        score=5,
        total=5,
        passed=True,
        effortless=True,
        feedback=[
            QuestionFeedback(id="q1", topic="Pipes", correct=True),
            QuestionFeedback(id="q2", topic="Pipes", correct=True),
            QuestionFeedback(id="q3", topic="Paths", correct=True),
        ],
    )

    after = roadmap.after_checkpoint(path, terminal, grade)

    assert after.item(terminal).progress == "passed"
    assert [(p.module_id, p.choice) for p in after.proposals] == [
        (algebra, Choice.SKIP)
    ]
    assert "passed the checkpoint" in llm.prompts[-1]
    assert "answering questions on: Pipes; Paths." in llm.prompts[-1]
    assert "Bash every day" in llm.prompts[-1]  # planned again from the stored answers


def test_without_a_model_a_checkpoint_still_counts_but_brings_no_suggestions(
    curriculum, questions
):
    from roadmap.checkpoints import Grade

    roadmap = Roadmap(curriculum, questions, llm=None)
    path = roadmap.build_path({}, None).confirm()
    grade = Grade(
        attempt=0, score=5, total=5, passed=True, effortless=True, feedback=[]
    )

    after = roadmap.after_checkpoint(path, "basics/terminal", grade)

    assert after.item("basics/terminal").progress == "passed"
    assert after.proposals == []


def test_a_failed_checkpoint_makes_later_modules_and_topics_heavier_at_once(
    curriculum, questions
):
    from helpers import planner_response
    from roadmap.checkpoints import Grade, QuestionFeedback
    from roadmap.curriculum import Topic
    from roadmap.path import TopicChoice

    terminal, algebra, notes, vision = (
        "basics/terminal",
        "basics/algebra",
        "tracks/notes",
        "tracks/vision/resources",
    )
    course = curriculum.model_copy(
        update={
            "modules": [
                (
                    m.model_copy(
                        update={
                            "topics": [Topic(title="Intro"), Topic(title="Practice")]
                        }
                    )
                    if m.id == vision
                    else m
                )
                for m in curriculum.modules
            ]
        }
    )
    first = study_all(course, except_for={notes: (Choice.PROVE, "You have used it.")})
    vision_id = planner_response(course, {vision: (Choice.STUDY, "x")})["decisions"][0][
        "module_id"
    ]
    for decision in first["decisions"]:
        if decision["module_id"] == vision_id:
            decision["skim"] = ["Intro"]
    again = study_all(
        course,
        except_for={algebra: (Choice.SKIP, "Lighter, which a failure cannot bring.")},
    )
    llm = FakeLLM(first, again)
    roadmap = Roadmap(course, questions, llm)
    path = roadmap.build_path({"programming": "Some Python"}, Level.BEGINNER).confirm()
    assert path.item(vision).topic_choice("Intro") is TopicChoice.SKIM
    grade = Grade(
        attempt=0,
        score=1,
        total=5,
        passed=False,
        effortless=False,
        feedback=[QuestionFeedback(id="q1", topic="Pipes", correct=False)],
        review_topics=["Pipes"],
    )

    after = roadmap.after_checkpoint(path, terminal, grade)

    assert after.item(terminal).progress == "failed"
    # Made without asking, in course order; algebra's lighter "skip" is dropped after a failure.
    assert [
        (p.module_id, p.choice, p.topic, p.topic_choice)
        for p in after.changed_after_checkpoint
    ] == [
        (vision, None, "Intro", TopicChoice.STUDY),
        (notes, Choice.STUDY, None, None),
    ]
    assert after.proposals == []
    assert after.item(vision).topic_choice("Intro") is TopicChoice.STUDY
    assert after.item(notes).choice is Choice.STUDY
    assert after.item(algebra).choice is Choice.STUDY
    assert (after.item(notes).adjustment or "").startswith("Changed after a checkpoint")
    assert "failed the checkpoint" in llm.prompts[-1] and "Pipes" in llm.prompts[-1]
    assert f"{vision}: study (skim Intro)" in llm.prompts[-1]


def test_over_the_quota_a_failed_checkpoint_still_counts_without_suggestions(
    curriculum, questions
):
    from roadmap.checkpoints import Grade

    llm = FakeLLM(study_all(curriculum))
    roadmap = Roadmap(curriculum, questions, llm)
    path = roadmap.build_path({}, Level.BEGINNER).confirm()
    grade = Grade(
        attempt=0,
        score=1,
        total=5,
        passed=False,
        effortless=False,
        feedback=[],
        review_topics=["Pipes"],
    )

    after = roadmap.after_checkpoint(path, "basics/terminal", grade, suggest=False)

    assert after.item("basics/terminal").progress == "failed" and after.proposals == []
    assert len(llm.prompts) == 1  # only the first plan
