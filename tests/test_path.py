import pytest
from pydantic import ValidationError

from roadmap import Choice, Curriculum, LearningPath, PathItem, path_difference


def path_with(curriculum: Curriculum, choices: dict[str, Choice]) -> LearningPath:
    """A path that skips every module except those given choices."""
    return LearningPath(
        level=None,
        assessment=None,
        items=[
            PathItem.suggestion(module, choices.get(module.id, Choice.SKIP), "Test.")
            for module in curriculum.modules
        ],
        personalization_unavailable=False,
        curriculum_version=curriculum.version,
        attribution=curriculum.attribution,
    )


def test_path_difference_is_the_share_of_kept_modules_treated_differently(curriculum):
    def difference(first: dict[str, Choice], second: dict[str, Choice]) -> float:
        return path_difference(
            path_with(curriculum, first), path_with(curriculum, second)
        )

    terminal, algebra, vision = (
        "basics/terminal",
        "basics/algebra",
        "tracks/vision/resources",
    )
    study, prove = Choice.STUDY, Choice.PROVE
    assert difference({terminal: study}, {terminal: study}) == 0
    assert difference({terminal: study}, {algebra: study}) == 1
    assert difference(
        {terminal: study, algebra: study}, {algebra: study, vision: study}
    ) == pytest.approx(2 / 3)
    # Proving a module and studying it count as different.
    assert (
        difference({terminal: prove, algebra: study}, {terminal: study, algebra: study})
        == 0.5
    )


def test_learner_can_change_any_planner_decision(curriculum):
    suggested = path_with(curriculum, {"basics/terminal": Choice.STUDY})

    changed = suggested.with_choice("basics/terminal", Choice.PROVE)
    changed = changed.with_choice("basics/algebra", Choice.STUDY)

    terminal, algebra, *rest = changed.items
    assert (terminal.suggested, terminal.choice) == (Choice.STUDY, Choice.PROVE)
    assert (algebra.suggested, algebra.choice) == (Choice.SKIP, Choice.STUDY)
    assert terminal.changed_by_learner and algebra.changed_by_learner
    # The planner's reason stays next to the learner's choice.
    assert terminal.reason == algebra.reason == "Test."
    assert not any(item.changed_by_learner for item in rest)
    # The original path is left as it was.
    assert not any(item.changed_by_learner for item in suggested.items)


def test_only_a_module_with_a_checklist_can_be_proved(curriculum):
    path = path_with(curriculum, {})

    with pytest.raises(ValidationError):
        path.with_choice("basics/algebra", Choice.PROVE)  # algebra has no checklist


def test_a_change_after_confirmation_needs_a_new_confirmation(curriculum):
    confirmed = path_with(curriculum, {"basics/terminal": Choice.STUDY}).confirm()
    assert confirmed.confirmed

    assert not confirmed.with_choice("basics/algebra", Choice.STUDY).confirmed


def test_a_choice_for_a_module_the_path_does_not_have_is_an_error(curriculum):
    with pytest.raises(KeyError):
        path_with(curriculum, {}).with_choice("made/up", Choice.STUDY)
