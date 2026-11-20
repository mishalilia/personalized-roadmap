# Expected decisions for the example profiles

The reference that planner output is scored against (test plan §5). For each module: the expected decision,
any other decision we also accept, and why. Profiles are in [config/profiles.yaml](../../config/profiles.yaml);
first for the 18 modules of curriculum version 5c21272, then for the 20 of the current version (9fc5573).

Drafted with AI assistance (Claude) from the profiles and the module pages. Where two decisions are defensible,
both are accepted.

How a decision is scored:

- **match** — the expected decision or one we also accept;
- **harmful** — a module the learner needs is skipped, or "prove" is given with no evidence in the answers;
- **wasteful** — a module is studied although the learner clearly knows it or does not need it;
- **minor** — skip instead of prove, or prove instead of skip: the learner loses nothing they need.

## P1 · Experienced backend engineer, goal: computer vision research

| Module | Expected | Also accepted | Why |
|---|---|---|---|
| M1 Terminal & Algorithmic Basics | prove | — | Linux command line and Git every day |
| M2 Linear Algebra | study | prove | remembers matrix multiplication, eigenvectors "fuzzy"; research needs it |
| M3 Probability | study | prove | university course, unused apart from dashboard statistics |
| M4 Data Manipulation | study | — | Knows SQL and Git, but the checklist is mostly NumPy, Pandas, Matplotlib, which never used |
| ML Fundamentals | study | — | Never trained a model |
| Intro to AI Engineering | study | — | PyTorch, not used yet |
| Systems & Networking | prove | — | Runs services on Kubernetes and AWS |
| Infra Basics | prove | — | Docker, REST APIs, deployment are daily work; the HTML/JS item is small |
| Computer Vision · Resources | study | — | The goal |
| Computer Vision · Capstone | study | — | The goal |
| Data Science · Resources, Capstone | skip | — | Not the goal |
| Generative AI · Resources, Capstone | skip | — | Not the goal |
| NLP & LLMs · Resources | skip | study | transformers appear in vision research too, but the module is aimed at language |
| NLP & LLMs · Capstone | skip | — | Not the goal |
| AI Software Engineering · Resources | skip | prove | Not the goal; would pass it anyway |
| AI Software Engineering · Capstone | skip | — | Not the goal |

## P2 · Beginner after an intro Python course, goal: computer vision

Nothing can be proved: the answers give no evidence for any checklist.

| Module | Expected | Also accepted | Why |
|---|---|---|---|
| M1–M4 | study | — | One month of Python, no Git, no maths beyond high school |
| ML Fundamentals, Intro to AI Engineering | study | — | No machine learning |
| Systems & Networking | study | skip | part of the core, but far from the goal |
| Infra Basics | study | — | The computer vision capstone needs Docker and a web UI |
| Computer Vision · Resources, Capstone | study | — | The goal |
| Data Science, Generative AI, NLP & LLMs, AI Software Engineering (all) | skip | — | Not the goal |

## P3 · Strong maths, little coding, goal: multilingual speech systems

Speech recognition and translation are in the **Generative AI** specialization ("NLP, Diffusion Models, and
Speech Technologies"), and its capstone is automated video dubbing: speech recognition, translation, speech
synthesis. That is P3's goal almost exactly.

| Module | Expected | Also accepted | Why |
|---|---|---|---|
| M1 Terminal & Algorithmic Basics | study | — | Command line only to start MATLAB |
| M2 Linear Algebra | prove | skip | Core of the degree, used daily |
| M3 Probability | prove | skip | Core of the degree, used daily |
| M4 Data Manipulation | study | — | No NumPy, Pandas, SQL or Git |
| ML Fundamentals | study | — | knows the theory of regression and gradient descent, never in code |
| Intro to AI Engineering | study | — | No PyTorch |
| Systems & Networking | study | skip | part of the core, but far from the goal |
| Infra Basics | study | — | The Generative AI capstone needs Docker and REST APIs |
| Computer Vision · Resources, Capstone | skip | — | Not the goal |
| Data Science · Resources, Capstone | skip | — | Not the goal |
| Generative AI · Resources | study | — | Speech technologies |
| Generative AI · Capstone | study | — | Speech recognition and translation |
| NLP & LLMs · Resources | study | skip | transformers underlie speech and translation models, but the speech material is in Generative AI |
| NLP & LLMs · Capstone | skip | — | A RAG task assistant, not speech |
| AI Software Engineering · Resources, Capstone | skip | — | Not the goal |

---

# Current curriculum (commit 9fc5573, 20 modules)

Written on 20 November 2026, on the same rules as above. "Prove" is possible only for
modules that state what finishes them; electives are optional, so skipping them is expected.

## P1 · Experienced backend engineer, goal: computer vision research

| Module | Expected | Also accepted | Why |
|---|---|---|---|
| Terminal & Algorithmic Basics | prove | skip | Linux command line and Git every day |
| Math for AI | study | prove | studied it, has faded; research needs it |
| Data Foundations | study | — | SQL daily, but never used NumPy or Pandas |
| Engineering Fundamentals · Electives | skip | study | optional |
| Software Engineering for AI | prove | skip | readable code, tests and reviews are daily work |
| Applied ML & Deep Learning | study | — | never trained a model |
| LLM Fundamentals and Agent Workflows | study | skip | part of the core, far from the goal |
| Systems, Networking & Data | prove | skip | runs services on Kubernetes and AWS with PostgreSQL |
| APIs, Containers & Deployment | prove | skip | Docker, REST APIs and CI are daily work |
| Core Systems · Electives | skip | study | optional |
| Computer Vision · Resources, Capstone | study | — | the goal |
| Data Science · Resources, Capstone | skip | — | not the goal |
| Generative AI · Resources, Capstone | skip | — | not the goal |
| NLP & LLMs · Resources | skip | study | transformers appear in vision too, but the module is about language |
| NLP & LLMs · Capstone | skip | — | not the goal |
| AI Software Engineering · Resources | skip | prove | not the goal; would pass it anyway |
| AI Software Engineering · Capstone | skip | — | not the goal |

## P2 · Beginner after an intro Python course, goal: computer vision

| Module | Expected | Also accepted | Why |
|---|---|---|---|
| Terminal & Algorithmic Basics, Math for AI, Data Foundations | study | — | one month of Python, no Git, school maths |
| Engineering Fundamentals · Electives | skip | study | optional |
| Software Engineering for AI | study | — | has written only course exercises |
| Applied ML & Deep Learning | study | — | no machine learning |
| LLM Fundamentals and Agent Workflows | study | skip | part of the core, far from the goal |
| Systems, Networking & Data | study | skip | part of the core, far from the goal |
| APIs, Containers & Deployment | study | — | the computer vision capstone needs Docker and a web UI |
| Core Systems · Electives | skip | study | optional |
| Computer Vision · Resources, Capstone | study | — | the goal |
| Data Science, Generative AI, NLP & LLMs, AI Software Engineering (all) | skip | — | not the goal |

## P3 · Strong maths, little coding, goal: multilingual speech systems

| Module | Expected | Also accepted | Why |
|---|---|---|---|
| Terminal & Algorithmic Basics | study | — | command line only to start MATLAB |
| Math for AI | prove | skip | core of the degree, used daily |
| Data Foundations | study | — | no NumPy, Pandas or SQL |
| Engineering Fundamentals · Electives | skip | study | optional |
| Software Engineering for AI | study | — | short MATLAB scripts only |
| Applied ML & Deep Learning | study | — | knows the theory, never trained a model in code |
| LLM Fundamentals and Agent Workflows | study | — | transformers underlie speech and translation models |
| Systems, Networking & Data | study | skip | part of the core, far from the goal |
| APIs, Containers & Deployment | study | — | the Generative AI capstone needs Docker and REST APIs |
| Core Systems · Electives | skip | study | optional |
| Computer Vision · Resources, Capstone | skip | — | not the goal |
| Data Science · Resources, Capstone | skip | — | not the goal |
| Generative AI · Resources, Capstone | study | — | speech technologies; the capstone is speech recognition, translation and dubbing |
| NLP & LLMs · Resources | study | skip | language models matter for translation, but the speech material is in Generative AI |
| NLP & LLMs · Capstone | skip | — | a RAG task assistant, not speech |
| AI Software Engineering · Resources, Capstone | skip | — | not the goal |
