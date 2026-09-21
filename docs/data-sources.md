# Data Sources (draft)

**Status:** initial draft for the 23 September submission. Anything not yet decided is marked **TBD**.

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
| **Version** | **TBD.** Pin one commit hash before the submission and write it here: `<commit hash>` on `<date>` |
| **Shape** | MDX files with structured metadata. Numbers from our own parsing (see `project-overview.md`): about 25 MDX files, 116 linked resources with type, title, URL, duration, difficulty and rationale. |
| **Personal data** | None in the source. |
| **Preprocessing** | Parse MDX frontmatter and component attributes into a node graph. Add prerequisite edges by hand. Nothing is redistributed beyond what attribution requires. |

**Limitations we already know**

- Sections contain little original text (median about 75 words), so checkpoint questions cannot come from the text alone. See Q-004.
- The 116 linked resources belong to third parties under their own licences. We link to them and keep their metadata. We do not copy their content.
- Prerequisites exist only as prose, not as machine-readable data. Our team writes and reviews them.
- The curriculum can change. That is why we pin a commit.

---

## 2. Language model (LLM)

| | |
|---|---|
| **What for** | Level inference, relevance judgements, skip justifications. Later (Target): checkpoint questions. |
| **Options** | (a) A free-tier hosted model through an API key, for example from Google AI Studio. (b) An open model run locally or on Colab or Kaggle. |
| **Decision** | **TBD** (Q-003). We measure one full path: tokens used, time, and how much the result changes between runs. |
| **Access needs** | An API key, kept in `.env` (git-ignored). `.env.example` shows the variable names with empty values. Keys never go into the repo, a notebook or a slide. |
| **Check before relying on it** | The student offer for Google AI Plus is a consumer subscription. It may not include API access from code. Verify this first. |
| **Limits** | Free-tier quotas are counted per model and can change. Output can differ between runs. |
| **Open question** | May we send curriculum text and learner answers to an external AI service? Tracked as Q-005. Until it is answered, Baseline tests use invented profiles only. |
| **Fallback** | 1) A smaller model of the same family. 2) If no model works, the rule-based planner (order from the prerequisite graph and declared difficulty). The learner sees a message that personalization is unavailable. |

---

## 3. Test learner profiles (invented)

- 10 invented learner profiles with an expected level written down **before** we run anything. This includes the three demo profiles:
  - **P1:** experienced backend engineer, goal computer vision.
  - **P2:** beginner who finished an intro Python course last month, same goal.
  - **P3:** clearly different from both (proposal: strong math, weak coding, goal multilingual speech systems).
- Profiles are invented, not built from real people. No personal data.
- Stored in `config/` as YAML.

---

## 4. Real learner testing (Target)

- At least 5 people outside the team. Whether classmates count is a question for the professors.
- We tell them what we collect and why. We collect only what we need: answers, observations of what broke, one short rating.
- **Nothing from these sessions goes into the public repository.**

---

## 5. Derived data we generate

| Data | How it is made | Licence |
|---|---|---|
| Curriculum graph (JSON) | Parsed from the pinned commit, plus our hand-written prerequisite edges | CC BY-NC-SA 4.0 (derived from the curriculum) |
| Generated paths (JSON) | Output of the core | CC BY-NC-SA 4.0. Every item carries source title, URL and licence |

Both can be rebuilt from the pinned commit, so large files do not need to live in the repo.

---

## 6. Hosting (Target)

Free tier only. **TBD** between Hugging Face Spaces and another free option. No paid service is needed for Baseline.
