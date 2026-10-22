# Expected decisions for the example profiles

The reference that planner output is scored against (test plan §5). For each module: the expected decision,
any other decision we also accept, and why. Profiles are in [config/profiles.yaml](../../config/profiles.yaml);
modules are the 18 of curriculum version 5c21272.

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
