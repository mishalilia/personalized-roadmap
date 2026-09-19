# Project Overview — Personalized Learning Roadmap

## 1. Target users and the problem

High-quality free technical learning material is abundant; completion is not. The reference case is
[roadmap.humblebee.ai](https://roadmap.humblebee.ai), an open AI engineering curriculum that presents an
identical path to every visitor.

Two failure modes follow from a fixed path:

- **Learners with existing knowledge quit out of boredom.** The first modules repeat what they know and
  there is no mechanism to declare it.
- **Learners without the background quit out of overwhelm.** They reach material that assumes knowledge
  nobody checked they had.

A third problem cuts across both: nothing verifies that a section was understood. Learners advance on the
feeling of having read something and discover much later that it did not hold.

**Direct users:** self-directed learners working through an open technical curriculum — in our case
university students and career switchers, including ourselves and our classmates.

## 2. The buyer

**A learning platform / content publisher with a completion problem.** The buyer owns the content product,
can see where learners drop out, and cannot fix it because the content is fixed while the audience is not.
Value is measured directly in completion and retention, which makes the business case checkable rather
than rhetorical.

The brief requires building for one customer type, and names the content we build on: the public
roadmap.humblebee.ai curriculum. A learning platform is the buyer who owns content of exactly that kind —
open, structured, and judged by completion — so the buyer and the corpus match.

The other two were set aside over content, not users. Internal corporate upskilling would mean
personalizing a company's own training material and reading its staff data, neither of which a class project
can obtain. An education provider's material is its own syllabus, which we have neither in a machine-readable
form nor with a licence to process; and completion there is governed by enrolment and grading rather than by
drop-off the buyer can act on. Our classmates remain our test users either way.

## 3. How users solve this today

- They follow the fixed path and skim or skip sections by feel, with no record of what was skipped or why.
- They abandon the curriculum and assemble their own path from scattered video, blog and course links,
  losing the sequencing that made the curriculum useful.
- They ask a mentor or a senior colleague what to skip, which does not scale and is unavailable to most.
- They ask a general chatbot for a study plan and receive a plausible list that is not tied to any real
  curriculum, has no prerequisite structure, and cannot track progress.

None of these verify understanding, and none leave a record the learner or the platform can act on.

## 4. Why AI (and not a decision tree)

Three parts of this cannot be built as fixed branching logic:

1. **Level inference from open-ended answers.** A fixed questionnaire yields a handful of preset paths.
   Interpreting what a person actually knows from how they describe their experience requires a model.
2. **Planning against an arbitrary goal.** The set of learner goals is not enumerable in advance; routes
   for "multilingual speech systems" and "computer vision research" cannot both be pre-authored.
3. **Generating checkpoints from content.** Hand-writing questions for every section does not scale, which
   is exactly why most free material has none.

## 5. Proposed implementation

A Python core that produces a learning path as a structured artifact, plus a thin interface that consumes it.

1. **Content ingestion.** Parse the curriculum repository into a graph of nodes (module, section, resource)
   with metadata already present in the source: type, title, url, duration, difficulty, rationale.
2. **Prerequisite graph.** Hand-authored dependency edges between modules, reviewed by the team. The source
   states prerequisites only in prose, in a "Soft-Landing Prerequisites" table covering command line, problem
   solving, linear algebra, statistics and NumPy; that table also names public certificate tests and exams
   for those sections, which we can use to test a learner's level instead of asking for it.
3. **Onboarding.** A short set of open-ended questions on coding background and end goal.
4. **Level inference.** An LLM maps the answers onto the graph and produces a level estimate **with its
   reasoning stated**, which the learner can override. The estimate is presented as a suggestion, never a
   verdict.
5. **Path generation.** An ordered route through the graph toward the stated goal, with every skipped node
   explicitly marked and justified against the inferred level.
6. **Checkpoints (Target).** Questions and coding problems generated per section, with progress gated on
   them and the remainder of the path replanned on failure.

The path is emitted as JSON, which any interface reads.

## 6. Inputs and outputs

| | |
|---|---|
| **Input** | Learner's answers to onboarding questions (free text: background, experience, end goal); optional explicit corrections to the inferred level; later, checkpoint answers. |
| **Reference data** | The curriculum graph parsed from a pinned version of the public content repository. |
| **Output** | An ordered learning path: included nodes in order, each with a reason; skipped nodes with justification; the inferred level with the reasoning behind it; attribution for every referenced resource. Emitted as JSON, rendered for the learner. |
| **Output (Target)** | Checkpoint questions per section; pass/fail state; a revised remaining path after a failed checkpoint. |

## 7. Baseline and how we build it

| DoD (Baseline) | Plan |
|---|---|
| Onboarding questions covering coding background and end goal | 6-8 open questions, kept in a config file in this repository. |
| Infers a level from the answers and explains the reasoning, so the learner can correct it | One model call returns the level, the evidence for it and how sure it is. The learner sees that evidence and can change the level; the planner then uses their version. |
| Generates an ordered path through the real content, with skipped material explicitly marked and justified | Code walks the prerequisite graph and produces the order. The model only judges whether a module is relevant to the goal, and why a skipped one is safe to skip. |
| Produces visibly different paths for three clearly different learner profiles | Three example profiles are kept in the repository and their paths are compared automatically, so the difference is measured rather than claimed. They are invented, not built from real people's answers. |
| Licence attribution correctly implemented | Each item in the output carries its source title, URL and licence. |

Order, prerequisites and attribution are ordinary code; the model is used only where a judgement is needed.
That makes most of the Baseline testable, and leaves a working path when no model is available.

## 8. Target and Stretch

**Target (what we aim for after Baseline is complete):** checkpoint questions and coding problems generated
from section content; progress blocked past a failed checkpoint; the remaining path adjusted on failure or on
effortless success; a usable web interface; testing with at least five real learners outside the team, written
up; a business case quantifying what a completion-rate improvement is worth to a learning platform.

**Stretch (only if all Baseline and Target work is done):** automatic checking of generated coding problems
against tests; mid-path goal change with replanning; peer recommendation at a similar stage; drop-off analysis
fed back to the content owner.

**Out of scope:** user accounts and authentication; any paid API on the Baseline path; model fine-tuning;
curricula other than the one named below.

## 9. Data sources and access

| | |
|---|---|
| **Dataset** | HumbleBeeAI Open Curriculum content |
| **Source** | https://roadmap.humblebee.ai — repository https://github.com/humblebeeai/int.academy-curriculum |
| **Licence** | CC BY-NC-SA 4.0 (attribution, share-alike, non-commercial), confirmed in the repository's LICENSE file |
| **Access** | Obtained. Public repository, cloned directly; no scraping and no credentials required. |
| **Shape** | 25 MDX documents (22 of them curriculum content, 3 meta pages), about 165 KB of text, 151 sections, 116 structured resource entries with type, title, url, duration, difficulty and rationale. Resource types: course 36, tutorial 22, video 22, paper 9, article 6, docs 5, practice 4, book 4, guide 4, blog 3, talk 1. Declared difficulty: beginner 44, intermediate 53, advanced 19. |
| **Version** | To be pinned to a specific tag or commit. The source repository maintains `curriculum-versions.json` and `versioned_docs`, so the version we build against is recorded and reproducible. |
| **Personal data** | None in the source. Learner data collected during testing is kept minimal, is not published, and does not enter this repository. |
| **Preprocessing** | MDX frontmatter and component attributes parsed into a node graph; prerequisite edges added by us; no content redistributed beyond what attribution requires. |

**Licence consequences to resolve before the final submission:** the path we generate is a derivative of
CC BY-NC-SA material, so share-alike affects the licence of our own output and repository, and the
non-commercial condition constrains how the business case may be phrased. Tracked as Q-001 in
[questions.md](questions.md). Licence compliance is graded on this project.

## 10. Tools, models, free options and hardware

| | |
|---|---|
| **Language / core** | Python 3.11 |
| **Starter template** | [module-python-template](https://github.com/humblebeeai/module-python-template) — the core is a library, not a service. No HTTP API or database is introduced until something outside the core needs one. |
| **LLM** | TBD between a free-tier hosted model (Google AI student offer, 12 months) and an open model run locally or on Colab. Decision criteria: cost of one path generation, latency, and output stability across repeated runs. Tracked as Q-003. |
| **Fallback when the model is unavailable or rate-limited** | Free-tier quotas are counted per model, so the first fallback is a smaller model of the same family; the provider and the models themselves are still TBD (Q-003). If no model is reachable at all, the rule-based planner runs on the prerequisite graph and the difficulty declared in the content, and the learner is told that personalization is unavailable. |
| **Interface** | The path JSON is the contract. A web interface is a Target item and is built as a client of that JSON. |
| **Hosting** | TBD (Hugging Face Spaces or Vercel), free tier only. |
| **Hardware** | None beyond team laptops. No GPU required; no model training. |

## 11. Technical difficulties to investigate first

1. **What checkpoint questions can be generated from.** The source is a curated set of links, not lesson
   prose: 126 sections carry 12,786 words in total, a median of 75 each. Working answer: generate questions
   about the topic a section defines, using its stated outcomes, structure, declared difficulty and the
   authors' per-resource notes. First test: 10 questions for one module, rated by someone who knows the topic
   (Q-004).
2. **Whether the corpus supports visibly different paths.** 25 modules may be too coarse a unit; 116
   resources is finer. First test: hand-build paths for the three example profiles before writing the planner.
3. **The prerequisite graph does not exist in machine-readable form** and must be authored and reviewed by us
   from the prose prerequisites table and the structure of the curriculum.
4. **Self-reported level is unreliable in both directions.** Testing is stronger than asking, but a long
   test loses the learner before they start. To be settled with real learners.
5. **How strictly a failed checkpoint blocks progress.** Too strict and learners quit; too loose and
   checkpoints mean nothing. To be tested.
6. **Output stability.** The same profile run repeatedly must not produce arbitrarily different paths; the
   degree of variation is measured and reported.

## 12. References and sources

- Project Pool, tab **S2 — Personalized Learning Roadmap**, Convergence of Business Administration & Engineering Capstone Design,
  Inha University IBT / ISE, Fall 2026, in partnership with HumbleBeeAI.
- Inha Capstone Project Documentation Guide.
- HumbleBeeAI Open Curriculum — https://roadmap.humblebee.ai (CC BY-NC-SA 4.0),
  repository https://github.com/humblebeeai/int.academy-curriculum
- Starter template — https://github.com/humblebeeai/module-python-template
