# The personal path page for the curriculum site

The React code that replaces the Streamlit app. It is not a site of its own: it is added to the curriculum
site, [humblebeeai/int.academy-curriculum](https://github.com/humblebeeai/int.academy-curriculum) (Docusaurus),
and talks to this repository's HTTP API (`src/roadmap/api.py`).

It is kept here, and not in a fork of the curriculum repository, because the team has no such fork yet.

## What is here

- `src/components/personal-path/`, `src/pages/personal-path.tsx`, `src/theme/DocItem/Content/index.tsx`: new
  files, copied into the curriculum site as they are.
- `upstream.patch`: small changes to five files the curriculum site already has (`docusaurus.config.ts`,
  `.env.example`, `Dockerfile`, `compose.yml`, `README.md`): two settings and a "Personal path" link in the
  top bar.

Both were made against curriculum commit `9fc5573` (22 October 2026), the version `config/curriculum.yaml`
calls `current`.

## What a learner gets

- `/personal-path`: answer the questions, get a path, change any decision, confirm it. The path is kept in the
  learner's browser; there are no accounts.
- On a module page: the path's decision for the module, and its checkpoint. Five questions an attempt, four to
  pass; then the coding problem, which runs in the browser (Pyodide).
- Changing the goal replans the modules not yet finished.

## Run it locally

From this repository's root, the API (needs Python 3.11):

```sh
pip install -e ".[api]"
python -m roadmap fetch
uvicorn roadmap.api:app --app-dir src --port 8000
```

The site, with the page added (needs Node 20 or later):

```sh
git clone https://github.com/humblebeeai/int.academy-curriculum.git
cd int.academy-curriculum
git checkout 9fc5573
cp -r ../personalized-roadmap/site/src .
git apply ../personalized-roadmap/site/upstream.patch
npm install
PERSONAL_PATH_API=http://localhost:8000 npm start
```

Then open <http://localhost:3000/personal-path>. Adjust `../personalized-roadmap` to where this repository is.
Without a model key in `.env` the API still answers, but every path follows the course as written.
