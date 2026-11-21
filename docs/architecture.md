# Architecture: C4 Level 1 and Level 2

**Status:** matches the code on 20 November 2026. Changes since the 23 September draft are listed at the end.

The diagrams are in Mermaid, which GitHub draws. **Dashed** boxes and arrows are Stretch items, all built. We draw
Level 1 and Level 2, as the course guide asks.

---

## C1: System Context

**Question it answers:** who uses the system, what are we building, and what does it connect to outside itself?

```mermaid
flowchart TB
    learner["<b>Learner</b><br/>[Person]<br/>Self-directed learner who wants a personal path"]
    reviewer["<b>Reviewer</b><br/>[Person]<br/>Course staff: check AI project reviews and reported questions"]
    owner["<b>Course Authors</b><br/>[Person, Stretch]<br/>Maintain the curriculum and want to see where learners stop"]
    system["<b>Personalized Roadmap System</b><br/>[Software system]<br/>Suggests the level, builds a personal path with reasons, checks understanding, reviews projects, keeps progress"]
    curriculum["<b>HumbleBeeAI Curriculum Repository</b><br/>[External system]<br/>Public GitHub repo with the course content, CC BY-NC-SA 4.0"]
    llm["<b>LLM Service</b><br/>[External system]<br/>OpenAI (GPT-6 Luna); Gemini or Groq as alternatives"]
    github["<b>GitHub</b><br/>[External system]<br/>Learners' public project repositories"]
    cdn["<b>jsDelivr CDN</b><br/>[External system]<br/>Serves Pyodide, Python for the browser"]
    google["<b>Google Sign-In</b><br/>[External system, optional]<br/>Confirms a learner's Google account and email"]

    learner -->|"Answers questions, confirms the path, takes checkpoints, submits projects, asks the assistant in"| system
    reviewer -->|"Checks project reviews and question reports in"| system
    system -->|"Reads course content from"| curriculum
    system -->|"Asks for levels, path decisions, suggestions, open-answer marks, project reviews and assistant answers from"| llm
    system -->|"Downloads submitted project repositories from"| github
    learner -->|"Loads Python for coding problems from"| cdn
    system -->|"Asks who signed in from (OAuth 2.0, OpenID Connect)"| google
    owner -.->|"Reads where learners stop from"| system

    classDef person fill:#fff3b0,stroke:#333
    classDef sys fill:#ffd43b,stroke:#333
    classDef ext fill:#dddddd,stroke:#333
    classDef later stroke-dasharray:5 5
    class learner,reviewer,owner person
    class system sys
    class curriculum,llm,github,cdn,google ext
    class owner later
```

**How to read it**

- The yellow box is what our team builds. Everything outside it is a person or an external system we do not control.
- The learner uses the system through a page on the curriculum site. The course authors only read a report of
  where learners who chose to share their progress stop (Stretch).
- We do **not** copy the curriculum into our repository. We read it from its own repository at pinned versions.
- The learner's browser loads Pyodide from the CDN only when they run a coding problem.
- Google takes part only when a learner chooses to sign in with it; no Google script runs on the site.
- GitHub is reached only to download a project a learner submitted as a link, through GitHub's own download
  address.
- Reviewers are people listed in `API_REVIEWER_EMAILS`; they can change any AI review.

---

## C2: Container

**Question it answers:** what are the main applications and data stores inside the system, and how do they talk to each other?

```mermaid
flowchart TB
    learner["<b>Learner</b><br/>[Person]"]
    reviewer["<b>Reviewer</b><br/>[Person]"]
    owner["<b>Course Authors</b><br/>[Person, Stretch]"]
    curriculum["<b>HumbleBeeAI Curriculum Repository</b><br/>[External system]"]
    llm["<b>LLM Service</b><br/>[External system: OpenAI; Gemini, Groq]"]
    github["<b>GitHub</b><br/>[External system]"]

    subgraph boundary ["Personalized Roadmap System [Software system]"]
        page["<b>Personal Path Page</b><br/>[Container: React in the curriculum site, Docusaurus]<br/>Questions, level, path and topics in a panel beside the course; checkpoints, coding problems and project submission on module pages; the assistant; the review page"]
        api["<b>HTTP API</b><br/>[Container: FastAPI, Python 3.11]<br/>Holds the model keys; grades checkpoints; applies locks and rules; reviews projects; answers the assistant"]
        cli["<b>Command Line</b><br/>[Container: Python 3.11]<br/>Fetches the curriculum, runs paths for the example learners, generates checkpoints, prints the report"]
        core["<b>Roadmap Core</b><br/>[Container: Python library]<br/>Parses each curriculum version, suggests the level, plans the path, checks the model's answers, falls back to the course order"]
        db[("<b>Accounts and Paths</b><br/>[Data store: PostgreSQL]<br/>Accounts, sessions, each learner's path and progress, project submissions and reviews, question reports")]
        uploads[("<b>Project Archives</b><br/>[Data store: files on the server]<br/>Submitted .zip and .tar.gz archives, under random names")]
        events[("<b>Shared Progress</b><br/>[Data store: PostgreSQL, Stretch]<br/>Anonymous events from learners who opted in")]
        config[("<b>Configuration</b><br/>[Data store: YAML files]<br/>Curriculum versions, questions, example learners, models")]
        checkpoints[("<b>Checkpoints</b><br/>[Data store: YAML files]<br/>Reviewed questions and coding problems per module and version")]
        checkout[("<b>Curriculum Checkouts</b><br/>[Data store: git worktrees]<br/>Each listed version at its pinned commit")]
    end

    learner -->|"Uses [HTTPS, browser]"| page
    reviewer -->|"Uses the review page [HTTPS, browser]"| page
    page -->|"Calls [HTTPS, JSON]"| api
    api -->|"Keeps accounts, paths and reviews in"| db
    api -->|"Keeps archives in"| uploads
    api -->|"Downloads linked projects from [HTTPS]"| github
    api -->|"Calls [Python]"| core
    cli -->|"Calls [Python]"| core
    api -->|"Reads"| checkpoints
    cli -->|"Writes"| checkpoints
    core -->|"Reads"| config
    core -->|"Checks out pinned versions into [git over HTTPS]"| checkout
    checkout -.-|"Copy of"| curriculum
    core -->|"Sends prompts and reads JSON answers from [HTTPS, OpenAI-compatible API]"| llm
    api -.->|"Records opted-in events in"| events
    owner -.->|"Reads the report from [HTTPS, token]"| api

    classDef person fill:#fff3b0,stroke:#333
    classDef ext fill:#dddddd,stroke:#333
    classDef later stroke-dasharray:5 5
    class learner,reviewer,owner person
    class curriculum,llm,github ext
    class events later
```

### What each container does

| Container | Responsibility | Technology | Tier |
|---|---|---|---|
| Personal Path Page | Asks the questions (or fills them from an example learner), shows the suggested level with its evidence and the path; the learner changes any decision and confirms it. Study, skim or skip per topic. On each module page: the decision, the checkpoint, the coding problem, the project submission, or "mark as done". Shows progress, the next module, hours, suggestions after a checkpoint and the goal change; the assistant; a public link to progress; the review page for reviewers | React components added to the curriculum site (Docusaurus); kept in `site/` with a patch for the site's own files | Baseline (the path), Target (checkpoints and progress) |
| Accounts and Paths | Accounts (email, scrypt password hash), sessions (hashed tokens, 30 days), each learner's path: decisions, topics, confirmation, progress per module, attempts, locks, suggestions; project submissions and reviews; question reports; paths planned before signing up, for a day | PostgreSQL beside the API (`src/roadmap/accounts.py`, `DATABASE_URL`); a SQLite file in tests | Target |
| HTTP API | Serves questions, example learners, a level and a path; confirms paths; serves checkpoint questions without answers, grades attempts, applies locks and rules; plans the rest of a path for a new goal; reviews submitted projects; answers the assistant; records opted-in events and serves the report. Holds the model keys; limits model calls per client | FastAPI (`src/roadmap/api.py`), one uvicorn worker | Target |
| Command Line | Fetches the curriculum versions, runs paths for the example learners and compares them, generates checkpoints and checks their coding problems, prints the report | `python -m roadmap` | Baseline |
| Project Archives | Archives learners submit, under random names; read in memory, never unpacked or run; deleted with the account | Files in `API_UPLOADS_DIR` (a Docker volume in `deploy/`) | Beyond the plan |
| Roadmap Core | Parses each curriculum version into modules; suggests the level and explains why; asks the model for study, prove or skip on every module with a reason; rejects an answer that leaves a module out and tries the next model; keeps the course order; falls back to the whole course when no model answers | Python library (`src/roadmap/`) | Baseline |
| Configuration | The curriculum versions with their commits, the seven questions, the three invented example learners, the providers and models in fallback order | YAML files (`config/`) | Baseline |
| Checkpoints | Questions (and a coding problem for modules that teach programming) per module and curriculum version, generated once and reviewed by a person | YAML files (`checkpoints/`) | Target |
| Curriculum Checkouts | Every listed version at its pinned commit, read directly from its Docusaurus files | One clone and a git worktree per version in `data/curricula/`, git-ignored | Baseline |
| Shared Progress | A random path id, the curriculum version and module events (included, failed, questions passed, finished, goal changed) from learners who opted in; counted per module in the report | The same PostgreSQL database | Stretch |

### Key decisions

1. **The model judges, code decides the rest.** The model suggests the level, a decision for each module and
   suggestions after a checkpoint, marks open answers and reviews projects. Code keeps the course order, checks
   that every module got a decision, grades multiple-choice questions, applies locks and attaches attribution, so
   these parts are tested and work without a model.
2. **The learner has the last word.** Every decision the model suggests can be changed, the path is confirmed
   before it is used, and suggestions after a checkpoint change nothing until the learner accepts them.
3. **Accounts keep the path on the server.** The browser holds an HTTP-only session cookie, not the path; every
   change to a path goes through the API and the path's rules. Shared progress stays anonymous: the
   events hold a random path id, never the account.
4. **The curriculum stays outside our repository.** We check it out at pinned commits and record the licence.

### Deployment

On one server, Docker Compose runs the curriculum site (nginx), the API, PostgreSQL and Caddy, which serves the
site and the API over HTTPS under two domain names ([deploy/](../deploy/README.md)). Only Caddy is reachable from
outside. Live since 21 November 2026 at https://polarislearning.me (the site) and https://api.polarislearning.me
(the API), on the team's VPS, where an existing reverse proxy serves HTTPS in Caddy's place.

### Changes since the first draft

- **No prerequisite graph.** The path follows the course's own order. The curriculum already orders its modules and states its prerequisites as text, and a hand-written graph would need maintenance every time the course changes. The trade-off: we cannot reorder modules for a learner, only include, prove or skip them.
- **"Prove" as a third decision.** Besides study and skip, the model can suggest that the learner proves a module they likely know. Where a module has a checkpoint, proving means passing it.
- **The interface is a page on the curriculum site.** The Baseline prototype used Streamlit; the page on the curriculum site replaced it and does everything it did. The site is static, so it calls an HTTP API that holds the model keys and runs the core.
- **Checkpoints are generated once per module, not per learner.** A person reviews them; multiple-choice questions cost no model call when a learner takes them and are graded by code; only the open question is marked by the model. Right answers appear only after a pass, and options are shuffled per attempt, so a learner cannot pass by remembering earlier attempts.
- **Coding problems run in the browser.** The learner's code runs in Pyodide, never on our server, which could not run untrusted code safely. The server takes the browser's word that the tests passed; it is the one step a learner could fake.
- **Several curriculum versions.** In October the site moved to a restructured course. New paths follow the current version; paths planned for an older listed version keep working against it. The parser, the planner and the checkpoints all work per version.
- **Progress lives on the server, behind accounts.** First kept in the browser without accounts (Q-005); the professors' feedback asked for login, and a path kept in the browser let a learner undo a lock or replay an attempt. A learner can still look at a planned path before signing up.
- **The path is part of the course pages.** A panel beside them shows the learner's progress, what is next and each module's status; each module page shows its decision and its checkpoint, with a link to the next module of the path.
- **Deployment on the team's VPS** with Docker Compose and Caddy, not a free host: the API holds keys and a small database, and free hosts sleep or reset their disks.
- **The model.** OpenAI `gpt-6-luna` by default; Gemini and Groq as free alternatives, all through the same OpenAI-compatible client (Q-003).
- **Topics inside a module.** The learner can study, skim or skip each topic; checkpoints ask only about topics not skipped.
- **Capstone projects are reviewed by a model** against each capstone's rubric, with every piece of evidence checked in code; reviewers can change any decision.

The modules inside the core (parser, level, planner, checkpoints, events, model client) are Level 3 and not drawn.
