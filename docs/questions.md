# Question Log

Questions we had, who we asked, and what was decided.

---

### Q-001 — Does a generated path count as an adaptation of the curriculum?

- **Related DoD item:** Baseline — licence attribution correctly implemented
- **Why it matters:** The answer decides how much of this repository share-alike reaches. Attribution is
  required either way, and licence compliance is graded.
- **Our reading:** A path orders the modules and includes their titles, descriptions, topics and completion
  criteria, so it may count as an adaptation rather than a collection. "Prove" needs the completion criteria,
  so we keep them. Checkpoint questions are written from the same material, so the same question applies to
  them.
- **What we have tried:** Read the licence in the source repository, where it is stated inconsistently (see
  the licence section of the README), and applied the stricter option to ourselves. That is safe under
  either answer.
- **Ask:** Professor
- **Status:** Decided
- **Decision and date:** 20 November 2026: no longer relevant. HumbleBeeAI is the project's partner and gave us
  its course to use; DotPath runs only on HumbleBeeAI's course site. We keep the attribution and the
  curriculum's licence, CC BY-NC-SA 4.0, on paths and checkpoints.
- **Follow-up:** none.

### Q-002 — In what form should AI assistance be recorded?

- **Related DoD item:** Not applicable (course rule)
- **Why it matters:** The rules require AI-generated content to be attributed and require a record of what we
  used it for and what we reviewed or changed, but do not state the granularity: a summary section, a
  separate document, or per-commit notes.
- **What we have tried:** Recorded purpose, what was verified and what was changed in the README.
- **Ask:** Professor
- **Status:** Decided
- **Decision and date:** A section in the README is enough for now; move it to a separate document if it
  grows, keeping the README readable (professor, 20 September 2026).
- **Follow-up:** keep the README section short and move it out when it grows.

### Q-003 — Which model, and does the free tier cover the Baseline?

- **Related DoD item:** Baseline — level inference and path generation
- **Why it matters:** Every project is required to have a free path
  to Baseline. The choice also affects latency and how stable the output is across repeated runs.
- **What we have tried:** Provider documentation checked on 21 September; Google AI Plus gives no API quota.
  Candidates: Gemini API free tier (requests may be used to improve Google's products), Groq free plan, a
  local model. On 3 October we ran the prototype for P1–P3; a path takes two model calls, level then plan.
  - Groq, per model: 30 requests/min, 1,000 a day, 8K tokens/min, 200K tokens a day. `openai/gpt-oss-120b`
    needs 6–8K tokens and about 6 s per path, so one path a minute and 25–30 a day; a second path in the
    same minute waited 20–40 s. Its answers were always valid JSON. The smaller `openai/gpt-oss-20b`, used
    once as the fallback, left modules out of its plan.
  - Gemini, per project and model (AI Studio): `gemini-3.8-flash` 5 requests/min and 20 a day, which is 10
    paths; `gemini-3.5-flash-lite` 15 a minute and 500 a day. Daily limits reset at midnight Pacific time.
    `gemini-3.8-flash` took 14–27 s per path and was refused as overloaded (503) on 4 of 10 calls;
    flash-lite answered instead.
  - Quality: P1 and P2 differ by 40–45% (0–22% before the prove option), P3 by 62–77% from both. Some
    decisions look wrong — flash-lite skipped Data Manipulation for P1, who has never used NumPy or Pandas
    — and `gpt-oss-120b` changed its decision on Systems & Networking for P1 between runs.
  - 21 October, each model 3–5 times per profile with no fallback, scored against the expected decisions
    ([report](test-results/2026-10-21-model-stability.md)): `gemini-3.5-flash-lite` kept 93% of its decisions
    across runs and matched 96%; `gpt-oss-120b` kept 76%, and its wrong skips landed in different modules each
    run; `gemini-3.8-flash` was the most stable but took 35 s a path; `gpt-oss-20b` cut its answer short in 5
    of 9 paths.
- **Ask:** Team decision; assistant if no free option holds
- **Status:** Decided
- **Decision and date:** 22 October 2026: `gemini-3.5-flash-lite`, then `gemini-3.8-flash`; Groq
  `openai/gpt-oss-120b` as the second provider; `gpt-oss-20b` dropped. November 2026:
  OpenAI `gpt-6-luna` became the default, so learners' answers do not go to a free tier that may use them to
  improve the provider's products. It costs about $0.002 a path ($0.10 per million input tokens, $0.50 per
  million output; token counts from our server's log on 20 November). Gemini and Groq stay in `config/llm.yaml`,
  so the Baseline still runs on a free tier.
- **Follow-up:** none.

### Q-004 — What can checkpoint questions actually be generated from?

- **Related DoD item:** Target — checkpoint questions generated from the content of each section
- **Why it matters:** The source is a curated set of links rather than lesson prose. We measured it: 126
  sections carry 12,786 words of original text in total, a median of 75 words each, with 80 of the 126 under
  100 words. Questions that test understanding cannot be extracted from 75 words, and the linked material is
  third-party ("Third party sources: under their original licence" in the source README), so copying from it
  is not open to us either. This gates the whole Target tier.
- **What we have tried:** Measured the corpus as above, and confirmed that `llms-full.txt` cannot replace
  parsing the content: 10,646 characters, 4 URLs, no resource metadata. Built on the working answer below:
  `python -m roadmap checkpoints` gives the model a module's topics, stated outcomes, resource notes and
  completion criteria, and asks for questions on each topic. Run with GPT-6 Luna for 13 modules of the current
  version; every question was then reviewed by a person.
- **Working answer:** Generate questions about the topic the section defines. Its heading and structure,
  stated learning outcomes, declared difficulty and the authors' per-resource notes specify what to test; the
  model supplies the subject knowledge. Nothing is copied from third-party sites and it scales across all 126
  sections. Known risk to report as a limitation: questions can drift from what a specific linked resource
  actually covered. Fetching openly licensed sources stays available as a Stretch refinement.
- **Ask:** Team experiment first
- **Status:** Decided
- **Decision and date:** November 2026: the working answer, with a pool of questions per topic, an open
  question marked against a rubric, and a coding problem per topic. Every question is reviewed by a person
  before learners see it; learners can report a wrong question in one click.
- **Follow-up:** none.

### Q-005 — Where is a learner's path kept: in their browser or on our server?

- **Related DoD item:** Target — progress blocked past a failed checkpoint; a usable web interface
- **Why it matters:** At first accounts were out of scope, so the path and its progress lived in the learner's
  browser and in the file they downloaded. That loses the path on another device or after clearing the browser,
  and a learner who edited the saved path could undo a lock or replay an attempt.
- **Ask:** Professor
- **Status:** Decided
- **Decision and date:** 8 November 2026: on the server. The professors' feedback asked for login, so the path
  is kept under the learner's account (Google, or email and password) and every change goes through the API. A
  path planned before signing up is kept for a day; the learner can delete the account with everything in it.
- **Follow-up:** none.
