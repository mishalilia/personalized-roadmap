# Project Overview — Personalized Learning Roadmap

The plan written for the 20 September submission, updated with what was built. **Status on 20 November
2026:** Baseline, Target and three of the four Stretch items are built and tested (§7, §8).

## 1. Target users and the problem

Free technical learning material is abundant; completion is not. The reference case is
[roadmap.humblebee.ai](https://roadmap.humblebee.ai), an open AI engineering curriculum that shows the same
path to every visitor. A fixed path fails in two ways:

- **Learners who already know the basics quit out of boredom.** The first modules repeat what they know, and
  there is no way to say so.
- **Learners without the background quit out of overwhelm.** They reach material that assumes knowledge
  nobody checked.

And nothing checks that a module was understood: learners move on because they have read it.

**Users:** self-directed learners of a technical course — students and career switchers, including our
classmates.

## 2. The buyer

Today DotPath runs on the HumbleBeeAI course. **The buyer in our business plan is the owner of a paid
technical course without an ML team:** small online schools of programming, data, AI and
security, and mid-sized programming course platforms. A learner who stops costs them a refund, a cancelled
subscription or a lost next sale. They see where learners stop but cannot change a fixed course for each
learner. They pay $1 per active learner a month; the learner uses DotPath for free.

Considered and set aside: large platforms (Coursera, Udemy, Educative and others have built personal paths
themselves) and company training (Coursera, Udemy Business, Degreed and Docebo already sell it to companies).
The business plan gives the market size, the price and the forecast.

## 3. How learners solve this today

- They follow the fixed path and skim by feel, with no record of what they skipped.
- They leave the course and assemble their own from scattered links, losing its order.
- They ask a mentor what to skip, which few have.
- They ask a chatbot for a study plan, which is not tied to the course and does not track progress.

None of these checks understanding.

## 4. Why AI (and not a decision tree)

1. **Level from what the learner says and shows.** Weighing chosen options against the learner's own details
   and a code question, and saying why, needs a model; a branching questionnaire gives a few preset paths.
2. **Planning for any goal.** Goals cannot be listed in advance.
3. **Checkpoints from content.** Writing questions by hand for every module does not scale, which is why most
   free material has none.

## 5. Implementation

A Python core that produces the path as JSON, an HTTP API that puts it behind the curriculum site, and a page on
that site.

1. **Content ingestion.** The curriculum repository is parsed into modules with their resources, topics, stated
   outcomes, completion criteria and workload. Each version is pinned to a commit; a path keeps its version.
2. **Course order.** The path keeps the authors' order. Prerequisites exist only as prose and go to the model as
   text.
3. **Onboarding.** Seven questions: five answered by choosing, with optional details; one code question; the
   goal in the learner's words.
4. **Level.** The model suggests a level with its evidence; the learner can change it.
5. **Path.** For every module the model suggests study, prove or skip with a reason; inside a module the learner
   can study, skim or skip each topic. The learner can change anything and confirms the path.
6. **Checkpoints.** Questions per module, generated once and reviewed, with an open question marked by the
   model and a coding problem for programming modules, run in the browser. A failed checkpoint locks later
   modules and turns *prove* into *study*; after a failure or an effortless pass the model suggests heavier or
   lighter later modules, which the learner accepts or declines.

The path is kept on our server under the learner's account.

## 6. Inputs and outputs

| | |
|---|---|
| **Input** | Onboarding answers; changes to the level, decisions and topics; checkpoint answers and code; capstone projects. |
| **Reference data** | The modules parsed from pinned versions of the public curriculum repository. |
| **Output** | The path: every module in course order with a decision and a reason, the level with its evidence, each module's title and URL, the licence. Then checkpoint results, locks, suggestions, project reviews and the hours of the path against the whole course. |

## 7. Baseline

| DoD (Baseline) | How it is built |
|---|---|
| Onboarding questions covering coding background and end goal | 7 questions in `config/onboarding.yaml`: 5 to choose from with optional details, 1 code question, the goal as free text. |
| Infers a level and explains the reasoning, so the learner can correct it | One model call returns the level, its evidence and how sure it is; the learner can change the level. |
| Ordered path through the real content, skipped material marked and justified | Code keeps the course order and checks that every module has a decision; the model gives study, prove or skip with a reason. |
| Visibly different paths for three learner profiles | Three invented profiles in `config/profiles.yaml`; `python -m roadmap compare` measures how much their paths differ. |
| Licence attribution | Every module carries its title and URL, the path carries the licence, the page shows the attribution. |

All five are built and tested ([test-plan.md](test-plan.md)). Order, the every-module check and attribution are
code, so most of the Baseline is testable and a path exists without a model.

## 8. Target and Stretch

| Tier | Item | Status |
|---|---|---|
| Target | Checkpoint questions and coding problems generated from module content | Built; 13 of the 20 modules have one, generated with GPT-6 Luna (the capstones and electives have none on purpose) |
| Target | Progress blocked past a failed checkpoint | Built; the lock is kept on the server |
| Target | Path adjusted on failure or effortless success | Built |
| Target | A usable web interface | Built: a panel beside the course pages, on desktop and phone |
| Target | Testing with five learners outside the team | Done, November 2026 ([learner-testing.md](learner-testing.md)) |
| Target | Business case | Done, in the business plan |
| Stretch | Generated coding problems checked against tests | Built: tests run in the browser, and each problem's wrong solutions must fail them |
| Stretch | Goal change mid-path with replanning | Built |
| Stretch | Drop-off analysis for the content owner | Built: a report of where learners who share their progress stop |
| Stretch | Peer recommendation at a similar stage | Not built |

**Beyond the plan,** after the midterm feedback: accounts (Google, or email and password) with the path on the
server; study, skim or skip per topic; open checkpoint questions; capstone projects reviewed by an AI reviewer
against each rubric, with its evidence checked in code; an assistant in the panel; a read-only link to a
learner's progress, after roadmap.sh.

**Out of scope:** model fine-tuning; running learners' projects; curricula other than the one named below.

## 9. Data sources and access

| | |
|---|---|
| **Dataset** | HumbleBeeAI Open Curriculum |
| **Source** | https://roadmap.humblebee.ai — https://github.com/humblebeeai/int.academy-curriculum |
| **Licence** | CC BY-NC-SA 4.0 (attribution, share-alike, non-commercial), per the repository's LICENSE file |
| **Access** | Public repository, cloned directly; no scraping, no credentials. |
| **Shape** | Current version (commit 9fc5573): 20 modules, 175 resources, 96 of them without a stated difficulty. October 6 version (commit 5c21272): 18 modules, 116 resources with type, title, URL, duration, difficulty and rationale. |
| **Versions** | Pinned in `config/curriculum.yaml`: [`9fc5573`](https://github.com/humblebeeai/int.academy-curriculum/commit/9fc5573ddbd7be5d5da997a26c49afeafbfe6210) (22 October 2026) for new paths, [`5c21272`](https://github.com/humblebeeai/int.academy-curriculum/commit/5c212720af50ffd0a1592ea6c0f812c3af733ed3) (7 September 2026) for older ones. |
| **Personal data** | None in the source. Learner data is minimal and never enters this repository. |

HumbleBeeAI, the project's partner, gave us its course to use, and DotPath runs only on its site (Q-001). Our
documentation and curriculum-derived material carry CC BY-NC-SA 4.0, with attribution.

## 10. Tools and hardware

| | |
|---|---|
| **Core** | Python 3.11, from [module-python-template](https://github.com/humblebeeai/module-python-template); FastAPI for the HTTP API; PostgreSQL for accounts, paths, projects and shared progress. |
| **Model** | OpenAI `gpt-6-luna` by default, about $0.002 a path; Gemini and Groq free tiers as alternatives (Q-003). |
| **Fallback** | The provider's next model; if none answers, the whole course in its order, and the learner is told. |
| **Interface** | A React page in the curriculum site (Docusaurus). The Baseline prototype used Streamlit, which it replaced. |
| **Hosting** | One server with Docker Compose and Caddy for HTTPS ([deploy/](../deploy/README.md)). |
| **Hardware** | Team laptops and one small server. No GPU, no training. Coding problems run in the learner's browser. |

## 11. Hard parts and how they were settled

1. **What checkpoints can be generated from.** Modules hold little original text (a median of 75 words a
   section). Settled: questions about each topic the module defines, from its outcomes, the authors' resource
   notes and its completion criteria; the model supplies the subject knowledge (Q-004).
2. **Whether modules are fine enough for different paths.** Yes: the three profiles' paths differ by 40–85% of
   modules on the October version and 20–65% on the current one. Topics inside modules add finer choices.
3. **Prerequisites only in prose.** The path keeps the course order; the prose goes to the model.
4. **Self-reported level is unreliable.** Onboarding asks what the learner has done, plus a code question, and
   the level comes with its evidence so the learner can correct it.
5. **How strictly a failed checkpoint blocks.** A failure locks later modules until a retake passes; kept after
   the learner sessions.
6. **Output stability.** Measured: 93% of decisions stable on the October 6 version
   ([report](test-results/2026-10-21-model-stability.md)), 87% on the current one with GPT-6 Luna
   ([report](test-results/2026-11-20-current-curriculum.md)).

## 12. References

- Project Pool, tab **S2 — Personalized Learning Roadmap**, Convergence of Business Administration & Engineering
  Capstone Design, Inha University IBT / ISE, Fall 2026, in partnership with HumbleBeeAI.
- Inha Capstone Project Documentation Guide.
- HumbleBeeAI Open Curriculum — https://roadmap.humblebee.ai (CC BY-NC-SA 4.0)
- Starter template — https://github.com/humblebeeai/module-python-template
