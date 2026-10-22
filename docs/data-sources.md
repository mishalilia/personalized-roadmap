# Data Sources (draft)

**Status:** updated for the midterm. Anything not yet decided is marked **TBD**.

Default rule from the course: public or safe sample data only. No personal data, no real company data.

---

## 1. Curriculum content (main data source)

| | |
|---|---|
| **Name** | HumbleBeeAI Open Curriculum |
| **Where** | Site: <https://roadmap.humblebee.ai>. Repository: <https://github.com/humblebeeai/int.academy-curriculum> |
| **Licence** | CC BY-NC-SA 4.0: attribution required, share-alike applies to adaptations, non-commercial only. The source files disagree (some say CC BY-SA). We follow the stricter reading. See Q-001 in `questions.md`. |
| **How we get it** | `git clone` of the public repository. No scraping, no credentials. |
| **Access so far** | Yes. The repository is public, and the content statistics in `project-overview.md` come from parsing it. |
| **Version** | Commit [`5c21272`](https://github.com/humblebeeai/int.academy-curriculum/commit/5c212720af50ffd0a1592ea6c0f812c3af733ed3), 7 September 2026 |
| **Shape** | MDX files with structured metadata. Numbers from our own parsing (see `project-overview.md`): about 25 MDX files, 116 linked resources with type, title, URL, duration, difficulty and rationale. |
| **Personal data** | None in the source. |
| **Preprocessing** | Parse MDX frontmatter and component attributes into modules with their resources, prerequisites and checklists. Nothing is redistributed beyond what attribution requires. |

**Limitations we already know**

- Sections contain little original text (median about 75 words), so checkpoint questions cannot come from the text alone. See Q-004.
- The 116 linked resources belong to third parties under their own licences. We link to them and keep their metadata. We do not copy their content.
- Prerequisites exist only as prose. The planner gives them to the model as text.
- The curriculum can change. That is why we pin a commit.

---

## 2. Language model (LLM)

| | |
|---|---|
| **What for** | Level inference, relevance judgements, skip justifications. Later (Target): checkpoint questions. |
| **Options** | (a) A free hosted API: the Gemini API free tier or Groq. (b) An open model run locally or on Colab or Kaggle. |
| **Decision** | `gemini-3.5-flash-lite`, then `gemini-3.8-flash`; Groq `openai/gpt-oss-120b` as the second provider. Measurements in Q-003. |
| **Access needs** | An API key, kept in `.env` (git-ignored). `.env.example` shows the variable names with empty values. Keys never go into the repo, a notebook or a slide. |
| **Provider notes** (checked 21 September 2026) | The Google AI Plus student offer gives no API quota. The Gemini API free tier may use requests to improve Google's products; Groq keeps inputs and outputs only for troubleshooting and abuse checks. |
| **Limits** | Free-tier quotas are counted per model and can change. Output can differ between runs. |
| **Fallback** | 1) The provider's next model. 2) If no model answers, the whole course in its own order, and the learner is told that personalization is unavailable. |

---

## 3. Test learner profiles (invented)

- Three invented learner profiles: P1 and P2 from the demo script in the project brief, P3 our own.
  - **P1:** experienced backend engineer, goal computer vision.
  - **P2:** beginner who finished an intro Python course last month, same goal.
  - **P3:** strong maths, little coding, goal multilingual speech systems.
- Profiles are invented, not built from real people. No personal data.
- Stored in [config/profiles.yaml](../config/profiles.yaml). The decisions we expect for each module are in
  [test-results/expected-decisions.md](test-results/expected-decisions.md), written after the first model runs.

---

## 4. Real learner testing (Target)

- At least 5 people outside the team.
- We tell them what we collect and why, and which model provider receives their answers. Names are not kept. How consent is recorded: TBD. We collect only what we need: answers, observations of what broke, one short rating.
- **Nothing from these sessions goes into the public repository.**

---

## 5. Derived data we generate

| Data | How it is made | Licence |
|---|---|---|
| Generated paths (JSON) | Output of the core | CC BY-NC-SA 4.0. Every module carries its title and URL; the path carries the licence |

Paths are written to `out/`, which is not committed: they contain curriculum text and can be rebuilt.

---

## 6. Hosting (Target)

Free tier only. **TBD** between Hugging Face Spaces and another free option. No paid service is needed for Baseline.
