#!/usr/bin/env node
/**
 * a11y_runtime_common.js — shared helpers for a11y_runtime.js and
 * a11y_stateful.js.
 *
 * Both entry points inject axe-core into Playwright-managed pages and emit
 * findings that must round-trip through the same triage schema. The code
 * below covers everything they would otherwise have duplicated:
 *
 * - Dependency bootstrap (`ensureDeps`, `ensurePlaywrightBrowser`)
 * - Axe rule constants (`AXE_TO_STATIC_RULE`, `AXE_TRIAGE_HINT`,
 *   `RUNTIME_AXE_TAGS`). `AXE_TRIAGE_HINT` is the runtime twin of
 *   `triage.py → RULE_TO_GROUP`; keep them in sync.
 * - Config helpers (`loadConfig`, `resolveAuth`, `normalizeWaitUntil`,
 *   path/secret resolution)
 * - Page helpers (`applyWaitConditions`, `applyAuth`, `applyRouteBlocking`)
 * - Result mapping helpers (`extractWcag`, `stringTarget`, `countAxeNodes`,
 *   `addScreenshot`, `formatError`).
 *
 * This module is not a CLI. It is `require()`d by sibling scripts.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const { execSync } = require('child_process');

const DEP_CACHE_DIR = path.join(__dirname, '..', '.a11y-audit-deps');
const BROWSERS_DIR = path.join(DEP_CACHE_DIR, 'ms-playwright');

// A `require` bound to the cache dir's package.json. Node resolves packages
// relative to the file that owns the `require`, so mutating `module.paths`
// inside this common module would not help the caller modules reach
// `.a11y-audit-deps/node_modules`. Exporting a cache-bound require guarantees
// every runtime resolves against the same location, no matter which entry
// script called `ensureDeps()`.
const requireFromCache = createRequire(path.join(DEP_CACHE_DIR, 'package.json'));

const AXE_TO_STATIC_RULE = {
  'image-alt': 'img-missing-alt',
  'label': 'input-missing-label',
  'html-has-lang': 'html-missing-lang',
  'aria-hidden-focus': 'aria-hidden-focusable',
  'link-in-text-block': 'link-in-text-block',
  'duplicate-id': 'duplicate-id',
  'tabindex': 'positive-tabindex',
};

const AXE_TRIAGE_HINT = {
  'image-alt': 'input',
  'label': 'input',
  'color-contrast': 'input',
  // `html-has-lang` and `duplicate-id` were demoted from auto to input:
  // locale inference is unreliable, and renaming an id can break selectors
  // and ARIA references. See triage.py RULE_TO_GROUP for the source of truth.
  'html-has-lang': 'input',
  'duplicate-id': 'input',
  'aria-hidden-focus': 'auto',
  'tabindex': 'input',
  'region': 'manual',
  'landmark-one-main': 'manual',
  'page-has-heading-one': 'manual',
  'heading-order': 'input',
  'focus-order-semantics': 'manual',
};

const RUNTIME_AXE_TAGS = [
  'wcag2a', 'wcag2aa',
  'wcag21a', 'wcag21aa',
  'wcag22a', 'wcag22aa',
  'best-practice',
];

function ensureDepCache() {
  if (!fs.existsSync(DEP_CACHE_DIR)) {
    fs.mkdirSync(DEP_CACHE_DIR, { recursive: true });
  }
  const packageJsonPath = path.join(DEP_CACHE_DIR, 'package.json');
  if (!fs.existsSync(packageJsonPath)) {
    fs.writeFileSync(
      packageJsonPath,
      JSON.stringify({ name: 'a11y-audit-deps', version: '1.0.0', private: true }, null, 2)
    );
  }
}

function ensureDeps(required) {
  ensureDepCache();

  const missing = [];
  for (const dep of required) {
    try {
      requireFromCache.resolve(dep);
    } catch {
      missing.push(dep);
    }
  }
  if (missing.length === 0) {
    return;
  }

  console.error(`Installing required packages: ${missing.join(', ')}...`);
  execSync(`npm install --no-audit --no-fund --loglevel=error ${missing.join(' ')}`, {
    cwd: DEP_CACHE_DIR,
    stdio: 'inherit',
    env: {
      ...process.env,
      PLAYWRIGHT_BROWSERS_PATH: BROWSERS_DIR,
    },
  });
}

function ensurePlaywrightBrowser(playwright) {
  process.env.PLAYWRIGHT_BROWSERS_PATH = BROWSERS_DIR;
  const executablePath = playwright.chromium.executablePath();
  if (fs.existsSync(executablePath)) {
    return;
  }

  const cliPath = path.join(DEP_CACHE_DIR, 'node_modules', '.bin', 'playwright');
  if (!fs.existsSync(cliPath)) {
    throw new Error('Playwright is installed but the CLI helper is missing.');
  }

  console.error('Installing Playwright Chromium browser...');
  execSync(`${JSON.stringify(cliPath)} install chromium`, {
    cwd: DEP_CACHE_DIR,
    stdio: 'inherit',
    env: {
      ...process.env,
      PLAYWRIGHT_BROWSERS_PATH: BROWSERS_DIR,
    },
  });
}

function normalizeWaitUntil(value) {
  const normalized = String(value || 'networkidle').toLowerCase();
  if (normalized === 'networkidle2') {
    return 'networkidle';
  }
  if (!['load', 'domcontentloaded', 'networkidle', 'commit'].includes(normalized)) {
    throw new Error(`Unsupported wait condition "${value}". Use load, domcontentloaded, networkidle, or commit.`);
  }
  return normalized;
}

function resolvePath(baseDir, value) {
  if (!value) {
    return '';
  }
  return path.isAbsolute(value) ? value : path.resolve(baseDir, value);
}

function loadConfig(configPath, { required = false, kind = 'config' } = {}) {
  const label = kind === 'journey' ? 'Journey' : 'Runtime';

  // Explicit empty-string (`--config ''`) is a user error, not an absence.
  // Silently treating it as "no config" masks typos in invocation scripts;
  // surface it so the caller sees the mistake.
  if (configPath === '') {
    throw new Error(`${label} config path is empty. Pass a JSON or YAML file with --config.`);
  }
  if (configPath == null) {
    if (required) {
      throw new Error(`Provide --config with a JSON or YAML ${kind} file.`);
    }
    return { config: {}, baseDir: process.cwd() };
  }

  const absolutePath = path.resolve(process.cwd(), configPath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`${label} config file not found: ${configPath}`);
  }

  const extension = path.extname(absolutePath).toLowerCase();
  const raw = fs.readFileSync(absolutePath, 'utf-8');
  if (extension === '.json') {
    try {
      return { config: JSON.parse(raw), baseDir: path.dirname(absolutePath) };
    } catch (err) {
      throw new Error(`${label} config file ${configPath} is not valid JSON: ${err.message}`);
    }
  }
  if (extension === '.yaml' || extension === '.yml') {
    ensureDeps(['yaml']);
    const yaml = requireFromCache('yaml');
    try {
      return { config: yaml.parse(raw) || {}, baseDir: path.dirname(absolutePath) };
    } catch (err) {
      throw new Error(`${label} config file ${configPath} is not valid YAML: ${err.message}`);
    }
  }
  throw new Error(`${label} config files must use .json, .yaml, or .yml.`);
}

function resolveSecretValue(spec, label, baseDir) {
  if (spec == null) {
    throw new Error(`Missing value for ${label}.`);
  }
  if (typeof spec === 'string') {
    if (spec.startsWith('env:')) {
      const envName = spec.slice(4).trim();
      const value = process.env[envName];
      if (!value) {
        throw new Error(`Missing environment variable referenced by ${label}: ${envName}.`);
      }
      return value;
    }
    if (spec.startsWith('file:')) {
      const secretPath = resolvePath(baseDir, spec.slice(5).trim());
      if (!fs.existsSync(secretPath)) {
        throw new Error(`Missing secret file referenced by ${label}: ${path.basename(secretPath)}.`);
      }
      return fs.readFileSync(secretPath, 'utf-8').trim();
    }
    return spec;
  }
  if (typeof spec === 'object' && !Array.isArray(spec)) {
    if (spec.env) {
      return resolveSecretValue(`env:${spec.env}`, label, baseDir);
    }
    if (spec.file) {
      return resolveSecretValue(`file:${spec.file}`, label, baseDir);
    }
    if (Object.prototype.hasOwnProperty.call(spec, 'value')) {
      return String(spec.value);
    }
  }
  throw new Error(`Unsupported secret reference for ${label}. Use env:, file:, or { env/file/value }.`);
}

function resolveAuth(authConfig, baseDir) {
  if (!authConfig) {
    return { mode: 'none' };
  }

  const mode = String(authConfig.mode || '').trim();
  if (!mode) {
    throw new Error('Auth config requires a non-empty mode.');
  }

  if (mode === 'storage_state') {
    const storageStatePath = resolvePath(baseDir, authConfig.storage_state_path || '');
    if (!storageStatePath || !fs.existsSync(storageStatePath)) {
      throw new Error(
        'Auth config mode "storage_state" requires an existing storage_state_path. ' +
        'Refresh or provide the Playwright auth state file.'
      );
    }
    return { mode, storageStatePath };
  }

  if (mode === 'headers') {
    const headers = {};
    const source = authConfig.headers || {};
    for (const [headerName, valueSpec] of Object.entries(source)) {
      headers[headerName] = resolveSecretValue(valueSpec, `auth.headers.${headerName}`, baseDir);
    }
    if (Object.keys(headers).length === 0) {
      throw new Error('Auth config mode "headers" requires a non-empty headers object.');
    }
    return { mode, headers };
  }

  if (mode === 'cookies') {
    const cookiesPath = resolvePath(baseDir, authConfig.cookies_path || '');
    if (!cookiesPath || !fs.existsSync(cookiesPath)) {
      throw new Error('Auth config mode "cookies" requires an existing cookies_path JSON file.');
    }
    const cookies = JSON.parse(fs.readFileSync(cookiesPath, 'utf-8'));
    if (!Array.isArray(cookies)) {
      throw new Error('Auth cookies file must contain a JSON array of Playwright cookies.');
    }
    return { mode, cookies };
  }

  throw new Error(`Unsupported auth mode "${mode}". Use storage_state, headers, or cookies.`);
}

function extractWcag(tags) {
  for (const tag of tags || []) {
    if (!/^wcag\d{3,}$/.test(tag)) {
      continue;
    }
    const digits = tag.replace('wcag', '');
    return `${digits[0]}.${digits[1]}.${digits.slice(2)}`;
  }

  return (tags || [])
    .filter((tag) => /^wcag\d/.test(tag))
    .map((tag) => tag.replace('wcag', ''))
    .find((tag) => /^\d/.test(tag)) || '';
}

function stringTarget(target) {
  return Array.isArray(target) ? target.join(' > ') : String(target || '');
}

function countAxeNodes(results) {
  return (results || []).reduce((sum, item) => sum + ((item.nodes || []).length), 0);
}

function addScreenshot(issue, screenshotPath) {
  if (!screenshotPath) {
    return issue;
  }
  issue.fix_data.screenshot = screenshotPath;
  return issue;
}

async function applyWaitConditions(page, config) {
  const waitFor = config.wait_for || {};
  const timeout = config.timeout;
  if (waitFor.selector) {
    await page.waitForSelector(waitFor.selector, { state: 'visible', timeout });
  }
  if (waitFor.hidden_selector) {
    await page.waitForSelector(waitFor.hidden_selector, { state: 'hidden', timeout });
  }
  if (waitFor.load_state) {
    await page.waitForLoadState(normalizeWaitUntil(waitFor.load_state), { timeout });
  }
  if (waitFor.timeout_ms) {
    await page.waitForTimeout(parseInt(waitFor.timeout_ms, 10));
  }
}

async function applyAuth(context, auth) {
  if (auth.mode === 'headers') {
    await context.setExtraHTTPHeaders(auth.headers);
  } else if (auth.mode === 'cookies') {
    await context.addCookies(auth.cookies);
  }
}

async function applyRouteBlocking(page, routeBlocklist) {
  for (const pattern of routeBlocklist || []) {
    await page.route(pattern, (route) => route.abort());
  }
}

function formatError(err) {
  return err && err.message ? err.message : String(err);
}

module.exports = {
  DEP_CACHE_DIR,
  BROWSERS_DIR,
  AXE_TO_STATIC_RULE,
  AXE_TRIAGE_HINT,
  RUNTIME_AXE_TAGS,
  requireFromCache,
  ensureDepCache,
  ensureDeps,
  ensurePlaywrightBrowser,
  normalizeWaitUntil,
  resolvePath,
  loadConfig,
  resolveSecretValue,
  resolveAuth,
  extractWcag,
  stringTarget,
  countAxeNodes,
  addScreenshot,
  applyWaitConditions,
  applyAuth,
  applyRouteBlocking,
  formatError,
};
