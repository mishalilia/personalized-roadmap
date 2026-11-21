# Data Sources

**Status:** matches the code on 20 November 2026.

Default rule from the course: public or safe sample data only. No personal data, no real company data.

---

## 1. Curriculum content (main data source)

| | |
|---|---|
| **Name** | HumbleBeeAI Open Curriculum |
| **Where** | Site: <https://roadmap.humblebee.ai>. Repository: <https://github.com/humblebeeai/int.academy-curriculum> |
| **Licence** | CC BY-NC-SA 4.0: attribution required, share-alike applies to adaptations, non-commercial only. The source files disagree (some say CC BY-SA). We follow the stricter reading. See Q-001 in `questions.md`. |
| **How we get it** | `git clone` of the public repository (`python -m roadmap fetch`). No scraping, no credentials. |
| **Versions** | Listed in `config/curriculum.yaml`, each pinned to a commit. The current curriculum, commit [`9fc5573`](https://github.com/humblebeeai/int.academy-curriculum/commit/9fc5573ddbd7be5d5da997a26c49afeafbfe6210) (22 October 2026), for new paths. Commit [`5c21272`](https://github.com/humblebeeai/int.academy-curriculum/commit/5c212720af50ffd0a1592ea6c0f812c3af733ed3) (7 September 2026), the site's "October 6, 2026" version, for paths planned for it and for the model runs of 21 October. |
| **Shape** | MDX files with structured metadata. The current version: 20 modules and 175 linked resources; 96 of the resources state no difficulty, 79 state a duration, and 4 modules state their workload. The October 6 version: 18 modules and 116 resources, all with type, difficulty and duration. Numbers from our own parsing on 5 November. |
| **Personal data** | None in the source. |
| **Preprocessing** | MDX frontmatter, headings and component attributes parsed into modules: resources, prerequisites, topics with their stated outcomes, what finishes the module, and workload. Pages the authors hide (`unlisted`) are left out. Nothing is redistributed beyond what attribution requires. |

**Limitations we already know**

- Sections contain little original text (a median of about 75 words in the October 6 version), so checkpoint
  questions cannot come from the text alone. See Q-004.
- The linked resources belong to third parties under their own licences. We link to them and keep their
  metadata. We do not copy their content.
- Prerequisites exist only as prose. The planner gives them to the model as text.
- The curriculum changes. That is why each version is pinned to a commit, and why a path keeps the version it
  was planned for.
- The current version states workload for few modules and leaves difficulty and duration out of many resource
  cards, so time estimates cover only some modules.

---

## 2. Language model (LLM)

| | |
|---|---|
| **What for** | The level suggestion; a decision and a reason for every module; suggestions after a checkpoint; replanning for a new goal; marking open checkpoint answers; reviewing capstone projects; the assistant; writing checkpoint questions (once per module, not when a learner takes a checkpoint). |
| **Decision** | OpenAI `gpt-6-luna` by default (about $0.002 a path); Gemini (`gemini-3.5-flash-lite`, `gemini-3.8-flash`) and Groq (`openai/gpt-oss-120b`) free tiers as alternatives. Measurements and reasons in Q-003. |
| **What it receives** | The learner's onboarding answers and level, the curriculum's module outlines, open checkpoint answers, assistant messages, and the text files of a submitted project. The questions ask for no names or contact details. |
| **Access needs** | An API key, kept in `.env` (git-ignored) or `deploy/.env` on the server. `.env.example` shows the variable names with empty values. Keys never go into the repository, a notebook or a slide. |
| **Provider notes** | The Gemini API free tier may use requests to improve Google's products (checked 21 September 2026), one reason OpenAI is the default. Groq keeps inputs and outputs only for troubleshooting and abuse checks. |
| **Limits** | Output can differ between runs (measured: [October](test-results/2026-10-21-model-stability.md), [November](test-results/2026-11-20-current-curriculum.md)). The API limits model calls per learner (20 an hour by default). |
| **Fallback** | 1) The provider's next model. 2) If no model answers, the whole course in its own order, and the learner is told that personalization is unavailable. |

---

## 3. Example learners (invented)

- Three invented learners: P1 and P2 from the demo script in the project brief, P3 our own.
  - **P1:** experienced backend engineer, goal computer vision.
  - **P2:** beginner who finished an intro Python course last month, same goal.
  - **P3:** strong maths, little coding, goal multilingual speech systems.
- They are invented, not built from real people. No personal data.
- Stored in [config/profiles.yaml](../config/profiles.yaml); the page offers them as a starting point for demos.
  The decisions we expect for each module are in
  [test-results/expected-decisions.md](test-results/expected-decisions.md), for both curriculum versions.

---

## 4. Learner testing

- Five people outside the team, November 2026; protocol and results in [learner-testing.md](learner-testing.md).
- The protocol tells them what is collected and which model provider receives their answers. Names are not kept.
- **Nothing from these sessions is in the repository** except the summary.

---

## 5. Progress that learners choose to share (Stretch)

| | |
|---|---|
| **What** | For paths whose learner ticks "Share my progress anonymously": a random path id, the curriculum version, and events per module (included in the confirmed path, checkpoint failed, questions passed, finished) or for the path (goal changed), each with the time. |
| **What not** | Onboarding answers, the goal, the level, checkpoint answers, code, names, e-mail or IP addresses. The rate limit holds IP addresses in memory only, and the server's access log is turned off in `deploy/`. |
| **Where** | The API's PostgreSQL database (`DATABASE_URL`, a Docker volume in `deploy/`). Never in this repository. |
| **Who sees it** | Whoever holds `API_REPORT_TOKEN`, as counts per module (`GET /report`, `python -m roadmap report`). |
| **Default** | Off. Turning it off stops new events; events already sent stay counted, and the page says so. |

---

## 6. Data we generate

| Data | How it is made | Where it lives | Licence |
|---|---|---|---|
| Paths (JSON) | The API, for a learner; the command line, for the example learners | The learner's account on the API server, with their onboarding answers, until they delete it; a path planned without an account for a day; files the team writes with `--out`. Not committed: they contain curriculum text and can be rebuilt | CC BY-NC-SA 4.0. Every module carries its title and URL; the path carries the licence |
| Project submissions | A learner hands in a capstone | The API's database (the link, the note, the archive's name and size, the review) and `API_UPLOADS_DIR` (the archive, under a random name) on the API server. Seen by the learner and the reviewers only; for the AI review, the project's text files (up to about 120 000 characters) go to the model provider in `config/llm.yaml`; deleted with the account. Never in this repository | The learner's own work |
| Accounts | Sign-up on the curriculum site | The API's PostgreSQL database: the email (verified by Google, or not verified), a scrypt hash of the password or Google's id for the learner, session tokens as SHA-256 hashes. Deleted with the account. Never in this repository | — |
| Question reports | A learner marks a checkpoint question as wrong | The API's database: the account's id, the question, the reason and the comment; seen by reviewers. Not deleted with the account | — |
| Public progress links | A learner makes a read-only link | The API's database: a random token and the account; the page shows only finished modules. Removed with the account | — |
| Checkpoints (YAML) | Written by the model from a module's outline, reviewed by a person (Li Mikhail) | `checkpoints/` in this repository | CC BY-NC-SA 4.0, as material derived from the curriculum |

---

## 7. Hosting and third parties

- The team's VPS: [deploy/](../deploy/README.md) runs the site, the API and Caddy with Docker Compose.
- A learner who signs in with Google goes to Google's sign-in page, so Google learns that they signed in to
  this site. We receive their Google id and email address (scope `openid email`), nothing else.
- A learner who runs a coding problem loads Pyodide (Python for the browser) from the jsDelivr CDN, which sees
  their IP address like any website. The site can serve its own copy instead (`PYODIDE_URL`).
- The curriculum site carries HumbleBeeAI's own chat assistant; it is theirs, not part of our system.
