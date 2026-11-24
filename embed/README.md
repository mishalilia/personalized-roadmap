# DotPath on any website: the script tag

DotPath runs on a school's own website from one line in its page template:

```html
<script src="https://api.polarislearning.me/embed/dotpath.js" data-site="https://dotpath.polarislearning.me" defer></script>
```

On every page the line adds the path panel, the assistant's button and sign-in. On a lesson page it also adds the
module's status above the lesson and its checkpoint below it.

Live example since 24 November 2026: a demo school, https://school.polarislearning.me (a plain HTML site with its
own look, made from the course's lessons by `school/build_school.py`).

These are the same React components as on the course site (`site/src/components/personal-path`). Only the
Docusaurus parts are replaced (`src/shims/docusaurus.tsx`). The widget lives in shadow roots, so the school's
styles do not affect DotPath and DotPath's styles do not affect the school.

## How it works

```
school's page ──<script dotpath.js>──► reads data-* from its own tag
   │                                      │
   │ GET /embed/site (Origin: school) ◄───┘  where each module's lesson lives on this site,
   │                                         the CSS selector of the lesson, and the site's look
   ├─ <div id="dotpath"> shadow root: PathDrawer, AskButton, AuthDialog
   ├─ before the lesson: shadow root with ModulePanel   (status, topics)
   └─ after the lesson:  shadow root with ModuleFinish  (checkpoint, coding problem, project)
```

- **Session.** Browsers block or partition third-party cookies, so the widget does not rely on the cookie. It
  sends `X-DotPath-Embed: 1`; on sign-in and sign-up the API then returns a `token`, which the widget keeps in the
  school's `localStorage` (`dotpath.session`) and sends as `Authorization: Bearer …`. The course site never gets
  the token, and its answers keep their old shape.
- **Google.** In a separate window: `/auth/google` → Google → `/embed/signed-in?origin=…`. That page creates a
  session and passes it with `postMessage` only to the school's origin, then closes. Only origins in
  `API_ALLOWED_ORIGINS` are accepted.
- **Which school, which pages.** The school's origin must be in `API_ALLOWED_ORIGINS`. The page map is in
  `API_EMBED_SITES_FILE`: `{origin: {versions: [{name, label, docs: [{id, path}]}], content, designers}}`. An
  engineer writes it when converting the course.
- **Styles.** The components' styles and `src/base.css` (the Infima variables they rely on) go into the bundle
  and are attached to each shadow root. The fonts are linked in the page's `<head>`, because fonts cannot be
  declared inside a shadow root.
- **Single-page school sites.** The widget follows `history.pushState` and `replaceState` and puts the lesson
  blocks back after each navigation.

## The panel's look

A school's designer signs in on the school's site; the account menu then offers **Panel design** (a link with
`#dotpath-design` opens it too). Every change shows at once on the real page.

| Setting | Choices |
|---|---|
| Theme | Dark (DotPath's) or light |
| Accent colour | Eight swatches or any colour; a warning when text in it is hard to read, or when it is close to the blue of modules to prove |
| Font | DotPath's, the site's own, system, serif |
| Corners | Sharp, soft (DotPath's), round |
| Logo on the assistant's button | An image address, or DotPath's star |

- **Who may change it:** the emails in the site's `designers` list in the sites file. The list is never sent to
  browsers and does not depend on `API_REVIEWER_EMAILS`.
- **Where it is kept:** `API_EMBED_THEMES_FILE` (by default `embed-themes.json` in the uploads folder), by site
  address. Every visitor of that site gets it with `GET /embed/site`.
- **What a look can carry:** only these fields, each checked by the API. A school cannot put its own CSS into the
  widget this way.
- **How the components follow it:** `themable.mjs` rewrites the components' stylesheets while building the
  bundle only; every rewritten value falls back to the original, so the default look and the course site are
  unchanged.

## Files

| File | What it is |
|---|---|
| `src/main.tsx` | Entry point: shadow roots, token, lesson blocks, navigation, the design window |
| `src/config.ts` | Reads `data-api`, `data-site`, `data-content`, `data-logo` and `data-pyodide` from the tag |
| `src/site.ts` | The school's page map from `/embed/site` |
| `src/shims/docusaurus.tsx` | `Link`, `useBaseUrl`, `useLocation`, `useDoc` and the others, without Docusaurus |
| `src/base.css` | The basic theme styles inside the shadow roots |
| `src/theme.ts`, `src/Designer.tsx` | The look and the design window |
| `themable.mjs` | Makes the components' styles follow a look, at build time |
| `build.mjs` | Builds `dist/dotpath.js` with the curriculum site's own esbuild, React and icons |
| `school/build_school.py`, `school/school.css` | The demo school: 20 lessons from the course's MDX, and the page map |
| `school/sites.json` | The page map for the demo school run locally (`http://127.0.0.1:5050`) |

The API side is in `src/roadmap/api.py` (`/embed/*`), with tests in `tests/test_embed.py` and
`tests/test_embed_theme.py`.

## Build and run locally

The bundle is built from a checkout of the curriculum site with this repository's `site/src` copied in and its
packages installed (see [site/README.md](../site/README.md)):

```bash
node embed/build.mjs --site ../int.academy-curriculum      # writes embed/dist/dotpath.js
PYTHONPATH=src python embed/school/build_school.py --docs ../int.academy-curriculum/docs
API_EMBED_DIR=embed/dist API_EMBED_SITES_FILE=embed/school/sites.json \
API_ALLOWED_ORIGINS=http://127.0.0.1:5050 API_COOKIE_SECURE=false uvicorn roadmap.api:app --app-dir src --port 8030
cd embed/school/public && python -m http.server 5050 --bind 127.0.0.1
```

`build_school.py` takes `--api`, `--site`, `--origin`, `--out` and `--designers` for other addresses.

## On the server

The bundle and the sites file live in `/opt/dotpath/embed`, mounted read-only into the API container, and the
demo school is a small nginx container behind the same Traefik. The server's `deploy/compose.override.yml` sets:

```yaml
api:
  environment:
    API_ALLOWED_ORIGINS: https://${SITE_DOMAIN},https://school.polarislearning.me
    API_EMBED_DIR: /embed
    API_EMBED_SITES_FILE: /embed/sites.json
  volumes:
    - /opt/dotpath/embed:/embed:ro
```

Connecting a new school: convert its course into a page map, add its origin to `API_ALLOWED_ORIGINS` and the map
(with its designers) to the sites file, and give the school the line above.

## Limitations

- **The token lives in the school's `localStorage`.** An XSS hole on the school's site could steal it; that is
  the usual trade-off for widgets.
- **Looks are kept in a JSON file, not in PostgreSQL.** Enough for a few schools and one API process.
- **Not tested end to end:** Google sign-in in the popup (covered by tests with a fake Google) and downloading a
  submitted project's archive from the widget.
- **The demo school's lessons come from MDX through a simple script.** A real school's course needs its own page
  map and checkpoints: the conversion by an engineer that the business plan prices in.
