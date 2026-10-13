// Drive a running Flipfix dev server (started by start.sh) with headless Chromium.
//
//   node .claude/skills/run-flipfix/driver.mjs shot /wiki/ /machines/
//       Log in as runcheck, full-page screenshot each path, report console errors.
//   node .claude/skills/run-flipfix/driver.mjs flow .claude/skills/run-flipfix/flows/wiki_images.mjs
//       Log in, then run a flow module: export default async ({ page, base, shot, manage, runDir }) => result
//   Flags (anywhere): --anon skips login (public pages); --mobile uses a 390x844 phone viewport.
//
// Env: RUN_DIR (default $TMPDIR/flipfix-run), PORT (default 8765), CHROME (browser binary override).
import fs from 'fs';
import os from 'os';
import path from 'path';
import { createRequire } from 'module';
import { execFileSync } from 'child_process';
import { fileURLToPath, pathToFileURL } from 'url';

const RUN_DIR = process.env.RUN_DIR || path.join(process.env.TMPDIR || '/tmp', 'flipfix-run');
const BASE = `http://127.0.0.1:${process.env.PORT || 8765}`;
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const SHOTS = path.join(RUN_DIR, 'shots');

// Playwright lives in RUN_DIR (installed by start.sh), not in the repo.
const { chromium } = createRequire(path.join(RUN_DIR, 'package.json'))('playwright');

/** The newest browser already in Playwright's cache, for when npm's playwright wants a newer build. */
function cachedHeadlessShell() {
  const cache = path.join(os.homedir(), '.cache/ms-playwright');
  if (!fs.existsSync(cache)) return undefined;
  const dirs = fs
    .readdirSync(cache)
    .filter((d) => d.startsWith('chromium_headless_shell-'))
    .sort();
  for (const dir of dirs.reverse()) {
    const bin = path.join(cache, dir, 'chrome-headless-shell-linux64/chrome-headless-shell');
    if (fs.existsSync(bin)) return bin;
  }
  return undefined;
}

async function launch() {
  const args = ['--no-sandbox'];
  try {
    return await chromium.launch({ args, executablePath: process.env.CHROME });
  } catch (err) {
    const fallback = cachedHeadlessShell();
    if (!fallback || process.env.CHROME) throw err;
    return chromium.launch({ args, executablePath: fallback });
  }
}

/** Run a Django management command against the isolated DB; returns stdout. */
function manage(...args) {
  return execFileSync(path.join(REPO, '.venv/bin/python'), ['manage.py', ...args], {
    cwd: REPO,
    env: {
      ...process.env,
      DATABASE_URL: `sqlite:///${RUN_DIR}/run.db`,
      DJANGO_SETTINGS_MODULE: 'flipfix.settings.dev',
    },
    stdio: ['ignore', 'pipe', 'ignore'],
  }).toString();
}

const argv = process.argv.slice(2);
const anon = argv.includes('--anon');
const mobile = argv.includes('--mobile');
const [cmd, ...rest] = argv.filter((a) => !a.startsWith('--'));
if (!['shot', 'flow'].includes(cmd) || rest.length === 0) {
  console.error('usage: driver.mjs [--anon] [--mobile] shot <path>... | flow <module.mjs>');
  process.exit(2);
}

fs.mkdirSync(SHOTS, { recursive: true });
const browser = await launch();
const viewport = mobile ? { width: 390, height: 844 } : { width: 1200, height: 900 };
const page = await (
  await browser.newContext({ viewport, isMobile: mobile, hasTouch: mobile })
).newPage();
const errors = [];
page.on('console', (m) => m.type() === 'error' && errors.push(`${page.url()}: ${m.text()}`));
page.on('pageerror', (e) => errors.push(`${page.url()}: ${e}`));

const shot = async (name) => {
  const file = path.join(SHOTS, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
};

let exitCode = 0;
try {
  if (!anon) {
    await page.goto(`${BASE}/login/`);
    await page.fill('#id_username', 'runcheck');
    await page.fill('#id_password', fs.readFileSync(path.join(RUN_DIR, 'pw'), 'utf8').trim());
    await page.click('button[type=submit]');
    await page.waitForLoadState('networkidle');
    if (page.url().includes('/login')) throw new Error('login failed - did start.sh run?');
  }

  let result;
  if (cmd === 'shot') {
    result = [];
    for (const p of rest) {
      const response = await page.goto(`${BASE}${p}`);
      await page.waitForLoadState('networkidle');
      const slug = p.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home';
      const name = mobile ? `${slug}_mobile` : slug;
      result.push({ path: p, status: response?.status(), screenshot: await shot(name) });
    }
  } else {
    const flow = await import(pathToFileURL(path.resolve(rest[0])).href);
    result = await flow.default({ page, base: BASE, shot, manage, runDir: RUN_DIR, repo: REPO });
  }
  console.log(JSON.stringify({ result, consoleErrors: errors }, null, 2));
} catch (err) {
  console.error(err);
  console.error('screenshot of failure:', await shot('failure').catch(() => 'n/a'));
  exitCode = 1;
} finally {
  await browser.close();
}
process.exit(exitCode);
