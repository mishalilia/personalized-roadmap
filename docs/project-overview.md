# Project Overview — Personalized Learning Roadmap

The plan as written for the 20 September submission, kept up to date with what changed since. **Status on
5 November 2026:** the Baseline and the Target code are built (§7, §8); learner testing and the business case
are not done yet.

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

## 5. Implementation

A Python core that produces a learning path as a structured artifact, an HTTP API that puts it behind the
curriculum site, and a page on that site that the learner uses.

1. **Content ingestion.** Parse the curriculum repository into modules and their resources, with metadata
   already present in the source: type, title, url, duration, difficulty, rationale, and each module's topics,
   stated outcomes and completion criteria. Each curriculum version is pinned to a commit; paths keep the
   version they were planned for.
2. **Course order.** The path keeps the order the authors gave the course. The source states prerequisites
   only in prose; they go to the model as text. (The first plan was a hand-written prerequisite graph; see
   the changes in [architecture.md](architecture.md).)
3. **Onboarding.** A short set of open-ended questions on coding background and end goal.
4. **Level inference.** An LLM reads the answers and produces a level estimate **with its
   reasoning stated**, which the learner can override. The estimate is presented as a suggestion, never a
   verdict.
5. **Path generation.** For every module the model suggests study, prove (the learner likely knows it and
   shows it) or skip, each with a reason. The learner can change any of them and confirms the path.
6. **Checkpoints (Target).** Questions per module, generated once and reviewed by a person, and a coding
   problem for modules that teach programming, run in the learner's browser. A failed checkpoint locks the
   modules after it and turns "prove" into "study"; a checkpoint passed without a mistake lets the model suggest
   lightening later modules, which the learner accepts or declines.

The path is JSON. The page keeps it in the learner's browser, and the learner can download it.

## 6. Inputs and outputs

| | |
|---|---|
| **Input** | Learner's answers to onboarding questions (free text: background, experience, end goal); optional corrections to the suggested level and to any decision; checkpoint answers and code. |
| **Reference data** | The modules parsed from pinned versions of the public content repository. |
| **Output** | The path: every module in course order, marked study, prove or skip with a reason; the suggested level with the reasoning behind it; the title and URL of every module, and the licence. JSON, shown on the page. |
| **Output (Target)** | Checkpoint results per module; locked modules after a failed checkpoint; suggestions after an effortless pass; the hours of the path against the whole course. |

## 7. Baseline and how we build it

| DoD (Baseline) | Plan |
|---|---|
| Onboarding questions covering coding background and end goal | 6-8 open questions, kept in a config file in this repository. |
| Infers a level from the answers and explains the reasoning, so the learner can correct it | One model call returns the level, the evidence for it and how sure it is. The learner sees that evidence and can change the level; the planner then uses their version. |
| Generates an ordered path through the real content, with skipped material explicitly marked and justified | Code keeps the course order and checks that every module has a decision. The model decides study, prove or skip, with a reason for each. |
| Produces visibly different paths for three clearly different learner profiles | Three example profiles are kept in the repository and their paths are compared automatically, so the difference is measured rather than claimed. They are invented, not built from real people's answers. |
| Licence attribution correctly implemented | Every module in a path carries its title and URL, the path carries the licence, and the page shows the attribution under every path. |

All five are built; their tests are in [test-plan.md](test-plan.md). Order, the check that every module got a
decision, and attribution are ordinary code; the model is used only where a judgement is needed, and
prerequisites, which the source states only in prose, reach it as text. That makes most of the Baseline
testable, and leaves a working path when no model is available.

## 8. Target and Stretch

**Target (what we aim for after Baseline is complete):** checkpoint questions and coding problems generated
from section content; progress blocked past a failed checkpoint; the remaining path adjusted on failure or on
effortless success; a usable web interface; testing with at least five real learners outside the team, written
up; a business case quantifying what a completion-rate improvement is worth to a learning platform.

**Stretch (only if all Baseline and Target work is done):** automatic checking of generated coding problems
against tests; mid-path goal change with replanning; peer recommendation at a similar stage; drop-off analysis
fed back to the content owner.

**Status:** the Target code is built — checkpoints with coding problems, the lock, both adjustments and the
page on the curriculum site. Learner testing and the business case are not done. Three Stretch items came
with it: coding problems are checked against their tests in the learner's browser, goal change replans the
rest of a path, and a report shows where learners who opt in stop. Peer recommendation is not started.

**Out of scope:** user accounts and authentication; any paid API on the Baseline path; model fine-tuning;
curricula other than the one named below.

## 9. Data sources and access

| | |
|---|---|
| **Dataset** | HumbleBeeAI Open Curriculum content |
| **Source** | https://roadmap.humblebee.ai — repository https://github.com/humblebeeai/int.academy-curriculum |
| **Licence** | CC BY-NC-SA 4.0 (attribution, share-alike, non-commercial), confirmed in the repository's LICENSE file |
| **Access** | Obtained. Public repository, cloned directly; no scraping and no credentials required. |
| **Shape** | Measured in September on commit 5c21272: 25 MDX documents (22 of them curriculum content, 3 meta pages), about 165 KB of text, 151 sections, 116 structured resource entries with type, title, url, duration, difficulty and rationale. Resource types: course 36, tutorial 22, video 22, paper 9, article 6, docs 5, practice 4, book 4, guide 4, blog 3, talk 1. Declared difficulty: beginner 44, intermediate 53, advanced 19. The current curriculum (commit 9fc5573) has 20 modules and 175 resources, 96 of them without a declared difficulty. |
| **Version** | Each version pinned to a commit in `config/curriculum.yaml`: [`9fc5573`](https://github.com/humblebeeai/int.academy-curriculum/commit/9fc5573ddbd7be5d5da997a26c49afeafbfe6210) (22 October 2026, the current curriculum) for new paths, and [`5c21272`](https://github.com/humblebeeai/int.academy-curriculum/commit/5c212720af50ffd0a1592ea6c0f812c3af733ed3) (7 September 2026, the site's October 6 version) for older paths. The source repository maintains `curriculum-versions.json` and `versioned_docs`, so the versions we build against are recorded and reproducible. |
| **Personal data** | None in the source. Learner data collected during testing is kept minimal, is not published, and does not enter this repository. |
| **Preprocessing** | MDX frontmatter and component attributes parsed into modules, resources, prerequisites and checklists; no content redistributed beyond what attribution requires. |

A generated path links to and orders the material without reproducing it, so we read it as a collection
rather than an adaptation. We license our own documentation and curriculum-derived artifacts CC BY-NC-SA 4.0
anyway, which is safe under either reading.
Tracked as Q-001 in [questions.md](questions.md).

## 10. Tools, models, free options and hardware

| | |
|---|---|
| **Language / core** | Python 3.11 |
| **Starter template** | [module-python-template](https://github.com/humblebeeai/module-python-template) — the core is a library. An HTTP API (FastAPI) was added when the curriculum site needed one, and a SQLite file for the progress learners choose to share. |
| **LLM** | Gemini API free tier (`gemini-3.5-flash-lite`, then `gemini-3.8-flash`), with Groq (`openai/gpt-oss-120b`) as the second provider. Chosen on cost, latency and stability across repeated runs (Q-003). |
| **Fallback when the model is unavailable or rate-limited** | Free-tier quotas are counted per model, so the first fallback is the provider's next model. If no model answers, the path is the whole course in its own order, and the learner is told that personalization is unavailable. |
| **Interface** | A page on the curriculum site (React, Docusaurus), calling the API. The Baseline prototype used Streamlit, which the page replaced. The path JSON is the contract between them. |
| **Hosting** | The team's VPS, with Docker Compose and Caddy for HTTPS ([deploy/](../deploy/README.md)). |
| **Hardware** | Team laptops and one small VPS. No GPU required; no model training. Coding problems run in the learner's browser. |

## 11. Technical difficulties to investigate first

1. **What checkpoint questions can be generated from.** The source is a curated set of links, not lesson
   prose: 126 sections carry 12,786 words in total, a median of 75 each. Working answer: generate questions
   about the topic a section defines, using its stated outcomes, structure, declared difficulty and the
   authors' per-resource notes. First test: 10 questions for one module, rated by someone who knows the topic
   (Q-004). Status: the generator is built; the rating has not been done.
2. **Whether the corpus supports visibly different paths.** 18 modules may be too coarse a unit; resources
   are finer. Status: with `gemini-3.5-flash-lite`, the paths of the three profiles differ by 40–85% at module
   level (21 October), so modules are enough.
3. **Prerequisites exist only in prose.** We use the course order and give the prose to the model instead of
   writing a graph by hand.
4. **Self-reported level is unreliable in both directions.** Testing is stronger than asking, but a long
   test loses the learner before they start. To be settled with real learners.
5. **How strictly a failed checkpoint blocks progress.** Too strict and learners quit; too loose and
   checkpoints mean nothing. Status: a failed checkpoint locks every module after it until a retake passes;
   whether that is too strict is to be tested with real learners.
6. **Output stability.** The same profile run repeatedly must not produce arbitrarily different paths; the
   degree of variation is measured and reported. Status: measured on 21 October (93% of decisions stable with
   the chosen model).

## 12. References and sources

- Project Pool, tab **S2 — Personalized Learning Roadmap**, Convergence of Business Administration & Engineering Capstone Design,
  Inha University IBT / ISE, Fall 2026, in partnership with HumbleBeeAI.
- Inha Capstone Project Documentation Guide.
- HumbleBeeAI Open Curriculum — https://roadmap.humblebee.ai (CC BY-NC-SA 4.0),
  repository https://github.com/humblebeeai/int.academy-curriculum
- Starter template — https://github.com/humblebeeai/module-python-template
