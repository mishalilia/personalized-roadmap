# Deploying on one server

The curriculum site with the personal path page, the API and Caddy, which gets HTTPS certificates by itself,
run with Docker Compose on one Linux server.

```
learner ── https://SITE_DOMAIN ──► Caddy ──► site (nginx, the built curriculum site)
        └─ https://API_DOMAIN ───►       └─► api (uvicorn, one worker) ──► model provider
```

## Before you start

- A server with Docker and the Compose plugin, ports 80 and 443 open.
- Two DNS A records pointing at the server, for example `path.example.com` (the site) and
  `api.path.example.com` (the API). Caddy cannot get certificates until they resolve.
- This repository and the curriculum repository with the personal path page (our fork) side by side:

```bash
git clone https://github.com/mishalilia/personalized-roadmap
```

```bash
git clone <the fork of int.academy-curriculum> int.academy-curriculum
```

## Configure

```bash
cd personalized-roadmap/deploy
```

```bash
cp .env.example .env
```

Fill in `.env`: the two domains, `SITE_DIR` (the fork, relative to `deploy/`), at least one model key, and a
long random `API_REPORT_TOKEN` (`openssl rand -hex 32`). The file holds keys: keep it on the server only.

## Run

```bash
docker compose up -d --build
```

The first build takes a few minutes: it installs the site's packages and checks out every curriculum version
in `config/curriculum.yaml`. Then open `https://SITE_DOMAIN/personal-path`.

Check the API:

```bash
curl https://API_DOMAIN/health
```

See where learners who share their progress stop:

```bash
curl -H "Authorization: Bearer $API_REPORT_TOKEN" https://API_DOMAIN/report
```

## Update

After pulling changes in either repository:

```bash
docker compose up -d --build
```

Shared progress lives in the `api-state` volume and survives a rebuild. Paths live in learners' browsers, so
a rebuild loses nothing of theirs. When `config/curriculum.yaml` gains a new curriculum version, keep the old
one listed for as long as learners may still be working through paths planned for it.

## What this setup assumes

- **One API worker.** The rate limit is kept in memory. More workers would each keep their own count.
- **The API is not published.** Only Caddy reaches it, which is why uvicorn trusts the client address Caddy
  forwards; the limit then counts per learner, not per proxy. Do not publish port 8000.
- **No access log.** uvicorn runs with `--no-access-log`, and the Caddyfile has no `log` directive, so
  learners' IP addresses are not written anywhere (docs/data-sources.md promises that). Errors are still
  logged: `docker compose logs api`.
- **Python for coding problems loads from the jsDelivr CDN** in the learner's browser. To serve it from the site
  instead, copy the files of Pyodide 0.26.4 into the site's `static/pyodide/` and set `PYODIDE_URL=/pyodide/`
  in `.env` before building.
- **Model data:** learners' answers go to the model provider in `config/llm.yaml`. Before testing with real
  learners, settle Q-003's follow-up (the Gemini free tier may use requests to improve Google's products).
