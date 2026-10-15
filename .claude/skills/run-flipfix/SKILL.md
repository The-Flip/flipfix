---
name: run-flipfix
description: Run, start, and drive the Flipfix Django web app in a headless browser. Use when asked to run Flipfix, start the dev server, take a screenshot of a page (desktop or mobile), click through a UI flow, or confirm a change works in the real app rather than just in tests.
---

Start an isolated dev server with `start.sh`, then drive it with headless Chromium via `driver.mjs`: `shot` for screenshots, `flow` for scripted interactions. Paths below are relative to the repo root.

## Prerequisites

Already true on a bootstrapped checkout (`make bootstrap`): `.venv/` with the app's dependencies, Node 22 (`.nvmrc`), `lsof`, `curl`. A Playwright Chromium in `~/.cache/ms-playwright/` is used if present (see Gotchas).

## Run (agent path)

```bash
.claude/skills/run-flipfix/start.sh --fresh                 # empty DB, ~10s (first run also npm-installs Playwright)
.claude/skills/run-flipfix/start.sh --fresh --sample-data   # with machines/problems/logs/parts, ~20s
.claude/skills/run-flipfix/start.sh                         # restart, keeping the DB
```

It serves `http://127.0.0.1:8765` from a **throwaway SQLite DB** at `$TMPDIR/flipfix-run/run.db` (with `TMPDIR` unset: `/tmp/flipfix-run`), and creates a maintainer login `runcheck` whose password is in `$RUN_DIR/pw`. The Postgres DB in `.env` (which may hold synced prod data) is never touched. Server log: `$RUN_DIR/server.log`.

```bash
node .claude/skills/run-flipfix/driver.mjs shot /machines/ /wiki/          # logged in, full-page screenshots
node .claude/skills/run-flipfix/driver.mjs --mobile shot /wiki/create/     # 390x844 phone viewport
node .claude/skills/run-flipfix/driver.mjs --anon shot /                   # not logged in
node .claude/skills/run-flipfix/driver.mjs flow .claude/skills/run-flipfix/flows/wiki_images.mjs
```

Output is JSON on stdout: per-path HTTP status and screenshot path, or the flow's return value, plus `consoleErrors` (browser console errors and uncaught exceptions). Screenshots go to `$RUN_DIR/shots/<path_slug>[_mobile].png`; on an exception the driver saves `failure.png` and exits 1. **Open the screenshots and look at them.**

A **flow** is a module that receives a logged-in Playwright `page`:

```js
// my_flow.mjs
export default async ({ page, base, shot, manage, runDir, repo }) => {
  await page.goto(`${base}/wiki/create/`);
  await page.fill('#id_title', 'Smoke');
  await page.click('button[type=submit]:has-text("Create Doc")');
  await shot('after_create'); // -> $RUN_DIR/shots/after_create.png
  const out = manage('shell', '--no-imports', '-c', 'print(1)'); // Django command on the isolated DB; returns stdout
  return { url: page.url() }; // printed as JSON
};
```

`flows/wiki_images.mjs` is a worked example covering paste, file chooser, drag and drop, toast checks, deleting a record, and running a scheduled task through `manage()`. It needs `--fresh` because it creates "Doc A" and "Doc B".

Running Django commands by hand against the same DB:

```bash
DATABASE_URL=sqlite:////tmp/flipfix-run/run.db DJANGO_SETTINGS_MODULE=flipfix.settings.dev .venv/bin/python manage.py shell --no-imports -c "..."
```

Stop the server:

```bash
lsof -ti:8765 -sTCP:LISTEN | xargs -r kill
```

Afterwards, delete any uploads your flow created under the repo's `media/` (e.g. `rm -rf media/wiki`). `media/` is gitignored but shared with the normal dev server.

## Run (human path)

`make runserver`: port 8000 against whatever `.env` says (usually the local Postgres). It runs `pkill -f "manage.py runserver"` first, which also kills the agent server on 8765.

## Test

```bash
DJANGO_SETTINGS_MODULE=flipfix.settings.test .venv/bin/python manage.py test --noinput --exclude-tag=integration   # ~2300 tests, ~50s
npx vitest run                                                                                                      # JS, ~250 tests
```

## Gotchas

- **`chromium-cli` isn't installed here, and npm's latest `playwright` wants a newer browser build than the cache holds** (`Executable doesn't exist at ~/.cache/ms-playwright/chromium_headless_shell-1248/...`). The driver catches that and falls back to the newest cached `chromium_headless_shell-*`. To pick a browser yourself, set `CHROME=/path/to/chrome-headless-shell`. With an empty cache: `cd $RUN_DIR && npx playwright install chromium-headless-shell`.
- **Playwright is installed in `$RUN_DIR`, not the repo** (no root `package.json` dependency). The driver loads it with `createRequire($RUN_DIR/package.json)`. ESM ignores `NODE_PATH`, so plain `import 'playwright'` from the skill dir fails.
- **Worker tasks call the web service over HTTP** (`core/web_service.py`), e.g. the wiki media sweep. `driver.mjs`'s `manage()` sets `DJANGO_WEB_SERVICE_URL` to this server; the token (`TRANSCODING_UPLOAD_TOKEN`) comes from `.env`. Calling such a task from a plain `manage.py shell` hits whatever `.env` says (usually port 8000).
- **`DATABASE_URL` in the environment overrides `.env`**, because python-decouple reads the environment first. That's what keeps the agent server off the dev Postgres. Any `manage.py` call that forgets the override hits Postgres.
- **`create_sample_data` refuses a DB that has any users**, so `start.sh` loads it before creating `runcheck`, and only together with `--fresh`.
- **Uploaded media always lands in the repo's `media/`** (`MEDIA_ROOT` is fixed in `settings/base.py`), even with the isolated DB.
- **Paste, drop, and file pickers can't use real OS input in headless mode.** Dispatch `new ClipboardEvent('paste', { clipboardData: dt })` or `DragEvent('drop', { dataTransfer: dt })` with a `DataTransfer` holding `File`s built from a `<canvas>`. For `<input type=file>`, use `page.waitForEvent('filechooser')` and `chooser.setFiles({ name, mimeType, buffer })`. See `flows/wiki_images.mjs`.
- **Full-page screenshots draw the sticky header partway down the page** if the page scrolled before the capture. It's a capture artifact, not a layout bug.
- **`manage.py shell -c` prints a "16 objects could not be automatically imported" banner to stdout** (Django 5.2 auto-imports). Pass `--no-imports` when you parse the output.
- **The wiki_images flow reports one console error on purpose:** the 400 from the rejected non-image upload.
- **Login form:** `/login/` with `#id_username` and `#id_password`. Maintainer access means membership of the `Maintainers` group (created by migrations); `flipfix.apps.core.test_utils.create_maintainer_user` handles that.

## Troubleshooting

- **`manage.py test` stops at "Type 'yes' if you would like to try deleting the test database":** a previous run left `test_flipfix` in Postgres. Add `--noinput`.
- **`apply-seccomp: write /proc/self/setgroups ... Permission denied` on every command:** this comes from Claude Code's bash sandbox, not the app. Rerun the command outside the sandbox.
- **Driver says `login failed - did start.sh run?`:** the server is down, or `$RUN_DIR/pw` doesn't match the DB (for example because you deleted `run.db` by hand). Rerun `start.sh --fresh`.
