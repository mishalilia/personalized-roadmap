# The personal path page for the curriculum site

The learner's side of DotPath: React code added to the curriculum site,
[humblebeeai/int.academy-curriculum](https://github.com/humblebeeai/int.academy-curriculum) (Docusaurus), that
talks to this repository's HTTP API (`src/roadmap/api.py`). It is kept here because the curriculum site is
HumbleBeeAI's repository.

## What is here

- `src/`: new files, copied into the curriculum site as they are — the components in
  `src/components/personal-path/`, the pages `/personal-path`, `/progress`, `/report` and `/review`, and theme
  overrides for the docs sidebar and module pages.
- `upstream.patch`: changes to files the curriculum site already has — two settings (`PERSONAL_PATH_API`,
  `PYODIDE_URL`) in `.env.example`, `Dockerfile`, `compose.yml`, `docusaurus.config.ts` and `README.md`; the path
  panel mounted in `src/theme/Root.tsx` in place of the site's roadmap pop-up, which is removed.

Both are made against curriculum commit `9fc5573` (22 October 2026), the version `config/curriculum.yaml` calls
`current`.

## What a learner gets

- A panel beside the course pages, which the learner can widen: questions, level, path, account.
- Across the course: progress and the next module above the docs sidebar, each module's status in the sidebar,
  the decision and topics at the top of a module page, and its checkpoint, coding problem or project submission
  at the end.
- An assistant in the panel; `/progress?link=…`, a read-only page of what a learner finished.
- For reviewers: `/review` (project reviews and reported questions) and `/report` (where learners stop).

## Run it locally

From this repository's root, the API (Python 3.11):

```sh
pip install -e ".[api]"
python -m roadmap fetch
uvicorn roadmap.api:app --app-dir src --port 8000
```

The site with the page added (Node 20 or later):

```sh
git clone https://github.com/humblebeeai/int.academy-curriculum.git
cd int.academy-curriculum
git checkout 9fc5573
cp -r ../personalized-roadmap/site/src .
git apply ../personalized-roadmap/site/upstream.patch
npm ci
PERSONAL_PATH_API=http://localhost:8000 npm start
```

Then open <http://localhost:3000/personal-path>. Adjust `../personalized-roadmap` to where this repository is.
Without a model key in `.env` the API still answers, but every path follows the course as written.
