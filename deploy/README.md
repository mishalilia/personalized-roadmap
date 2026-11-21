# Deploying on one server

The curriculum site with the personal path page, the API, its PostgreSQL database and Caddy, which gets HTTPS
certificates by itself, run with Docker Compose on one Linux server.

```
learner ── https://SITE_DOMAIN ──► Caddy ──► site (nginx, the built curriculum site)
        └─ https://API_DOMAIN ───►       └─► api (uvicorn, one worker) ──► model provider
                                                    └──► db (PostgreSQL 16)
```

## Before you start

- A server with Docker and the Compose plugin, ports 80 and 443 open.
- Two DNS A records pointing at the server, for example `path.example.com` (the site) and
  `api.path.example.com` (the API). Caddy cannot get certificates until they resolve.
- This repository and the curriculum repository side by side, with the personal path page added to the
  curriculum site from `site/` ([site/README.md](../site/README.md)):

```bash
git clone https://github.com/mishalilia/personalized-roadmap
```

```bash
git clone https://github.com/humblebeeai/int.academy-curriculum
```

```bash
cd int.academy-curriculum && git checkout 9fc5573 && cp -r ../personalized-roadmap/site/src . && git apply ../personalized-roadmap/site/upstream.patch && cd ..
```

## Configure

```bash
cd personalized-roadmap/deploy
```

```bash
cp .env.example .env
```

Fill in `.env`: the two domains; optionally a Google OAuth client for sign-in with Google (its redirect URI is
`https://API_DOMAIN/auth/google/callback`); `SITE_DIR` (the curriculum site with the page, relative to `deploy/`); at least one model key
(`LLM_API_KEY_OPENAI` for the default model); a long random `API_REPORT_TOKEN` (`openssl rand -hex 32`) and
`POSTGRES_PASSWORD` (`openssl rand -hex 24`). The file holds keys: keep it on the server only.

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

Accounts, learners' paths, submitted projects and shared progress live in PostgreSQL, in the `db-data` volume;
the archives of submitted projects in the `api-state` volume. Both survive a rebuild. Back them up: they are the
only copy of learners' progress. A dump of the database, for example nightly from cron:

```bash
docker compose exec -T db pg_dump -U roadmap roadmap | gzip > roadmap-$(date +%F).sql.gz
```

Restore one into an empty database:

```bash
gunzip -c roadmap-2027-01-15.sql.gz | docker compose exec -T db psql -U roadmap roadmap
```
 When `config/curriculum.yaml` gains a new curriculum version, keep the old
one listed for as long as learners may still be working through paths planned for it.

## What this setup assumes

- **The site and the API under one domain**, such as `path.example.com` and `api.path.example.com`. The
  session cookie is `SameSite=Lax`, so browsers send it only between pages of the same site.
- **One API worker.** The rate limit is kept in memory. More workers would each keep their own count. The
  database is not what holds this back: PostgreSQL serves several API processes, and a learner's path is
  locked in the database while one request changes it.
- **The database is not published.** Only the API reaches PostgreSQL, on the compose network.
- **The API is not published.** Only Caddy reaches it, which is why uvicorn trusts the client address Caddy
  forwards; the limit then counts per learner, not per proxy. Do not publish port 8000.
- **No access log.** uvicorn runs with `--no-access-log`, and the Caddyfile has no `log` directive, so
  learners' IP addresses are not written anywhere (docs/data-sources.md promises that). Errors are still
  logged: `docker compose logs api`.
- **Python for coding problems loads from the jsDelivr CDN** in the learner's browser. To serve it from the site
  instead, copy the files of Pyodide 0.26.4 into the site's `static/pyodide/` and set `PYODIDE_URL=/pyodide/`
  in `.env` before building.
- **Model data:** learners' answers go to the model provider in `config/llm.yaml`, OpenAI by default (Q-003).
