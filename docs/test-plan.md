# Test Plan — Personalized Learning Roadmap

Maps every Baseline, Target and Stretch item of the S2 brief to the test that checks it, and records the
result. Companion to [project-overview.md](project-overview.md).

## 0. Results at a glance (21 November 2026)

- `pytest`: **230 tests pass**, eight of them on the real curriculum. The model is a stub, so these check
  everything code decides.
- The whole flow ran with GPT-6 Luna on 20 November on a local copy of the site and the API: level, path,
  checkpoints with an open question, suggestions after a checkpoint, the assistant, project review and goal
  change.
- Model quality was measured on both curriculum versions (§6).
- Five learners outside the team used the product in November ([learner-testing.md](learner-testing.md)).
- The page was checked in a browser at 1200 px and 375 px wide.

## 1. Principles

- **Code is tested where code decides** (parsing, order, attribution, grading, locks): unit tests with exact
  expected output.
- **The model is tested where it judges** (level, decisions, questions, reviews): against measured properties —
  stability, agreement with expected decisions — rather than exact output, in dated reports in
  `docs/test-results/`, not in CI.
- Nothing is reported as tested unless it was run.

## 2. Test levels

| Level | What it covers | Tooling |
|---|---|---|
| Unit | Parsing, order, attribution, fallback, grading, locks, topics, accounts | `pytest` |
| Integration | Questions → level → path → checkpoints → progress → project review through the HTTP API, model stubbed | `pytest`, FastAPI's test client, `tests/helpers.py` (`FakeLLM`) |
| Browser | The page on the curriculum site against a running API | Playwright scenario, run by hand |
| Model quality | Stability, agreement with expected decisions, difference between profiles | `python -m roadmap compare`, reports in `docs/test-results/` |
| People | Five learners outside the team | [learner-testing.md](learner-testing.md) |

## 3. Baseline

| DoD item | Test | Result |
|---|---|---|
| Onboarding covers background and goal | `test_onboarding_schema` | passing — 7 questions: 5 choice, 1 code, the goal as text |
| Infers a level and explains it | `test_level_inference_returns_evidence`, `test_an_assessment_without_evidence_is_rejected` | passing; live with GPT-6 Luna on 20 November |
| Level can be corrected | `test_learner_override_replaces_model_level` | passing |
| Ordered path | `test_path_follows_course_order_whatever_order_the_model_answers_in` | passing — the path keeps the course order (no prerequisite graph, see architecture) |
| Skipped material marked and justified | `test_a_plan_that_leaves_out_modules_is_not_used` — every module gets a decision with a reason | passing |
| Three profiles, visibly different paths | `python -m roadmap compare`, 5 runs per profile | current version, `gpt-6-luna` (20 November): P1–P2 differ by 20–30%, P2–P3 by 25–40%, P1–P3 by 45–65% of modules; October 6 version, `gemini-3.5-flash-lite` (21 October): 40–50%, 50–54%, 75–85% |
| Licence attribution | `test_every_module_in_a_path_carries_its_source` | passing — modules carry title and URL, the path carries the licence |
| Decisions editable and confirmed before use | `test_learner_can_change_any_planner_decision`, `test_a_change_after_confirmation_needs_a_new_confirmation` | passing |
| Works without a model | `test_fallback_planner_no_llm` | passing — the whole course in order, nothing skipped |

## 4. Target

| DoD item | Test | Result |
|---|---|---|
| Checkpoints generated from module content | `test_generated_questions_must_name_the_modules_own_topics`, `test_a_question_has_four_distinct_options_and_one_answer`, `test_the_generator_writes_two_open_questions_a_topic` | passing; checkpoints for 13 modules generated with GPT-6 Luna |
| Progress blocked past a failed checkpoint | `test_a_failed_checkpoint_locks_what_follows_until_it_is_passed`, `test_a_failed_attempt_hides_the_answers_and_locks_the_rest_until_a_retake_passes`, `test_a_failed_attempt_names_topics_to_review_but_not_the_answers` | passing; the lock is kept on the server |
| Open questions marked by the model | `test_an_open_answer_counts_when_it_makes_enough_rubric_points`, `test_an_answer_that_states_something_wrong_does_not_count_even_with_enough_points`, `test_without_a_model_the_open_question_is_left_out_and_one_fewer_right_answer_passes` | passing |
| Path adapts to failure or an easy pass | `test_a_failed_prove_becomes_study_and_the_path_stays_confirmed`, `test_a_failed_checkpoint_turns_the_skimmed_topics_it_got_wrong_to_study`, `test_a_perfect_first_checkpoint_brings_lighter_suggestions_for_later_modules` | passing; live with GPT-6 Luna on 20 November |
| Topics: study, skim or skip | `test_the_learner_studies_skims_or_skips_a_topic_without_a_new_confirmation`, `test_a_skipped_topic_leaves_the_checkpoint_and_its_problem` | passing |
| A usable web interface | Browser scenario at 1200 px and 375 px | passing; used by five learners |
| Five learners outside the team | [learner-testing.md](learner-testing.md) | done, November 2026 |
| Business case | The business plan | done |

## 5. Stretch

| Item | Test | Result |
|---|---|---|
| Coding problems checked against tests | `test_a_coding_problem_must_be_python_and_its_solution_must_pass_its_tests`, `test_the_tests_must_reject_every_wrong_solution`, `test_a_coding_problem_follows_the_questions_before_the_module_counts_as_passed` | passing; runs in the browser (Pyodide 0.26.4) |
| Goal change with replanning | `test_a_new_goal_replans_what_is_not_started_and_asks_for_confirmation` | passing; live with GPT-6 Luna on 20 November |
| Drop-off analysis for the owner | `test_only_shared_paths_are_counted_and_the_report_needs_its_token`, `test_reviewers_see_the_report_on_the_site_and_learners_do_not` | passing |
| Peer recommendation | — | not built |

Beyond the plan:

| Feature | Test | Result |
|---|---|---|
| Accounts | `tests/test_accounts.py`, `tests/test_google.py`, `test_signing_in_again_finds_the_path_and_wrong_passwords_are_refused` | passing |
| Project review | `test_a_criterion_counts_only_with_evidence_that_is_in_the_files`, `test_a_project_passes_when_every_criterion_of_the_passing_level_holds`, `test_only_github_repositories_are_read_from_links` | passing; live with GPT-6 Luna on 20 November |
| Public progress link | `test_a_public_link_shows_what_the_learner_finished_and_nothing_private`, `test_deleting_the_account_ends_its_public_link` | passing |
| Question reports | `test_a_learner_reports_a_question_and_reviewers_see_it_with_the_answer_key` | passing |
| Assistant | `test_after_a_failed_checkpoint_the_assistant_sees_the_topics_of_the_wrong_answers` | passing; live with GPT-6 Luna on 20 November |

## 6. Model quality

Stability and agreement with the [expected decisions](test-results/expected-decisions.md), 5 runs per profile:

| Curriculum | Model | Stable | Match | Report |
|---|---|---|---|---|
| Current (20 modules) | `gpt-6-luna` | 87% | 98% | [20 November](test-results/2026-11-20-current-curriculum.md) |
| October 6 (18 modules) | `gemini-3.5-flash-lite` | 93% | 96% | [21 October](test-results/2026-10-21-model-stability.md) |

## 7. Not tested

- Load and performance: not needed at our scale.
- Security beyond the code's own limits (archive sizes, GitHub-only links, no code run on the server) and the
  key check before every commit.

## 8. Test data

| Fixture | Contents | Location |
|---|---|---|
| Example learners | Three invented profiles | `config/profiles.yaml` |
| Curriculum subset | A small invented course in the same Docusaurus format | `tests/fixtures/docs/` |
| Stub model | Canned answers for every model call | `tests/helpers.py` (`FakeLLM`) |
| Checkpoints | 15 files, reviewed; coding problems whose reference solutions pass and, in the current version, whose wrong solutions fail | `checkpoints/` |

No data from real learners is committed.
