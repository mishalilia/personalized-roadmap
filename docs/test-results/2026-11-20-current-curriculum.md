# Model decisions on the current curriculum, 20 November 2026

The same check as on [21 October](2026-10-21-model-stability.md), on the current curriculum (commit 9fc5573,
20 modules): how much the decisions change between runs, and how often they match the
[expected decisions](expected-decisions.md#current-curriculum-commit-9fc5573-20-modules).

## How it was run

- OpenAI `gpt-6-luna`, the default model; 5 paths per profile, 15 in all, cost about $0.04.
- A path is the level call plus the planning call. Paths are in `out/stability-current/`, not committed.
- Counted as in the October report: **stable** = module–profile pairs where all 5 runs agree ÷ 60;
  **match** = decisions that are expected or accepted ÷ 300.

## Results

| | Result |
|---|---|
| Paths with no usable answer | 0 of 15 |
| Suggested level | the same in every run: P1 intermediate, P2 and P3 beginner |
| Stable decisions | 52 / 60 = 87% |
| Match | 294 / 300 = 98% |
| Difference between profiles | P1–P2 20–30%, P2–P3 25–40%, P1–P3 45–65% of modules |

## What went wrong

- **P3, LLM Fundamentals and Agent Workflows: skipped in 5 of 5 runs**, because "the speech-focused curriculum is a
  closer fit". We expected study: language models matter for translation.
- **P1, Data Foundations: "prove" in 1 of 5 runs**, because of P1's SQL work, though P1 has never used NumPy or
  Pandas. On the October version Gemini made this error in every run.

The changing decisions are mostly about electives (study or skip, both accepted) and about whether P1 proves or
skips modules P1 already knows.

## Compared with October

| | October 6 version, `gemini-3.5-flash-lite` | Current version, `gpt-6-luna` |
|---|---|---|
| Stable decisions | 93% | 87% |
| Match | 96% | 98% |
| Repeated harmful error | P1 Data Manipulation "prove" in 5 of 5 | P3 LLM Fundamentals skipped in 5 of 5 |

P1 and P2 differ less than in October (20–30% against 40–50%): P1 now proves or skips the core modules P1 knows,
and P2 studies them, but both study the same computer vision modules and skip the same specializations.

## Limitations

- 5 runs per profile on one day.
- Three invented profiles, not real learners.
- The expected decisions were drafted with AI assistance (Claude), as the October ones.
