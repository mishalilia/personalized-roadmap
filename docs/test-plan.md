# Test Plan — Personalized Learning Roadmap

Companion to [`docs/project-overview.md`](./project-overview.md). Maps every Baseline and Target
Definition-of-Done item from the S2 brief to a concrete, checkable test, so "it works" is never asserted
without a way to verify it.

## 0. Current stage

**Prototype code exists for the Baseline** (`src/roadmap/`, `app/`, `tests/`). The statuses in §3 come from a
`pytest` run on 3 October 2026. Model runs are reported in `docs/test-results/`; the first report is from
21 October. A clean clone was installed and tested on Windows on 20 October: all 50 tests pass, and without a
key the path falls back to the course order.

As code lands, update the `Status` column in this file (`planned` → `written` → `passing`) instead of moving
test cases elsewhere — keeping the plan and its current state in one place is more useful than a separate
progress tracker.

## 1. Scope and principles

- **Code is tested where code makes the decision** (parsing, path ordering,
  attribution). These are ordinary unit tests with deterministic expected output.
- **The model is tested where the model makes the judgement** (level inference, relevance/skip reasoning,
  checkpoint generation). These cannot have a single "correct" output, so they are tested against
  measurable properties (stability, agreement rate, hand-rated quality) instead of exact-match assertions.
- **Nothing ships untested at the Baseline tier.** Target and Stretch items are tested once they exist;
  they are not blocked on being finished, but a partially-built Target item is not marked done in the
  README until its test in this plan is `passing`.
- Every test case references the DoD line it satisfies, so the README checklist can cite this document
  instead of restating criteria.

## 2. Test levels

| Level | What it covers | Tooling | Needs before it can run |
|---|---|---|---|
| Unit | Content parsing, path ordering, attribution formatting, fallback planner | `pytest` | The relevant module to exist |
| Integration | Onboarding → level inference → path generation, end to end, with the model mocked | `pytest` + fixture LLM responses | The core pipeline wired together |
| Data-driven / offline eval | Level inference agreement, path difference across profiles, checkpoint question quality, output stability | `pytest` scripts writing results to `docs/test-results/` | A working planner and a model connection |
| Manual / human-in-the-loop | Skip-justification spot checks, real-learner testing (Target), checkpoint question review | Checklist + write-up, no automation | A runnable path to show a learner |

## 3. Baseline test cases

| DoD item | Test | Pass condition | Status |
|---|---|---|---|
| Onboarding questions cover background and goal | `test_onboarding_schema` — validates the question config file loads and each question has a non-empty prompt and expected-answer type | Loads without error; all required onboarding questions are present, including questions covering coding background and learning goal. | passing — `config/onboarding.yaml`, 6 questions |
| Infers a level from answers, explains reasoning | `test_level_inference_returns_evidence` — mocked and live-call tests assert the response always contains `level`, `evidence`, `confidence` fields | 100% of mocked-response tests pass; live-call smoke test run manually before each milestone | mocked: passing; live: run by hand for P1–P3 on 3 October with both providers |
| Level inference correctable | `test_learner_override_replaces_model_level` — planner is called with an explicit override and asserted to plan against the override, not the inferred level | Planner output level == override in all cases | passing |
| Ordered path from prerequisite graph | `test_topological_order_respects_prerequisites` — for a fixed graph fixture, assert no node appears before any of its prerequisites | 0 violations across the full parsed graph | replaced: there is no graph, the path keeps the course's own order; `test_path_follows_course_order_whatever_order_the_model_answers_in` passes |
| Skipped material explicitly marked and justified | `test_skipped_nodes_have_justification` — every node absent from a generated path appears in a `skipped` list with a non-empty reason string | 100% coverage, no silent omissions | passing — every module gets a decision (study, prove or skip); a model answer that leaves one out is rejected |
| Three profiles produce visibly different paths | `test_profile_paths_differ` — three fixed example profiles (novice/backend-experienced/CV-goal, per §11.2 of the overview) are run through the real planner and the pairwise share of non-overlapping included nodes is computed | Each pair differs by a set threshold (proposed: ≥30% non-overlap) — record the actual number | passing with `gemini-3.5-flash-lite`, 5 runs per profile on 21 October: P1–P2 40–50%, P1–P3 75–85%, P2–P3 50–54%. With `gpt-oss-120b` one pair of P1 and P2 paths came out identical. A module counts as different when the paths study, prove or skip it differently |
| Licence attribution correct | `test_every_resource_has_attribution` — every emitted resource object carries `title`, `url`, `licence` | 100% coverage; licence string equals `CC BY-NC-SA 4.0` (the source is inconsistent, see Q-001) | passing in a different form, `test_every_module_in_a_path_carries_its_source`: modules carry title and URL, and the path carries the licence; resources carry title and URL only, since they keep their own licences — to confirm with Data & Research |
| Path decisions editable and approved before use (course rule for AI output) | `test_learner_can_change_any_planner_decision`, `test_a_change_after_confirmation_needs_a_new_confirmation`, `test_learner_changes_the_path_and_confirms_it` — the learner changes decisions, the planner's suggestion is kept, and the path can be downloaded only after confirmation | Every decision can be changed; any change clears the confirmation | passing |
| Rule-based fallback works with no model | `test_fallback_planner_no_llm` — planner is run with the model client replaced by a stub that raises, and must still return a valid path in the course order | Valid path returned, `personalization_unavailable` flag set | passing — without a model the path is the whole course, nothing skipped |

## 4. Target test cases
| DoD item | Test | Pass condition | Status |
|---|---|---|---|
| Checkpoint questions generated from section content | `python -m roadmap checkpoints <module>` generates 10 questions from the module's topics, stated outcomes, resource notes and checklist (Q-004); a team member who knows the topic rates them. Code checks: `test_generated_questions_are_numbered_and_kept_as_a_draft`, `test_a_question_has_four_distinct_options_and_one_answer` | ≥8/10 rated as actually checking understanding, not generic/pattern-matchable | generator built and tested with a stub model; **not yet run with a real model, and no rating yet**. Two draft checkpoints in `checkpoints/` were written by Claude for the demo, not by the generator, and are not reviewed |
| Progress blocked on failed checkpoint | `test_a_failed_checkpoint_locks_what_follows_until_it_is_passed`, `test_a_failed_attempt_locks_the_rest_and_a_passed_retake_opens_it` — a failed checkpoint locks every later module until a retake passes; the API refuses progress on a locked module | Learner state does not advance past the failed node | passing. The lock lives in the learner's browser (no accounts), so it can be bypassed by editing it; reported as a limitation. Answers cannot be learned from failed attempts: `test_a_failed_attempt_names_topics_to_review_but_not_the_answers`, `test_options_are_shuffled_the_same_way_within_an_attempt_and_differently_across_attempts` |
| Path adapts to failure/easy pass | `test_a_failed_prove_becomes_study_and_the_path_stays_confirmed` (failure: code rule), `test_a_perfect_first_checkpoint_brings_lighter_suggestions_for_later_modules` and `test_only_suggestions_that_lighten_a_module_not_started_are_kept` (easy pass: the model suggests, the learner accepts or declines) | Replanned path differs from original in the expected direction | passing with a stub model; the easy-pass suggestions are **not yet tried with a real model** |
| Real-learner testing | Manual, per [learner-testing.md](learner-testing.md) — ≥5 learners outside the team complete onboarding, receive a path and take a checkpoint; observations logged in `docs/test-results/learner-sessions.md` | 5 sessions logged with what broke, not just "it worked" | not started — protocol written; needs the API and the site hosted |
| Coding problems in checkpoints | `test_a_coding_problem_follows_the_questions_before_the_module_counts_as_passed`, `test_a_coding_problem_must_be_python_and_its_solution_must_pass_its_tests`; browser scenario: a wrong solution fails with the failed assert, a right one passes the module (Pyodide 0.26.4) | The module passes only after the questions and the problem | passing; checked in a browser on 5 November. Auto-checking runs in the learner's browser, so it is trust-based |
| Business case quantified | Cross-checked against measured numbers from the corpus/data-driven tests, not estimates | Every number in the business case traces to a test result in this plan | not started |

## 5. Model-quality tests (data-driven, no fixed expected output)

- **Level-inference agreement.** For a set of onboarding answers with a known self-reported level, compare
  inferred vs. self-reported. Success bar (from the overview): agreement in most cases, every disagreement
  explainable from the answers given — logged by hand, not auto-scored.
- **Skip-justification spot check.** Sample N skip reasons per test run, a team member checks each against
  the learner's stated background. Logged pass/fail with notes.
- **Output stability.** Run the same fixed profile N times; compute the share of modules whose decision stays
  the same across runs. Report the number — this is a measured tolerance, not a binary pass/fail, per §11.6
  of the overview. Run on 21 October with N = 3–5 per model, together with agreement against the
  [expected decisions](test-results/expected-decisions.md): see
  [2026-10-21-model-stability.md](test-results/2026-10-21-model-stability.md).
- **Checkpoint question quality.** See Target table above.

They go in `docs/test-results/` as dated markdown reports, not asserted in CI — an LLM call is non-deterministic and a
CI failure on a stochastic threshold is noise. Run them on a schedule (e.g. before each milestone
submission) once there's something to run.

## 6. What can be started right now, with no code

Done: the example profiles, a small curriculum for fast tests and the onboarding questions are written; §8
lists where they are.

## 7. What is explicitly not tested yet

- Peer recommendation (Stretch): not started.
- Stretch items started early, tested in code with a stub model only: mid-path goal change
  (`test_a_new_goal_replans_what_is_not_started_and_asks_for_confirmation`) and drop-off analytics
  (`test_only_shared_paths_are_counted_and_the_report_needs_its_token`). Goal change with a real model is not
  yet tried.
- Load/performance testing — out of scope for a class project with no expected concurrent load.
- Security testing beyond "no API key committed" (covered by `.gitignore` + `.env.example`, not a test).

## 8. Test data and fixtures

| Fixture | Contents | Location | Status |
|---|---|---|---|
| Three example learner profiles | Invented, not real-learner data (per overview §7); the web interface offers them too | `config/profiles.yaml` | written |
| Curriculum subset | A small invented course in the same Docusaurus format, so parser tests need neither the network nor curriculum text | `tests/fixtures/docs/` | written |
| Mocked LLM responses | Canned `level`/`evidence`/`confidence` and planner responses, given by a stub model in the tests | `tests/helpers.py` (`FakeLLM`) | written for level and planner; checkpoint responses not yet |

Real learner session data (Target item) is never committed — per the ground rules and README, it stays out
of the repository entirely; only the write-up goes in `docs/test-results/`.

## 9. Traceability

Each pytest test function name should start with `test_` followed by the DoD line it checks, so
`grep test_ tests/` roughly reproduces this table. Keep this document and the README's
"Test results, known errors and limitations" section in sync — the README states the *result*, this
document states the *method and current status*.
