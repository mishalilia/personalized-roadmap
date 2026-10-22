# Model stability and agreement, 21 October 2026

Test plan §5: how much each model's decisions change between runs, and how often they match the
[expected decisions](expected-decisions.md). Three example profiles, curriculum 5c21272, prompts as merged in
PR #1.

## How it was run

- Each model on its own, without falling back to another one.
- A path is the level call plus the planning call, at the level the model suggested.
- `gemini-3.5-flash-lite` and `openai/gpt-oss-120b`: 5 runs per profile. `gemini-3.8-flash` (20 requests a
  day) and `openai/gpt-oss-20b`: 3.
- The paths are in `out/stability/`, not committed because they contain curriculum text.

## Results

| Model | Paths | No usable answer | Median time per path | Stable decisions | Match | Harmful decisions |
|---|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 15 | 0 | 5 s | 93% | 96% | 5, all the same one |
| `gemini-3.8-flash` | 9 | 0 | 35 s | 98% | 93% | 3, the same one |
| `openai/gpt-oss-120b` | 15 | 0 | 7 s | 76% | 93% | 4, in different modules |
| `openai/gpt-oss-20b` | 9 | 5 | 4 s | — | — | — |

**Stable decisions:** of the 18 modules × 3 profiles, the share where every run gave the same decision.
**Match:** the share of decisions that are expected or accepted. **Harmful:** a module the learner needs is
skipped, or "prove" is given without evidence.

The suggested level never changed: P1 intermediate, P2 and P3 beginner, with every model. P1 and P2 paths
differ by 40–50% with `gemini-3.5-flash-lite`; with `gpt-oss-120b`, one pair came out identical.

## What went wrong

- **Gemini, P1 Data Manipulation: "prove" in every run,** because a backend engineer "can validate NumPy and
  Pandas through the checklist". P1 has never used them.
- **`gpt-oss-120b`, P2 Computer Vision Capstone: skipped in 1 of 5 runs** because P2 lacks the prerequisites,
  which is a reason to study it later, not to skip it.
- **`gpt-oss-120b`, P3 Generative AI Capstone: skipped in 2 of 5 runs,** although it is the module closest to
  P3's goal.
- **`gpt-oss-120b`, P2 Infra Basics: skipped in 1 of 5 runs,** although the computer vision capstone needs
  Docker.
- **`gpt-oss-20b`** cut its answer short in 5 of 9 paths. Such answers are rejected, so these paths fell back
  to the whole course.

Counted as errors above, though the model's reason holds up: `gpt-oss-120b` had P3 study AI Software
Engineering (5 of 5 runs, to deploy speech services) and P1 study Terminal & Algorithmic Basics (3 of 5, for
its algorithm problems).

## Decision (Q-003)

- **`gemini-3.5-flash-lite` first:** stable, the best match, fast, and about 250 paths a day. Its one repeated
  error should be easier to fix in the prompt than scattered ones.
- **`gemini-3.8-flash`** next: the most stable, but 35 s a path and 20 requests a day.
- **`gpt-oss-120b`** as the second provider: it always answered, but changes a quarter of its decisions
  between runs.
- **`gpt-oss-20b`** removed.

## Limitations

- 3–5 runs per profile on one day.
- Three invented profiles, not real learners.
