# Team Ground Rules

Course rules on data, attribution and repositories apply regardless of what is written here.

## Meetings

- One fixed weekly meeting, **Mondays at 16:30**.
- Tell the team in advance if you cannot attend.
- Say early if you are stuck or may miss a date.

## Code and review

- Work on branches; changes reach `main` through a pull request.
- Important changes are reviewed by the assigned reviewer before merging.
- Each feature owner tests their own work and agrees the testing method with Data & Research.

## Everyone understands the project

- Every member must be able to explain who the project is for and how the main features work, including
  parts they did not write.

## Learner data

- Data collected from real learners during testing is kept minimal, participants are told what is collected,
  and it is not published or committed to this repository.

## API keys and cost

- No API key in code, notebooks, commits or presentations. Secrets live in a local `.env`, which is
  git-ignored; `.env.example` holds the variable names with blank values.
- If a key is ever committed, deleting it is not enough — it is revoked and rotated immediately.
- The Baseline must be reachable on free tiers or open models. We ask before paying for anything.

## AI tools

- AI-generated code and text are read and understood before being committed. If nobody on the team can
  explain it, it does not go in.
- Nothing is reported as tested or verified unless it was actually run.
