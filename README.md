# Personalized Learning Roadmap

> Everyone gets the same learning path, most people abandon it, and nobody finds out whether anything was learned.

An AI system that builds a **personalized path through real technical learning content**
([roadmap.humblebee.ai](https://roadmap.humblebee.ai)): it infers the learner's level from open-ended
answers and explains that inference, orders the material toward the learner's goal, marks and justifies what
was skipped, and — from the Target tier onward — verifies understanding with checkpoints before letting the
learner move on.

Capstone project **S2** — Convergence of Business Administration & Engineering Capstone Design,
Inha University (IBT / ISE), Fall 2026, in partnership with HumbleBeeAI.

Planning documents for the 20 September submission; no code yet.

## Documents

| Document | Contents |
|---|---|
| [docs/project-overview.md](docs/project-overview.md) | Problem, buyer, why AI, implementation plan, Baseline/Target/Stretch, data, tools, hard parts |
| [docs/team-rnr.md](docs/team-rnr.md) | Role owners, what each member owns, reviewers |
| [docs/ground-rules.md](docs/ground-rules.md) | How the team meets, reviews code and handles data |
| [docs/questions.md](docs/questions.md) | Open questions, assumptions and decisions we would like feedback on |
| [docs/test-plan.md](docs/test-plan.md) | Test scenarios mapped to Baseline/Target DoD items, current stage and status of each |

## The problem

Free technical learning material is abundant; completion is not. A fixed path fails in two directions at
once: experienced learners quit out of boredom because the early material repeats what they know and there
is no way to say so, and beginners quit out of overwhelm because they reach material assuming knowledge
nobody checked they had. Nothing verifies that a section was understood, so learners advance on the feeling
of having read something.

**Buyer:** a learning platform or content publisher with a completion problem. They can see where learners
drop out and cannot fix it, because the content is fixed and the audience is not. Value is measured directly
in completion and retention.

## How it works

1. **Onboarding** — open-ended questions about coding background and end goal.
2. **Level inference** — a model infers the level and states the reasoning; the learner can correct it, and
   the correction is what the planner uses. The inference is a suggestion, never a verdict.
3. **Path generation** — an ordered route through the real content toward the goal, with every skipped item
   explicitly marked and justified.
4. **Checkpoints** *(Target)* — questions generated from the content; progress is gated on them.
5. **Adaptation** *(Target)* — a failed checkpoint replans the remainder of the path.

## Architecture and starter template

Starter template: [module-python-template](https://github.com/humblebeeai/module-python-template).

Chosen because the planner, the prerequisite graph and the attribution logic are library code. The web
interface is a Target item; the HTTP layer it needs is added then, not before, and no database is planned
until there is state to keep between sessions.

C4 Level 1 and Level 2 diagrams are due 23 September and will be linked here.

## Content source, licence and attribution

| | |
|---|---|
| Dataset | HumbleBeeAI Open Curriculum |
| Source | https://roadmap.humblebee.ai · repository https://github.com/humblebeeai/int.academy-curriculum |
| Licence | **CC BY-NC-SA 4.0** — attribution required, share-alike applies to derivatives, non-commercial |
| Version | TBD — to be pinned to a specific commit or curriculum version tag |
| Personal data | None in the source content |
| Preprocessing | MDX parsed into a node graph; prerequisite edges authored by this team |

Learning content is © HumbleBeeAI, used under CC BY-NC-SA 4.0. Every resource emitted in a generated path
carries its source title, URL and licence.

### How we comply

A generated path links to and orders the curriculum without reproducing it, so we read it as a collection
rather than an adaptation. We license it the same way anyway, which is safe under either reading. Every
resource in an output carries its source title, URL and licence, and we do not sell the tool, charge for
access, or ship the content into a commercial product.

**This repository is licensed in two parts:** source code under **MIT** (matching the starter template), and
documentation plus anything derived from the curriculum — the parsed graph, generated paths — under
**CC BY-NC-SA 4.0**. Share-alike follows the content into its adaptations, but not into independent software
that reads it. The curriculum is not copied into this repository; it is fetched from its own repository at a
pinned version.

The source states its licence inconsistently: `LICENSE`, its README and the licensing section of
`CONTRIBUTING.md` say CC BY-NC-SA 4.0, while one line of `CONTRIBUTING.md` and both `llms.txt` files say
CC BY-SA 4.0, without the non-commercial term. We follow the stricter reading, which is also what the
project brief states. Whether a generated path counts as an adaptation is Q-001 in
[docs/questions.md](docs/questions.md), pending confirmation by the professors; attribution applies either way.

The 116 external resources the curriculum links to stay under their own licences — we link to them and keep
their metadata, and do not copy their content.

## Learner data

Any data collected while testing with real learners is kept to the minimum needed, participants are told
what is collected, and **no learner data is published in this repository**.

## Setup

TBD — no code yet. Copy `.env.example` to `.env` for the API key; `requirements.txt` is a placeholder until
the core module exists.

## How to obtain the data

The curriculum is a public repository and needs no credentials:

```bash
git clone https://github.com/humblebeeai/int.academy-curriculum
git checkout <pinned commit — TBD>
```

The curriculum stays outside this repository; usage conditions are in the licence section above.

## Fallback when the model is unavailable or rate-limited

Free-tier quotas are counted per model, so the first fallback is a smaller model of the same family. The
provider and the models themselves are still TBD (Q-003). If no model is reachable at all, the rule-based
planner runs — ordering from the prerequisite graph and the difficulty declared in the content — and the
learner is told that personalization is unavailable.

## Example output

A generated path: the included nodes in order with a reason for each, the skipped ones with justification,
the inferred level and the reasoning behind it, and attribution for every resource. A sample run will be
committed here once the core works.

## Test results, known errors and limitations

No runs yet. What we plan to check, and what will count as success:

- **Different paths for different profiles** — the three example profiles are compared against each other;
  success is a difference large enough to be visible without explanation, measured as the share of nodes
  they do not share.
- **Level inference** — compared against what learners say about themselves; success is agreement in most
  cases, with every disagreement explainable from the answers given.
- **Skipped material** — a sample of skip justifications is checked by hand; success is that they hold up
  against the learner's stated background.
- **Stability** — the same profile is run several times; success is that the paths stay within a set
  tolerance of each other.
- **Fallback** — the planner produces a valid path with no model available.

## Team

| Name | Role |
|---|---|
| Umaraliev Makhmudjon | PM |
| Abdulkhaev Akbarjon | Problem & Business |
| Jalilov Jakhongir Zukhriddin ugli | Data & Research |
| Li Mikhail | AI / Engineering |
| Chagai Vladimir | AI / Engineering |
| Imetov Daniiar | Demo & Presentation |

Student IDs, what each person is responsible for and who reviews their work are in the role sheet:
[docs/team-rnr.md](docs/team-rnr.md).

## Use of AI tools

A substantial part of the documentation here is written with AI
assistance (Claude).

For this submission we checked the Baseline, Target and Stretch items against the S2 project brief, the
licence in the source repository's own files, and the content statistics in the overview, which come from
parsing the source repository rather than from a model.

Drafts were edited rather than taken as they came.
