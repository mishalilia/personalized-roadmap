from helpers import ROOT

from roadmap import load_profiles
from roadmap.onboarding import format_answers


def test_onboarding_schema(questions):
    ids = [question.id for question in questions]
    assert len(ids) == len(set(ids))
    assert 6 <= len(questions) <= 8
    assert all(question.text.strip() for question in questions)
    # Coding background and end goal, as the Baseline requires.
    assert {"programming", "goal"} <= set(ids)


def test_example_profiles_answer_every_question(questions):
    profiles = load_profiles(ROOT / "config" / "profiles.yaml")
    assert [profile.id for profile in profiles] == ["p1", "p2", "p3"]
    for profile in profiles:
        assert set(profile.answers) == {question.id for question in questions}


def test_unanswered_questions_are_marked_in_the_prompt(questions):
    text = format_answers(questions, {"goal": "Computer vision research"})
    assert "A: Computer vision research" in text
    assert text.count("A: (no answer)") == len(questions) - 1
