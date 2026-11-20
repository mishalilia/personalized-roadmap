from helpers import ROOT

from roadmap import load_profiles
import pytest

from roadmap.onboarding import ChoiceAnswer, answer_texts, format_answers


def test_onboarding_schema(questions):
    ids = [question.id for question in questions]
    assert len(ids) == len(set(ids))
    assert 6 <= len(questions) <= 8
    assert all(question.text.strip() for question in questions)
    # Coding background and end goal, as the Baseline requires.
    assert {"programming", "goal"} <= set(ids)
    for question in questions:
        options = [option.id for option in question.options]
        assert len(options) == len(set(options))
        assert (question.kind == "text") == (not options)
        assert (question.kind == "check") == (question.correct is not None)
        assert question.correct is None or question.correct in options
    # The goal cannot be listed in advance: it is written freely.
    assert next(q for q in questions if q.id == "goal").kind == "text"


def test_example_profiles_answer_every_question_with_the_questions_options(questions):
    profiles = load_profiles(ROOT / "config" / "profiles.yaml")
    assert [profile.id for profile in profiles] == ["p1", "p2", "p3"]
    for profile in profiles:
        assert set(profile.answers) == {question.id for question in questions}
        assert all(answer_texts(questions, profile.answers).values())  # every option exists


def test_choices_reach_the_model_as_text_with_the_learners_own_words(questions):
    texts = answer_texts(
        questions,
        {
            "tools": ChoiceAnswer(choices=["git", "sql"], details="SQL for weekly reports"),
            "code_check": ChoiceAnswer(choices=["a"]),
            "math": ChoiceAnswer(),
            "goal": "Speech recognition for Uzbek",
        },
    )
    assert texts["tools"] == "Chose: Git; SQL. In their own words: SQL for weekly reports"
    assert texts["code_check"] == "Picked: ann bob (wrong; the right answer is bob ann)."
    assert texts["math"] == "" and texts["goal"] == "Speech recognition for Uzbek"
    assert "(right)" in answer_texts(questions, {"code_check": ChoiceAnswer(choices=["b"])})["code_check"]
    # The model sees the code the question is about.
    assert "sorted(scores, key=scores.get" in format_answers(questions, texts)


@pytest.mark.parametrize(
    "answers",
    [
        {"math": ChoiceAnswer(choices=["genius"])},
        {"math": ChoiceAnswer(choices=["school", "faded"])},
        {"code_check": ChoiceAnswer(choices=["a", "b"])},
        {"pets": "two cats"},
    ],
)
def test_options_a_question_does_not_offer_are_refused(questions, answers):
    with pytest.raises(ValueError):
        answer_texts(questions, answers)


def test_unanswered_questions_are_marked_in_the_prompt(questions):
    text = format_answers(questions, {"goal": "Computer vision research"})
    assert "A: Computer vision research" in text
    assert text.count("A: (no answer)") == len(questions) - 1
