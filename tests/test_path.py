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


# Progress through a path: checkpoints, locking, and suggestions after a checkpoint.

from roadmap.path import Progress, Proposal, PathStateError  # noqa: E402

TERMINAL, ALGEBRA, NOTES, VISION = (
    "basics/terminal",
    "basics/algebra",
    "tracks/notes",
    "tracks/vision/resources",
)


def confirmed(curriculum: Curriculum, choices: dict[str, Choice]) -> LearningPath:
    return path_with(curriculum, choices).confirm()


def test_a_failed_checkpoint_locks_what_follows_until_it_is_passed(curriculum):
    path = confirmed(
        curriculum,
        {TERMINAL: Choice.STUDY, ALGEBRA: Choice.STUDY, VISION: Choice.STUDY},
    )

    failed = path.with_checkpoint_result(TERMINAL, 2, 5, passed=False)

    assert failed.item(TERMINAL).progress is Progress.FAILED
    assert failed.blocking_module_id == TERMINAL
    assert ALGEBRA in failed.locked_module_ids and VISION in failed.locked_module_ids
    with pytest.raises(PathStateError):
        failed.marked_done(ALGEBRA)

    passed = failed.with_checkpoint_result(TERMINAL, 4, 5, passed=True)
    assert passed.locked_module_ids == [] and passed.blocking_module_id is None
    assert passed.item(TERMINAL).attempts == 2
    assert passed.item(TERMINAL).last_score == "4/5"
    assert passed.marked_done(ALGEBRA).item(ALGEBRA).progress is Progress.DONE


def test_a_failed_prove_becomes_study_and_the_path_stays_confirmed(curriculum):
    path = confirmed(curriculum, {TERMINAL: Choice.PROVE})

    failed = path.with_checkpoint_result(TERMINAL, 1, 5, passed=False)

    item = failed.item(TERMINAL)
    assert item.choice is Choice.STUDY and item.suggested is Choice.PROVE
    assert item.adjustment and "1/5" in item.adjustment
    assert failed.confirmed


def test_progress_needs_a_confirmed_path_and_an_included_module(curriculum):
    with pytest.raises(PathStateError):
        path_with(curriculum, {TERMINAL: Choice.STUDY}).marked_done(TERMINAL)
    with pytest.raises(PathStateError):
        confirmed(curriculum, {TERMINAL: Choice.STUDY}).marked_done(ALGEBRA)


def test_only_suggestions_that_lighten_a_module_not_started_are_kept(curriculum):
    path = confirmed(
        curriculum,
        {
            TERMINAL: Choice.STUDY,
            ALGEBRA: Choice.STUDY,
            NOTES: Choice.PROVE,
            VISION: Choice.STUDY,
        },
    ).marked_done(ALGEBRA)

    with_proposals = path.with_proposals(
        [
            Proposal(module_id=TERMINAL, choice=Choice.PROVE, reason="Shown."),
            Proposal(module_id=ALGEBRA, choice=Choice.SKIP, reason="Already done."),
            Proposal(module_id=NOTES, choice=Choice.SKIP, reason="Lighter."),
            Proposal(module_id=VISION, choice=Choice.STUDY, reason="Not lighter."),
        ]
    )

    assert [p.module_id for p in with_proposals.proposals] == [TERMINAL, NOTES]


def test_a_suggestion_to_prove_a_module_without_a_checklist_is_dropped(curriculum):
    path = confirmed(curriculum, {ALGEBRA: Choice.STUDY})

    kept = path.with_proposals(
        [Proposal(module_id=ALGEBRA, choice=Choice.PROVE, reason="Shown.")]
    )

    assert kept.proposals == []


def test_the_learner_accepts_or_declines_each_suggestion(curriculum):
    path = confirmed(
        curriculum, {TERMINAL: Choice.STUDY, VISION: Choice.STUDY}
    ).with_proposals(
        [
            Proposal(module_id=TERMINAL, choice=Choice.PROVE, reason="Shown."),
            Proposal(module_id=VISION, choice=Choice.SKIP, reason="Known."),
        ]
    )

    accepted = path.accept(TERMINAL)
    assert accepted.item(TERMINAL).choice is Choice.PROVE
    assert accepted.confirmed
    assert [p.module_id for p in accepted.proposals] == [VISION]

    declined = accepted.decline(VISION)
    assert declined.proposals == [] and declined.item(VISION).choice is Choice.STUDY
    with pytest.raises(PathStateError):
        declined.accept(VISION)


def test_a_path_saved_before_checkpoints_still_opens(curriculum):
    old = path_with(curriculum, {TERMINAL: Choice.STUDY}).model_dump(mode="json")
    for key in ("answers", "proposals", "locked_module_ids", "blocking_module_id"):
        old.pop(key)
    for item in old["items"]:
        for key in ("progress", "attempts", "last_score", "adjustment"):
            item.pop(key)
        item["module"].pop("topics")

    opened = LearningPath.model_validate(old)

    assert all(item.progress is Progress.NOT_STARTED for item in opened.items)
    assert opened.locked_module_ids == []


def test_passed_questions_with_a_problem_leave_the_module_in_practice_until_it_is_solved(
    curriculum,
):
    path = confirmed(curriculum, {TERMINAL: Choice.STUDY, ALGEBRA: Choice.STUDY})

    practice = path.with_checkpoint_result(
        TERMINAL, 5, 5, passed=True, problem_pending=True
    )

    assert practice.item(TERMINAL).progress is Progress.PRACTICE
    assert not practice.item(TERMINAL).finished
    assert practice.locked_module_ids == []  # practice does not lock what follows
    assert (
        practice.with_problem_solved(TERMINAL).item(TERMINAL).progress
        is Progress.PASSED
    )
    with pytest.raises(PathStateError):
        path.with_problem_solved(TERMINAL)


def test_a_new_goal_keeps_started_modules_and_takes_new_decisions_for_the_rest(
    curriculum,
):
    path = confirmed(
        curriculum, {TERMINAL: Choice.STUDY, VISION: Choice.STUDY}
    ).marked_done(TERMINAL)
    planned = [
        PathItem.suggestion(module, Choice.SKIP, "New goal.")
        for module in curriculum.modules
    ]

    changed = path.with_new_goal("Speech", planned)

    assert changed.item(TERMINAL).choice is Choice.STUDY
    assert changed.item(TERMINAL).progress is Progress.DONE
    assert changed.item(VISION).choice is Choice.SKIP
    assert changed.answers["goal"] == "Speech" and not changed.confirmed


def test_the_time_estimate_counts_studied_modules_fully_and_proved_ones_in_part(
    curriculum,
):
    from roadmap import Hours

    with_hours = curriculum.model_copy(
        update={
            "modules": [
                module.model_copy(
                    update={
                        "hours": (
                            Hours(low=10, high=20)
                            if module.id in (TERMINAL, ALGEBRA)
                            else None
                        )
                    }
                )
                for module in curriculum.modules
            ]
        }
    )
    path = path_with(
        with_hours,
        {TERMINAL: Choice.PROVE, ALGEBRA: Choice.STUDY, VISION: Choice.STUDY},
    )

    estimate = path.time_estimate

    assert (estimate.path_low, estimate.path_high) == (12, 24)
    assert (estimate.course_low, estimate.course_high) == (20, 40)
    assert estimate.modules_without_estimate == 1  # vision is included and has none
