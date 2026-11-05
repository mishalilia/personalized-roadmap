# Learner testing (Target)

How we test with at least five learners from outside the team, and how we write it up. The results go to
`docs/test-results/learner-sessions.md`; nothing that identifies a learner goes into this repository.

## What we want to learn

1. Do learners understand the six questions, and how long do they take? (Is the questionnaire too long?)
2. Do they agree with the suggested level and the decisions in their path? Which ones do they change, and why?
3. Do the checkpoint questions feel fair, and does a failed checkpoint make sense to them: the locked modules,
   "prove" turned into "study"?
4. Would they keep using the path for the course? Would they keep the downloaded file?

## Before the sessions

- The API and the curriculum site (our fork) are hosted, and both links work from a phone.
- **Decide Q-003's follow-up first:** the Gemini free tier may use requests to improve Google's products. Either
  use a provider whose terms do not, or tell learners plainly and let them decline.
- Checkpoints for at least the first two modules are reviewed (`status: reviewed`), not drafts.
- Each learner gets a code (L1–L5). The code, not the name, appears in notes.

## Consent, read out at the start

> We are testing a student project that suggests a personal path through an online AI course. You will answer
> six questions about your experience. Your answers are sent to our server and to [model provider], which
> [does / may] keep them [as its terms say]. We do not store them; your path stays in your browser. We will
> take notes on what you do and say, under a code, not your name. You can stop at any time.

Record only that consent was given and when, under the learner's code.

## The session (about 25 minutes)

| Step | The learner does | We note |
|---|---|---|
| 1 | Opens the personal path page and answers the questions, thinking aloud | Time taken, questions skipped or misread |
| 2 | Reads the suggested level and its evidence | Agrees or changes it, and why |
| 3 | Reads the path; changes any decision they disagree with; confirms | Each change and the reason given |
| 4 | Opens their first module to study or prove and takes its checkpoint | Score, questions they found unclear or unfair |
| 5 | If they fail: reads what changed. If they pass at once: reads the suggestions | Whether the change or suggestion makes sense to them |
| 6 | Downloads the path | Whether they would keep it, where |

## Questions at the end

1. In one sentence, what did the tool do for you?
2. Which decision in your path would you not have made yourself?
3. Was any checkpoint question wrong or unclear? Which?
4. On a scale of 1–5, how likely would you be to follow this path for the course? Why not higher?

## Write-up, per learner, in `docs/test-results/learner-sessions.md`

- Code, date, background in one line (as they described it, no names or employers).
- Time for the questions; level suggested and level chosen.
- Decisions changed, with reasons.
- Checkpoint: module, score, unclear questions.
- What broke or confused them, quoted where possible.
- The rating and the answers above.

Then a summary across learners: what to fix, ordered by how many learners it affected.
