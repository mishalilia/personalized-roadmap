# Architecture: C4 Level 1 and Level 2 (draft)

**Status:** initial draft for the 23 September submission. Things we have not decided are marked **TBD**.

The diagrams are written in Mermaid, which GitHub draws automatically. **Dashed** boxes and arrows are Target or Stretch items, not Baseline.

We draw only Level 1 and Level 2 for now, as the course guide asks. We will update them as the implementation changes.

---

## C1: System Context

**Question it answers:** who uses the system, what are we building, and what does it connect to outside itself?

```mermaid
flowchart TB
    learner["<b>Learner</b><br/>[Person]<br/>Self-directed learner who wants a personal path"]
    owner["<b>Content Owner</b><br/>[Person, Stretch]<br/>Maintains the curriculum and wants to see where learners drop off"]
    system["<b>Personalized Roadmap System</b><br/>[Software system]<br/>Infers the learner's level, builds a personal path with reasons, checks understanding"]
    curriculum["<b>HumbleBeeAI Curriculum Repository</b><br/>[External system]<br/>Public GitHub repo with the course content, CC BY-NC-SA 4.0"]
    llm["<b>LLM Service</b><br/>[External system]<br/>Language model that judges level and relevance (provider TBD)"]

    learner -->|"Answers questions and reads the path in"| system
    system -->|"Reads course content from"| curriculum
    system -->|"Asks for level estimates and relevance judgements from"| llm
    system -.->|"Sends drop-off report to (Stretch)"| owner

    classDef person fill:#fff3b0,stroke:#333
    classDef sys fill:#ffd43b,stroke:#333
    classDef ext fill:#dddddd,stroke:#333
    classDef later stroke-dasharray:5 5
    class learner,owner person
    class system sys
    class curriculum,llm ext
    class owner later
```

**How to read it**

- The yellow box is what our team builds. Everything outside it is a person or an external system we do not control.
- The learner is the only user in Baseline. The content owner appears only in the Stretch item "drop-off analysis".
- We do **not** copy the curriculum into our repository. We read it from its own repository at a pinned version.
- Every arrow says what the connection is used for.

---

## C2: Container

**Question it answers:** what are the main applications and data stores inside the system, and how do they talk to each other?

```mermaid
flowchart TB
    learner["<b>Learner</b><br/>[Person]"]
    curriculum["<b>HumbleBeeAI Curriculum Repository</b><br/>[External system]"]
    llm["<b>LLM Service</b><br/>[External system]"]

    subgraph boundary ["Personalized Roadmap System [Software system]"]
        core["<b>Roadmap Core</b><br/>[Container: Python library with a CLI, version TBD]<br/>Parses the curriculum, infers level, plans the path, enforces prerequisites, runs the fallback planner"]
        gstore[("<b>Curriculum Graph</b><br/>[Data store: JSON files]<br/>Nodes and prerequisite edges")]
        pathjson[("<b>Path Output</b><br/>[Data store: JSON files]<br/>Generated path: nodes, reasons, skips, level, attribution")]
        webui["<b>Web UI</b><br/>[Container: TBD, Target]<br/>Shows the path and runs checkpoints"]
        progress[("<b>Progress Store</b><br/>[Data store: TBD, Target]<br/>Checkpoint results and current position")]
    end

    learner -->|"Answers questions and reads the path using [CLI]"| core
    learner -.->|"Uses [HTTPS]"| webui
    core -->|"Clones a pinned version from [git over HTTPS]"| curriculum
    core -->|"Sends prompts and reads structured answers from [HTTPS, JSON]"| llm
    core -->|"Writes and reads [JSON files]"| gstore
    core -->|"Writes [JSON files]"| pathjson
    webui -.->|"Reads the path from [JSON files]"| pathjson
    webui -.->|"Saves and loads results in"| progress
    webui -.->|"Calls [Python]"| core

    classDef person fill:#fff3b0,stroke:#333
    classDef ext fill:#dddddd,stroke:#333
    classDef later stroke-dasharray:5 5
    class learner person
    class curriculum,llm ext
    class webui,progress later
```

The language model service is drawn **outside** the system boundary because we call it, we do not run it.

### What each container does

| Container | Responsibility | Technology | Tier |
|---|---|---|---|
| Roadmap Core | Turns the curriculum into a graph; reads the onboarding questions from a config file in the repo; infers the level and explains why; builds an ordered path; marks and justifies skipped items; enforces prerequisites; falls back to a rule-based planner when no model is available | Python library with a CLI (Python version TBD) | Baseline |
| Curriculum Graph | Stores the parsed curriculum (modules, sections, resources) and the prerequisite edges that our team writes by hand | JSON files, rebuilt from a pinned commit | Baseline |
| Path Output | The generated path. This JSON is the contract: any interface only needs to read it | JSON files | Baseline |
| Web UI | Shows the path, runs checkpoint questions, lets the learner correct the level | TBD (Streamlit, Gradio or a small web app) | Target |
| Progress Store | Remembers checkpoint results and where the learner is in the path | TBD (local file, SQLite or browser storage) | Target |

### Key decisions

1. **The core is a library plus a CLI, not a service.** Baseline needs no HTTP API and no database. We add them only when the Target web interface needs them. This matches the "Basic Python module" starter template we chose.
2. **The path JSON is the contract** between the core and any interface.
3. **The LLM is used only where a judgement is needed** (level and relevance). Order, prerequisites and attribution are ordinary code, so they can be tested and still work without a model.
4. **The curriculum stays outside our repository.** We clone it at a pinned commit and record the licence.

### Open points (TBD)

- Python version, and whether the Baseline interface is a command line, a script or a notebook.
- Web UI technology, and where progress is stored (Target only).
- Which LLM and which free path we use (Q-003 in `questions.md`).
- Whether we may send curriculum text and learner answers to an external AI service (Q-005).
- What counts as "human review and approval" of what the learner sees (Q-006).
- Whether hosting is Hugging Face Spaces or something else (free tier only).

### Not shown on purpose

The modules inside the core (parser, planner, level inference, checkpoint generator) belong to Level 3. We will draw them if the mid-course review needs them.
