#!/usr/bin/env node
/**
 * a11y_runtime.js — runtime accessibility scanner using Playwright + axe-core.
 *
 * Loads one or more target URLs in headless Chromium, injects axe-core, runs
 * the WCAG 2.2 AA rule set, and emits JSON findings aligned with the static
 * scanner's format.
 *
 * The script auto-installs `playwright`, `axe-core`, and `yaml` on first use
 * into a local `.a11y-audit-deps` cache directory.
 *
 * Usage:
 *   node a11y_runtime.js --url http://localhost:3000 --output results.json
 *   node a11y_runtime.js --urls url1,url2 --config runtime.config.json --output results.json
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DEP_CACHE_DIR = path.join(__dirname, '..', '.a11y-audit-deps');
const BROWSERS_DIR = path.join(DEP_CACHE_DIR, 'ms-playwright');

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
  const nodeModulesDir = path.join(DEP_CACHE_DIR, 'node_modules');
  if (!module.paths.includes(nodeModulesDir)) {
    module.paths.unshift(nodeModulesDir);
  }
}

function ensureDeps(required) {
  ensureDepCache();

  const missing = [];
  for (const dep of required) {
    try {
      require.resolve(dep);
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
  const nodeModulesDir = path.join(DEP_CACHE_DIR, 'node_modules');
  if (!module.paths.includes(nodeModulesDir)) {
    module.paths.unshift(nodeModulesDir);
  }
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

function parseViewport(value) {
  const match = /^(\d+)x(\d+)$/i.exec(value || '');
  if (!match) {
    throw new Error(`Invalid viewport value "${value}". Use WIDTHxHEIGHT, e.g. 1280x800.`);
  }
  return { width: parseInt(match[1], 10), height: parseInt(match[2], 10) };
}

function normalizeWaitUntil(value) {
  const normalized = (value || 'networkidle').toLowerCase();
  if (normalized === 'networkidle2') {
    return 'networkidle';
  }
  if (!['load', 'domcontentloaded', 'networkidle', 'commit'].includes(normalized)) {
    throw new Error(`Unsupported wait condition "${value}". Use load, domcontentloaded, networkidle, or commit.`);
  }
  return normalized;
}

function parseArgs(argv) {
  const args = {
    urls: [],
    output: null,
    config: null,
    waitUntil: 'networkidle',
    timeout: 30000,
    waitForSelector: '',
    waitForHiddenSelector: '',
    screenshotDir: '',
    viewport: { width: 1280, height: 800 },
    reducedMotion: 'no-preference',
    routeBlocklist: [],
    validateConfigOnly: false,
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--url') {
      args.urls.push(argv[++i]);
    } else if (arg === '--urls') {
      args.urls.push(...argv[++i].split(',').map((item) => item.trim()).filter(Boolean));
    } else if (arg === '--output') {
      args.output = argv[++i];
    } else if (arg === '--config') {
      args.config = argv[++i];
    } else if (arg === '--wait-for' || arg === '--wait-until') {
      args.waitUntil = argv[++i];
    } else if (arg === '--wait-for-selector') {
      args.waitForSelector = argv[++i];
    } else if (arg === '--wait-for-hidden-selector') {
      args.waitForHiddenSelector = argv[++i];
    } else if (arg === '--timeout') {
      args.timeout = parseInt(argv[++i], 10);
    } else if (arg === '--screenshot-dir') {
      args.screenshotDir = argv[++i];
    } else if (arg === '--viewport') {
      args.viewport = parseViewport(argv[++i]);
    } else if (arg === '--reduced-motion') {
      args.reducedMotion = argv[++i];
    } else if (arg === '--block-route') {
      args.routeBlocklist.push(argv[++i]);
    } else if (arg === '--validate-config-only') {
      args.validateConfigOnly = true;
    } else if (arg === '--help' || arg === '-h') {
      console.log(
        'Usage: node a11y_runtime.js --url <url> [--output results.json] ' +
        '[--config runtime.config.json] [--screenshot-dir dir]'
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return args;
}

function resolvePath(baseDir, value) {
  if (!value) {
    return '';
  }
  return path.isAbsolute(value) ? value : path.resolve(baseDir, value);
}

function loadConfig(configPath) {
  if (!configPath) {
    return { config: {}, baseDir: process.cwd() };
  }

  const absolutePath = path.resolve(process.cwd(), configPath);
  if (!fs.existsSync(absolutePath)) {
    throw new Error(`Runtime config file not found: ${configPath}`);
  }

  const extension = path.extname(absolutePath).toLowerCase();
  const raw = fs.readFileSync(absolutePath, 'utf-8');
  if (extension === '.json') {
    return { config: JSON.parse(raw), baseDir: path.dirname(absolutePath) };
  }
  if (extension === '.yaml' || extension === '.yml') {
    ensureDeps(['yaml']);
    const yaml = require('yaml');
    return { config: yaml.parse(raw) || {}, baseDir: path.dirname(absolutePath) };
  }
  throw new Error('Runtime config files must use .json, .yaml, or .yml.');
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
      throw new Error(
        'Auth config mode "cookies" requires an existing cookies_path JSON file.'
      );
    }
    const cookies = JSON.parse(fs.readFileSync(cookiesPath, 'utf-8'));
    if (!Array.isArray(cookies)) {
      throw new Error('Auth cookies file must contain a JSON array of Playwright cookies.');
    }
    return { mode, cookies };
  }

  throw new Error(`Unsupported auth mode "${mode}". Use storage_state, headers, or cookies.`);
}

function mergePageConfig(baseConfig, overrideConfig) {
  return {
    ...baseConfig,
    ...overrideConfig,
    viewport: { ...(baseConfig.viewport || {}), ...(overrideConfig.viewport || {}) },
    wait_for: { ...(baseConfig.wait_for || {}), ...(overrideConfig.wait_for || {}) },
    route_blocklist: overrideConfig.route_blocklist || baseConfig.route_blocklist || [],
  };
}

function buildPagePlans(args, config, configBaseDir) {
  const defaultPageConfig = {
    wait_until: normalizeWaitUntil(args.waitUntil),
    timeout: args.timeout,
    wait_for: {
      selector: args.waitForSelector,
      hidden_selector: args.waitForHiddenSelector,
    },
    route_blocklist: args.routeBlocklist,
    viewport: args.viewport,
    reduced_motion: args.reducedMotion,
    screenshot: Boolean(args.screenshotDir),
    screenshot_dir: args.screenshotDir ? resolvePath(process.cwd(), args.screenshotDir) : '',
  };

  const configuredDefaults = mergePageConfig(defaultPageConfig, config.defaults || {});
  if (configuredDefaults.wait_until) {
    configuredDefaults.wait_until = normalizeWaitUntil(configuredDefaults.wait_until);
  }
  if (configuredDefaults.viewport && (
    typeof configuredDefaults.viewport.width !== 'number' ||
    typeof configuredDefaults.viewport.height !== 'number'
  )) {
    throw new Error('Viewport config requires numeric width and height.');
  }
  if (!['reduce', 'no-preference'].includes(configuredDefaults.reduced_motion || 'no-preference')) {
    throw new Error('reduced_motion must be "reduce" or "no-preference".');
  }
  if (configuredDefaults.screenshot_dir) {
    configuredDefaults.screenshot_dir = resolvePath(configBaseDir, configuredDefaults.screenshot_dir);
  }

  const pagePlans = [];
  const seenUrls = new Set();

  for (const pageConfig of config.pages || []) {
    const merged = mergePageConfig(configuredDefaults, pageConfig || {});
    if (!merged.url) {
      throw new Error('Each runtime page config requires a url.');
    }
    merged.url = String(merged.url);
    merged.wait_until = normalizeWaitUntil(merged.wait_until);
    merged.timeout = parseInt(merged.timeout, 10);
    if (!Number.isFinite(merged.timeout) || merged.timeout <= 0) {
      throw new Error(`Invalid timeout for ${merged.url}.`);
    }
    if (merged.screenshot_dir) {
      merged.screenshot_dir = resolvePath(configBaseDir, merged.screenshot_dir);
    }
    pagePlans.push(merged);
    seenUrls.add(merged.url);
  }

  for (const url of args.urls) {
    if (seenUrls.has(url)) {
      continue;
    }
    pagePlans.push({ ...configuredDefaults, url });
  }

  if (pagePlans.length === 0) {
    throw new Error('Provide at least one URL via --url/--urls or config.pages[].url.');
  }

  return pagePlans;
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

function addScreenshot(issue, screenshotPath) {
  if (!screenshotPath) {
    return issue;
  }
  issue.fix_data.screenshot = screenshotPath;
  return issue;
}

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
  'html-has-lang': 'auto',
  'aria-hidden-focus': 'auto',
  'duplicate-id': 'auto',
  'tabindex': 'input',
  'region': 'manual',
  'landmark-one-main': 'manual',
  'page-has-heading-one': 'manual',
  'heading-order': 'input',
  'focus-order-semantics': 'manual',
};

function countAxeNodes(results) {
  return (results || []).reduce((sum, item) => sum + ((item.nodes || []).length), 0);
}

function mapAxeResult(result, pageUrl, screenshotPath) {
  const issues = [];

  for (const violation of result.violations || []) {
    for (const node of violation.nodes || []) {
      issues.push(addScreenshot({
        rule_id: AXE_TO_STATIC_RULE[violation.id] || violation.id,
        origin_rule_id: violation.id,
        wcag: extractWcag(violation.tags),
        file: pageUrl,
        line: 0,
        col: 0,
        snippet: (node.html || '').slice(0, 300),
        message: violation.help,
        framework: 'runtime',
        triage_hint: AXE_TRIAGE_HINT[violation.id] || (
          violation.impact === 'critical' || violation.impact === 'serious' ? 'auto' : 'input'
        ),
        fix_data: {
          axe_rule: violation.id,
          impact: violation.impact || 'unknown',
          target: stringTarget(node.target),
          help_url: violation.helpUrl || '',
          failure_summary: node.failureSummary || '',
          result_type: 'violation',
        },
      }, screenshotPath));
    }
  }

  for (const incomplete of result.incomplete || []) {
    for (const node of incomplete.nodes || []) {
      issues.push(addScreenshot({
        rule_id: AXE_TO_STATIC_RULE[incomplete.id] || incomplete.id,
        origin_rule_id: incomplete.id,
        wcag: extractWcag(incomplete.tags),
        file: pageUrl,
        line: 0,
        col: 0,
        snippet: (node.html || '').slice(0, 300),
        message: `${incomplete.help} (needs manual verification)`,
        framework: 'runtime',
        triage_hint: 'input',
        fix_data: {
          axe_rule: incomplete.id,
          impact: incomplete.impact || 'unknown',
          target: stringTarget(node.target),
          help_url: incomplete.helpUrl || '',
          failure_summary: node.failureSummary || '',
          result_type: 'incomplete',
        },
      }, screenshotPath));
    }
  }

  return issues;
}

function mapAxePasses(result, pageUrl) {
  return (result.passes || []).map((pass) => ({
    rule_id: AXE_TO_STATIC_RULE[pass.id] || pass.id,
    origin_rule_id: pass.id,
    wcag: extractWcag(pass.tags),
    url: pageUrl,
    node_count: (pass.nodes || []).length,
  }));
}

function slugifyUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    if (parsed.protocol === 'file:') {
      const base = path.basename(parsed.pathname).replace(path.extname(parsed.pathname), '');
      return base || 'page';
    }
    const joined = `${parsed.hostname}${parsed.pathname}`.replace(/[^\w.-]+/g, '-');
    return joined.replace(/-+/g, '-').replace(/^-|-$/g, '') || 'page';
  } catch {
    return String(rawUrl).replace(/[^\w.-]+/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '') || 'page';
  }
}

async function maybeCaptureScreenshot(page, pagePlan, issueCount) {
  if (!pagePlan.screenshot_dir || !issueCount) {
    return '';
  }
  fs.mkdirSync(pagePlan.screenshot_dir, { recursive: true });
  const screenshotPath = path.resolve(pagePlan.screenshot_dir, `${slugifyUrl(pagePlan.url)}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
  return screenshotPath;
}

async function applyWaitConditions(page, pagePlan) {
  const waitFor = pagePlan.wait_for || {};
  const timeout = pagePlan.timeout;
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

async function scanPage(browser, pagePlan, auth, axeSource) {
  const contextOptions = {
    viewport: pagePlan.viewport || { width: 1280, height: 800 },
    reducedMotion: pagePlan.reduced_motion || 'no-preference',
  };
  if (auth.mode === 'storage_state') {
    contextOptions.storageState = auth.storageStatePath;
  }

  const context = await browser.newContext(contextOptions);
  try {
    await applyAuth(context, auth);
    const page = await context.newPage();
    await applyRouteBlocking(page, pagePlan.route_blocklist);

    const response = await page.goto(pagePlan.url, {
      waitUntil: pagePlan.wait_until,
      timeout: pagePlan.timeout,
    });
    if (
      auth.mode !== 'none' &&
      response &&
      (response.status() === 401 || response.status() === 403)
    ) {
      throw new Error(
        `Authenticated request failed with HTTP ${response.status()}. ` +
        'Check the auth config or refresh the stored state.'
      );
    }

    await applyWaitConditions(page, pagePlan);
    await page.addScriptTag({ content: axeSource });
    const result = await page.evaluate(async () => {
      /* global axe */
      return axe.run(document, {
        runOnly: {
          type: 'tag',
          values: [
            'wcag2a', 'wcag2aa',
            'wcag21a', 'wcag21aa',
            'wcag22a', 'wcag22aa',
            'best-practice',
          ],
        },
        resultTypes: ['violations', 'incomplete', 'passes'],
      });
    });

    const issueCount = countAxeNodes(result.violations) + countAxeNodes(result.incomplete);
    const screenshotPath = await maybeCaptureScreenshot(page, pagePlan, issueCount);
    return {
      issues: mapAxeResult(result, pagePlan.url, screenshotPath),
      passes: mapAxePasses(result, pagePlan.url),
      counts: {
        issues: issueCount,
        violations: countAxeNodes(result.violations),
        incomplete: countAxeNodes(result.incomplete),
        passes: (result.passes || []).length,
      },
    };
  } finally {
    await context.close();
  }
}

function formatError(err) {
  return err && err.message ? err.message : String(err);
}

async function main() {
  const args = parseArgs(process.argv);
  const { config, baseDir: configBaseDir } = loadConfig(args.config);
  const auth = resolveAuth(config.auth, configBaseDir);
  const pagePlans = buildPagePlans(args, config, configBaseDir);

  if (args.validateConfigOnly) {
    console.error(`Validated runtime config for ${pagePlans.length} page(s).`);
    return;
  }

  ensureDeps(['playwright', 'axe-core']);
  const playwright = require('playwright');
  ensurePlaywrightBrowser(playwright);
  const axeSource = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf-8');

  const browser = await playwright.chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const allIssues = [];
  const allPasses = [];
  const perUrlCounts = {};
  const perUrlResultCounts = {};
  try {
    for (const pagePlan of pagePlans) {
      console.error(`Scanning: ${pagePlan.url}`);
      try {
        const scan = await scanPage(browser, pagePlan, auth, axeSource);
        perUrlCounts[pagePlan.url] = scan.issues.length;
        perUrlResultCounts[pagePlan.url] = scan.counts;
        allIssues.push(...scan.issues);
        allPasses.push(...scan.passes);
      } catch (err) {
        const message = formatError(err);
        console.error(`  Failed: ${message}`);
        perUrlCounts[pagePlan.url] = `error: ${message}`;
        perUrlResultCounts[pagePlan.url] = {
          issues: 0,
          violations: 0,
          incomplete: 0,
          passes: 0,
        };
      }
    }
  } finally {
    await browser.close();
  }

  const result = {
    scanner: 'runtime',
    engine: 'playwright',
    browser: 'chromium',
    urls: pagePlans.map((plan) => plan.url),
    per_url_counts: perUrlCounts,
    per_url_result_counts: perUrlResultCounts,
    issue_count: allIssues.length,
    pass_count: allPasses.length,
    issues: allIssues,
    passes: allPasses,
  };

  const output = JSON.stringify(result, null, 2);
  if (args.output) {
    fs.writeFileSync(args.output, output);
    console.error(`Wrote ${allIssues.length} runtime issues to ${args.output}`);
  } else {
    console.log(output);
  }
}

main().catch((err) => {
  console.error(formatError(err));
  process.exit(1);
});
