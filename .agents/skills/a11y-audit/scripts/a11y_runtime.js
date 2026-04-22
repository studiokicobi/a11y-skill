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

const {
  AXE_TO_STATIC_RULE,
  AXE_TRIAGE_HINT,
  RUNTIME_AXE_TAGS,
  addScreenshot,
  applyAuth,
  applyRouteBlocking,
  applyWaitConditions,
  countAxeNodes,
  ensureDeps,
  ensurePlaywrightBrowser,
  extractWcag,
  formatError,
  loadConfig,
  normalizeWaitUntil,
  requireFromCache,
  resolveAuth,
  resolvePath,
  stringTarget,
} = require('./a11y_runtime_common');

function parseViewport(value) {
  const match = /^(\d+)x(\d+)$/i.exec(value || '');
  if (!match) {
    throw new Error(`Invalid viewport value "${value}". Use WIDTHxHEIGHT, e.g. 1280x800.`);
  }
  return { width: parseInt(match[1], 10), height: parseInt(match[2], 10) };
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
        // Unknown axe rules default to 'input' (needs a human decision). We
        // should never autofix a rule we haven't explicitly vetted — severity
        // alone isn't a safety signal. Every 'auto' rule is an opt-in entry
        // in AXE_TRIAGE_HINT with a matching fix template in triage.render_fix.
        triage_hint: AXE_TRIAGE_HINT[violation.id] || 'input',
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
    const result = await page.evaluate(async (runOnlyTags) => {
      /* global axe */
      return axe.run(document, {
        runOnly: { type: 'tag', values: runOnlyTags },
        resultTypes: ['violations', 'incomplete', 'passes'],
      });
    }, RUNTIME_AXE_TAGS);

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
  // Load deps via the cache-bound `requireFromCache` so the caller module
  // doesn't need to find `.a11y-audit-deps/node_modules` via its own
  // `module.paths` walk. See a11y_runtime_common.js for why this matters.
  const playwright = requireFromCache('playwright');
  ensurePlaywrightBrowser(playwright);
  const axeSource = fs.readFileSync(requireFromCache.resolve('axe-core/axe.min.js'), 'utf-8');

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
