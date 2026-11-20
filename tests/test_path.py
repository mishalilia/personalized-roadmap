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
    # The path made the change, so it is its suggestion, not the learner's own choice.
    assert item.choice is Choice.STUDY and item.suggested is Choice.STUDY
    assert item.adjustment and "1/5" in item.adjustment
    assert failed.confirmed

    passed = failed.with_checkpoint_result(TERMINAL, 5, 5, passed=True)
    note = passed.item(TERMINAL).adjustment
    assert note and "passed on attempt 2 (5/5)" in note and "take the checkpoint again" not in note


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


def test_the_learner_studies_skims_or_skips_a_topic_without_a_new_confirmation(curriculum):
    from roadmap.curriculum import Topic
    from roadmap.path import PathStateError, SkimTopic, TopicChoice

    first, second, third = "1. Shell Basics", "2. Files", "3. Git"
    module = curriculum.modules[0].model_copy(
        update={"topics": [Topic(title=first), Topic(title=second), Topic(title=third)]}
    )
    items = [
        PathItem.suggestion(
            module if i == 0 else m, Choice.STUDY, "Study it.",
            skim=[SkimTopic(topic=second, reason="You use it daily.")] if i == 0 else None,
        )
        for i, m in enumerate(curriculum.modules)
    ]
    path = path_with(curriculum, {}).model_copy(update={"items": items}).confirm()

    marked = path.with_topic(module.id, first, TopicChoice.SKIM).with_topic(module.id, third, TopicChoice.SKIP)
    item = marked.item(module.id)
    assert [s.topic for s in item.skim] == [first, second]  # in the module's order
    assert item.skim[0].chosen and not item.skim[1].chosen
    assert item.skipped_topics == {third} and marked.confirmed

    moved = marked.with_topic(module.id, second, TopicChoice.SKIP)  # from skim to skip
    assert moved.item(module.id).skipped_topics == {second, third}
    assert [s.topic for s in moved.item(module.id).skim] == [first]
    back = moved.with_topic(module.id, second, TopicChoice.STUDY)
    assert back.item(module.id).skipped_topics == {third} and second not in back.item(module.id).skimmed_topics

    with pytest.raises(PathStateError):  # every topic left out: that is skipping the module
        moved.with_topic(module.id, first, TopicChoice.SKIP)
    with pytest.raises(KeyError):
        path.with_topic(module.id, "No such topic", TopicChoice.SKIP)
    proved = marked.with_choice(module.id, Choice.PROVE)
    assert proved.item(module.id).skipped_topics == frozenset()  # a module proved is checked whole
    with pytest.raises(PathStateError):
        proved.with_topic(module.id, first, TopicChoice.SKIP)


def test_a_projects_parts_cannot_be_skimmed_or_skipped(curriculum):
    from roadmap.curriculum import Topic
    from roadmap.path import PathStateError, TopicChoice

    project = curriculum.modules[0].model_copy(
        update={"id": "track/capstone", "topics": [Topic(title="Deliverables"), Topic(title="Rubric")]}
    )
    items = [PathItem.suggestion(project if i == 0 else m, Choice.STUDY, "Build it.") for i, m in enumerate(curriculum.modules)]
    path = path_with(curriculum, {}).model_copy(update={"items": items})

    with pytest.raises(PathStateError):
        path.with_topic(project.id, "Deliverables", TopicChoice.SKIP)


def _with_topics(curriculum: Curriculum, module_id: str, titles: list[str], skim: list[str]) -> LearningPath:
    """A confirmed path studying every module; `module_id` has the given topics and skims some of them."""
    from roadmap.curriculum import Topic
    from roadmap.path import SkimTopic

    items = []
    for module in curriculum.modules:
        if module.id == module_id:
            module = module.model_copy(update={"topics": [Topic(title=t) for t in titles]})
        marks = [SkimTopic(topic=t, reason="You know it.") for t in skim] if module.id == module_id else None
        items.append(PathItem.suggestion(module, Choice.STUDY, "Study it.", skim=marks))
    return path_with(curriculum, {}).model_copy(update={"items": items}).confirm()


def test_a_failed_checkpoint_turns_the_skimmed_topics_it_got_wrong_to_study(curriculum):
    path = _with_topics(curriculum, TERMINAL, ["1. Shell Basics", "2. Files", "3. Git"], ["2. Files", "3. Git"])

    failed = path.with_checkpoint_result(TERMINAL, 1, 5, passed=False, missed_topics=["Files", "Shell Basics"])

    item = failed.item(TERMINAL)
    assert [marked.topic for marked in item.skim] == ["3. Git"]  # the skimmed topic it got right stays
    assert "Changed to study in full: 2. Files" in (item.adjustment or "")


def test_after_a_failure_only_heavier_suggestions_are_kept_even_for_locked_modules(curriculum):
    from roadmap.path import TopicChoice

    path = _with_topics(curriculum, NOTES, ["Intro", "Practice"], ["Intro"])
    path = path.with_choice(VISION, Choice.STUDY).with_choice(
        "tracks/speech/resources", Choice.SKIP
    ).confirm()
    failed = path.with_checkpoint_result(TERMINAL, 1, 5, passed=False, missed_topics=["Shell Basics"])
    assert NOTES in failed.locked_module_ids

    suggested = failed.with_proposals(
        [
            Proposal(module_id="tracks/speech/resources", choice=Choice.STUDY, reason="Skipped.", after_failure=True),
            Proposal(module_id=ALGEBRA, choice=Choice.SKIP, reason="Lighter.", after_failure=True),
            Proposal(
                module_id=NOTES, topic="Intro", topic_choice=TopicChoice.STUDY, reason="Uses the shell.",
                after_failure=True,
            ),
            Proposal(
                module_id=NOTES, topic="Practice", topic_choice=TopicChoice.SKIM, reason="Lighter.",
                after_failure=True,
            ),
        ]
    )

    # The skipped module stays skipped, the lighter one is dropped; the topic of a kept module gets heavier.
    assert [(p.module_id, p.topic) for p in suggested.proposals] == [(NOTES, "Intro")]


def test_the_learner_accepts_or_declines_a_suggestion_about_one_topic(curriculum):
    from roadmap.path import TopicChoice

    path = _with_topics(curriculum, NOTES, ["Intro", "Practice"], ["Intro", "Practice"]).with_proposals(
        [
            Proposal(module_id=NOTES, topic=t, topic_choice=TopicChoice.STUDY, reason="Needed.", after_failure=True)
            for t in ("Intro", "Practice")
        ]
    )

    accepted = path.accept(NOTES, "Intro")
    assert accepted.item(NOTES).topic_choice("Intro") is TopicChoice.STUDY
    assert accepted.item(NOTES).topic_choice("Practice") is TopicChoice.SKIM
    assert accepted.confirmed
    declined = accepted.decline(NOTES, "Practice")
    assert declined.proposals == [] and declined.item(NOTES).topic_choice("Practice") is TopicChoice.SKIM


def test_a_proposal_changes_a_module_or_a_topic_not_both(curriculum):
    from roadmap.path import TopicChoice

    with pytest.raises(ValidationError):
        Proposal(module_id=NOTES, choice=Choice.STUDY, topic="Intro", topic_choice=TopicChoice.STUDY, reason="x")
    with pytest.raises(ValidationError):
        Proposal(module_id=NOTES, reason="Nothing to change.")


def test_suggestions_for_a_checkpoint_taken_again_meanwhile_are_dropped(curriculum):
    path = confirmed(curriculum, {TERMINAL: Choice.STUDY, NOTES: Choice.PROVE}).model_copy(
        update={"suggestions_pending": f"{TERMINAL}:2"}
    )
    late = [Proposal(module_id=NOTES, choice=Choice.STUDY, reason="Needed.", after_failure=True)]

    assert path.with_suggestions(f"{TERMINAL}:1", late).proposals == []
    landed = path.with_suggestions(f"{TERMINAL}:2", late)
    assert [p.module_id for p in landed.proposals] == [NOTES] and landed.suggestions_pending is None


def test_the_learner_marks_topics_of_a_module_they_study_as_finished(curriculum):
    from roadmap.curriculum import Topic
    from roadmap.path import TopicChoice

    first, second, third = "1. Shell Basics", "2. Files", "3. Git"
    module = curriculum.modules[0].model_copy(
        update={"topics": [Topic(title=first), Topic(title=second), Topic(title=third)]}
    )
    items = [
        PathItem.suggestion(module if i == 0 else m, Choice.STUDY, "Study it.")
        for i, m in enumerate(curriculum.modules)
    ]
    unconfirmed = path_with(curriculum, {}).model_copy(update={"items": items})
    with pytest.raises(PathStateError):  # as with all progress: only on a confirmed path
        unconfirmed.with_topic_finished(module.id, first, True)
    path = unconfirmed.confirm()

    marked = path.with_topic_finished(module.id, third, True).with_topic_finished(module.id, first, True)
    assert marked.item(module.id).finished_topics == [first, third]  # in the module's order
    assert marked.item(module.id).progress is Progress.NOT_STARTED and marked.confirmed  # a tally, not a pass
    assert marked.with_topic_finished(module.id, third, False).item(module.id).finished_topics == [first]

    # A topic left out is not one to finish, and skipping it takes the mark away.
    skipped = marked.with_topic(module.id, third, TopicChoice.SKIP)
    assert skipped.item(module.id).finished_topics == [first]
    with pytest.raises(PathStateError):
        skipped.with_topic_finished(module.id, third, True)
    with pytest.raises(KeyError):
        path.with_topic_finished(module.id, "No such topic", True)
    with pytest.raises(PathStateError):  # a module proved is checked whole
        path.with_choice(module.id, Choice.PROVE).confirm().with_topic_finished(module.id, first, True)


def test_a_finished_modules_decision_no_longer_changes(curriculum):
    module_id = curriculum.modules[0].id
    path = confirmed(curriculum, {m.id: Choice.STUDY for m in curriculum.modules})
    done = path.with_checkpoint_result(module_id, 5, 5, True, False)
    assert done.item(module_id).progress is Progress.PASSED
    with pytest.raises(PathStateError):
        done.with_choice(module_id, Choice.SKIP)
    assert done.with_choice(module_id, done.item(module_id).choice).item(module_id).progress is Progress.PASSED
