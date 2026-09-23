# Question Log

Open questions, who to ask, and what was decided. Updated whenever a question is answered.

Status values: Not checked / Under review / Decided.

---

### Q-001 — Does a generated path count as an adaptation of the curriculum?

- **Related DoD item:** Baseline — licence attribution correctly implemented
- **Why it matters:** The answer decides how much of this repository share-alike reaches. Attribution is
  required either way, and licence compliance is graded.
- **Our reading:** A path links to and orders material without reproducing it, which makes it a collection
  rather than an adaptation; Creative Commons states that a collection does not create adapted material.
- **What we have tried:** Read the licence in the source repository, where it is stated inconsistently (see
  the licence section of the README), and applied the stricter option to ourselves. That is safe under
  either answer.
- **Ask:** Professor
- **Status:** Under review
- **Decision and date:** —
- **Follow-up:** use the professor's answer when we are asked about the licence at the demo.

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
- **What we have tried:** Provider documentation checked on 21 September; nothing measured yet. Google AI
  Plus gives no API quota. Candidates: Gemini API free tier (requests may be used to improve Google's
  products), Groq free plan, a local model. Next: generate one full path and measure tokens, time and
  variation between runs.
- **Ask:** Team decision; assistant if no free option holds
- **Status:** Under review
- **Decision and date:** —
- **Follow-up:** TBD — pin the chosen model in the configuration and record its limits and the fallback in
  the README.

### Q-004 — What can checkpoint questions actually be generated from?

- **Related DoD item:** Target — checkpoint questions generated from the content of each section
- **Why it matters:** The source is a curated set of links rather than lesson prose. We measured it: 126
  sections carry 12,786 words of original text in total, a median of 75 words each, with 80 of the 126 under
  100 words. Questions that test understanding cannot be extracted from 75 words, and the linked material is
  third-party ("Third party sources: under their original licence" in the source README), so copying from it
  is not open to us either. This gates the whole Target tier.
- **What we have tried:** Measured the corpus as above, and confirmed that `llms-full.txt` cannot replace
  parsing the content: 10,646 characters, 4 URLs, no resource metadata. The check is 10 questions generated
  for one module from repository content only, rated by someone who knows the topic for how many test
  application rather than recall.
- **Working answer:** Generate questions about the topic the section defines. Its heading and structure,
  stated learning outcomes, declared difficulty and the authors' per-resource notes specify what to test; the
  model supplies the subject knowledge. Nothing is copied from third-party sites and it scales across all 126
  sections. Known risk to report as a limitation: questions can drift from what a specific linked resource
  actually covered. Fetching openly licensed sources stays available as a Stretch refinement.
- **Ask:** Team experiment first
- **Status:** Under review
- **Decision and date:** —
- **Follow-up:** TBD — if the approach holds, build the question generation around it; if it does not,
  narrow the checkpoint scope and say so in the README.
