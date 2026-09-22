# Test Plan — Personalized Learning Roadmap

Companion to [`docs/project-overview.md`](./project-overview.md). Maps every Baseline and Target
Definition-of-Done item from the S2 brief to a concrete, checkable test, so "it works" is never asserted
without a way to verify it.

## 0. Current stage

**No code exists yet** — only planning documents (`docs/project-overview.md`, `docs/team-rnr.md`,
`docs/ground-rules.md`, `docs/questions.md`) and repo scaffolding (`.env.example`, `.gitignore`,
`requirements.txt` as a placeholder). This document is written for that stage: every test case below is
**planned**, not implemented, and each has a `Status` column tracking that. Nothing here is a test report —
that comes later, in `docs/test-results/`, once tests actually run.

As code lands, update the `Status` column in this file (`planned` → `written` → `passing`) instead of moving
test cases elsewhere — keeping the plan and its current state in one place is more useful than a separate
progress tracker.

Two directories this document refers to throughout — `tests/` and `docs/test-results/` — do not exist in
the repository yet either. They get created with the first fixture file and the first dated report,
respectively, not before.

## 1. Scope and principles

- **Code is tested where code makes the decision** (parsing, prerequisite graph, path ordering,
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
| Unit | Content parsing, prerequisite graph, path ordering, attribution formatting, fallback planner | `pytest` | The relevant module to exist |
| Integration | Onboarding → level inference → path generation, end to end, with the model mocked | `pytest` + fixture LLM responses | The core pipeline wired together |
| Data-driven / offline eval | Level inference agreement, path difference across profiles, checkpoint question quality, output stability | `pytest` scripts writing results to `docs/test-results/` | A working planner and a model connection |
| Manual / human-in-the-loop | Skip-justification spot checks, real-learner testing (Target), checkpoint question review | Checklist + write-up, no automation | A runnable path to show a learner |

## 3. Baseline test cases

| DoD item | Test | Pass condition | Status |
|---|---|---|---|
| Onboarding questions cover background and goal | `test_onboarding_schema` — validates the question config file loads and each question has a non-empty prompt and expected-answer type | Loads without error; all required onboarding questions are present, including questions covering coding background and learning goal. | planned — config file not yet created |
| Infers a level from answers, explains reasoning | `test_level_inference_returns_evidence` — mocked and live-call tests assert the response always contains `level`, `evidence`, `confidence` fields | 100% of mocked-response tests pass; live-call smoke test run manually before each milestone | planned — depends on model choice (Q-003) |
| Level inference correctable | `test_learner_override_replaces_model_level` — planner is called with an explicit override and asserted to plan against the override, not the inferred level | Planner output level == override in all cases | planned |
| Ordered path from prerequisite graph | `test_topological_order_respects_prerequisites` — for a fixed graph fixture, assert no node appears before any of its prerequisites | 0 violations across the full parsed graph | planned — depends on prerequisite graph being authored |
| Skipped material explicitly marked and justified | `test_skipped_nodes_have_justification` — every node absent from a generated path appears in a `skipped` list with a non-empty reason string | 100% coverage, no silent omissions | planned |
| Three profiles produce visibly different paths | `test_profile_paths_differ` — three fixed example profiles (novice/backend-experienced/CV-goal, per §11.2 of the overview) are run through the real planner and the pairwise share of non-overlapping included nodes is computed | Each pair differs by a set threshold (proposed: ≥30% non-overlap) — record the actual number | planned — can write the fixture profiles now, before the planner exists |
| Licence attribution correct | `test_every_resource_has_attribution` — every emitted resource object carries `title`, `url`, `licence` | 100% coverage; licence string matches source exactly | planned |
| Rule-based fallback works with no model | `test_fallback_planner_no_llm` — planner is run with the model client replaced by a stub that raises, and must still return a valid path using only the prerequisite graph and declared difficulty | Valid path returned, `personalization_unavailable` flag set | planned |

## 4. Target test cases (write these once the feature exists — don't block on it)

| DoD item | Test | Pass condition | Status |
|---|---|---|---|
| Checkpoint questions generated from section content | `test_checkpoint_generation` (data-driven) — generate 10 questions for one module, rated by a team member who knows the topic, per §11.1 of the overview | ≥8/10 rated as actually checking understanding, not generic/pattern-matchable | not started — Target-tier, depends on Baseline planner |
| Progress blocked on failed checkpoint | `test_checkpoint_blocks_advance` — simulate a failed checkpoint answer and assert the next node is not served | Learner state does not advance past the failed node | not started |
| Path adapts to failure/easy pass | `test_replan_on_failure` / `test_replan_on_easy_pass` — assert the remaining path changes relative to the original plan | Replanned path differs from original in the expected direction | not started |
| Real-learner testing | Manual — ≥5 learners outside the team complete onboarding and receive a path; observations logged in `docs/test-results/learner-sessions.md` | 5 sessions logged with what broke, not just "it worked" | not started — needs a runnable path first |
| Business case quantified | Cross-checked against measured numbers from the corpus/data-driven tests, not estimates | Every number in the business case traces to a test result in this plan | not started |

## 5. Model-quality tests (data-driven, no fixed expected output)

- **Level-inference agreement.** For a set of onboarding answers with a known self-reported level, compare
  inferred vs. self-reported. Success bar (from the overview): agreement in most cases, every disagreement
  explainable from the answers given — logged by hand, not auto-scored.
- **Skip-justification spot check.** Sample N skip reasons per test run, a team member checks each against
  the learner's stated background. Logged pass/fail with notes.
- **Output stability.** Run the same fixed profile N times (propose N=10); compute the share of nodes that
  stay constant across runs. Report the number — this is a measured tolerance, not a binary pass/fail,
  per §11.6 of the overview.
- **Checkpoint question quality.** See Target table above.

None of these can run before a model is chosen (Q-003) and the planner exists. They go in
`docs/test-results/` as dated markdown reports, not asserted in CI — an LLM call is non-deterministic and a
CI failure on a stochastic threshold is noise. Run them on a schedule (e.g. before each milestone
submission) once there's something to run.

## 6. What can be started right now, with no code

- `tests/fixtures/profiles.json` — the three (or more) example learner profiles. These are invented text,
  not code, and don't depend on anything else existing.
- `tests/fixtures/curriculum_sample.json` — a small hand-picked slice of the parsed curriculum, once the
  MDX parsing format is settled, for fast unit tests that don't need the full 151-section graph.
- The onboarding question set itself (`test_onboarding_schema`'s subject) — a config file, no logic needed.

Writing these now means the first real pytest run, once the planner exists, has fixtures ready rather than
becoming a second project.

## 7. What is explicitly not tested yet

- Stretch items — no test written until the team starts one (auto-graded coding problems, mid-path replan,
  peer recommendation, drop-off analytics).
- Load/performance testing — out of scope for a class project with no expected concurrent load.
- Security testing beyond "no API key committed" (covered by `.gitignore` + `.env.example`, not a test).

## 8. Test data and fixtures

| Fixture | Contents | Location | Status |
|---|---|---|---|
| Three example learner profiles | Invented, not real-learner data (per overview §7) | `tests/fixtures/profiles.json` | can write now |
| Curriculum subset | A pinned small slice of the parsed graph | `tests/fixtures/curriculum_sample.json` | blocked on parser format |
| Mocked LLM responses | Canned `level`/`evidence`/`confidence` and checkpoint-question responses | `tests/fixtures/llm_responses/` | blocked on model choice (Q-003) |

Real learner session data (Target item) is never committed — per the ground rules and README, it stays out
of the repository entirely; only the write-up goes in `docs/test-results/`.

## 9. Traceability

Each pytest test function name should start with `test_` followed by the DoD line it checks, so
`grep test_ tests/` roughly reproduces this table. Keep this document and the README's
"Test results, known errors and limitations" section in sync — the README states the *result*, this
document states the *method and current status*.
