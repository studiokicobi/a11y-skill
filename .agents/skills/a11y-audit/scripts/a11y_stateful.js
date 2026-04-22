#!/usr/bin/env node
/**
 * a11y_stateful.js — Playwright journey runner with checkpoint axe scans.
 *
 * Reads a JSON/YAML journey config, executes supported interaction steps, and
 * emits stateful accessibility findings that align with the triage schema.
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

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

function parseArgs(argv) {
  const args = {
    config: '',
    output: '',
    screenshotDir: '',
    validateConfigOnly: false,
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--config') {
      args.config = argv[++i];
    } else if (arg === '--output') {
      args.output = argv[++i];
    } else if (arg === '--screenshot-dir') {
      args.screenshotDir = argv[++i];
    } else if (arg === '--validate-config-only') {
      args.validateConfigOnly = true;
    } else if (arg === '--help' || arg === '-h') {
      console.log(
        'Usage: node a11y_stateful.js --config journeys.json [--output results.json] ' +
        '[--screenshot-dir dir]'
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!args.config) {
    throw new Error('Provide --config with a JSON or YAML journey file.');
  }
  return args;
}

function mergeConfig(baseConfig, overrideConfig) {
  return {
    ...baseConfig,
    ...overrideConfig,
    viewport: { ...(baseConfig.viewport || {}), ...(overrideConfig.viewport || {}) },
    wait_for: { ...(baseConfig.wait_for || {}), ...(overrideConfig.wait_for || {}) },
    route_blocklist: overrideConfig.route_blocklist || baseConfig.route_blocklist || [],
  };
}

function resolveTargetUrl(rawUrl, options) {
  const value = String(rawUrl || '').trim();
  if (!value) {
    throw new Error('URL value must not be empty.');
  }
  const currentUrl = options.currentUrl || '';
  const baseUrl = options.baseUrl || '';
  const baseDir = options.baseDir || process.cwd();

  try {
    return new URL(value).toString();
  } catch {
    // fall through
  }

  if (baseUrl) {
    return new URL(value, baseUrl).toString();
  }
  if (currentUrl) {
    return new URL(value, currentUrl).toString();
  }

  const localPath = resolvePath(baseDir, value);
  if (fs.existsSync(localPath)) {
    return pathToFileURL(localPath).toString();
  }
  return value;
}

function validateViewport(viewport) {
  if (!viewport) {
    return;
  }
  if (typeof viewport.width !== 'number' || typeof viewport.height !== 'number') {
    throw new Error('Viewport config requires numeric width and height.');
  }
}

function buildJourneyPlans(args, config, configBaseDir) {
  const defaults = mergeConfig({
    wait_until: 'networkidle',
    timeout: 30000,
    wait_for: {},
    route_blocklist: [],
    viewport: { width: 1280, height: 800 },
    reduced_motion: 'no-preference',
    screenshot: Boolean(args.screenshotDir),
    screenshot_dir: args.screenshotDir ? resolvePath(process.cwd(), args.screenshotDir) : '',
  }, config.defaults || {});

  defaults.wait_until = normalizeWaitUntil(defaults.wait_until);
  validateViewport(defaults.viewport);
  if (!['reduce', 'no-preference'].includes(defaults.reduced_motion || 'no-preference')) {
    throw new Error('reduced_motion must be "reduce" or "no-preference".');
  }
  if (defaults.screenshot_dir) {
    defaults.screenshot_dir = resolvePath(configBaseDir, defaults.screenshot_dir);
  }

  const journeys = Array.isArray(config.journeys) ? config.journeys : [];
  if (journeys.length === 0) {
    throw new Error('Journey config requires a non-empty journeys array.');
  }

  return journeys.map((journey, index) => {
    const journeyId = String(journey.id || `journey-${index + 1}`);
    const mergedJourney = mergeConfig(defaults, journey || {});
    mergedJourney.id = journeyId;
    mergedJourney.timeout = parseInt(mergedJourney.timeout, 10);
    if (!Number.isFinite(mergedJourney.timeout) || mergedJourney.timeout <= 0) {
      throw new Error(`Invalid timeout for journey "${journeyId}".`);
    }
    validateViewport(mergedJourney.viewport);
    if (mergedJourney.screenshot_dir) {
      mergedJourney.screenshot_dir = resolvePath(configBaseDir, mergedJourney.screenshot_dir);
    }
    mergedJourney.base_url = mergedJourney.base_url || config.base_url || '';
    mergedJourney.start_url = resolveTargetUrl(journey.start_url || '', {
      baseUrl: mergedJourney.base_url,
      baseDir: configBaseDir,
    });
    if (!Array.isArray(journey.steps) || journey.steps.length === 0) {
      throw new Error(`Journey "${journeyId}" requires a non-empty steps array.`);
    }
    mergedJourney.steps = journey.steps.map((step, stepIndex) => {
      const mergedStep = mergeConfig(mergedJourney, step || {});
      mergedStep.id = String(step.id || `step-${stepIndex + 1}`);
      mergedStep.action = String(step.action || '').trim();
      if (!mergedStep.action) {
        throw new Error(`Journey "${journeyId}" step ${stepIndex + 1} requires an action.`);
      }
      mergedStep.timeout = parseInt(mergedStep.timeout, 10);
      if (!Number.isFinite(mergedStep.timeout) || mergedStep.timeout <= 0) {
        throw new Error(`Invalid timeout for ${journeyId}/${mergedStep.id}.`);
      }
      if (mergedStep.wait_until) {
        mergedStep.wait_until = normalizeWaitUntil(mergedStep.wait_until);
      }
      return mergedStep;
    });
    return mergedJourney;
  });
}

function slugify(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^\w.-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'item';
}

function checkpointScreenshotPath(screenshotDir, journeyId, stepId, checkpointIndex) {
  if (!screenshotDir) {
    return '';
  }
  fs.mkdirSync(screenshotDir, { recursive: true });
  return path.resolve(
    screenshotDir,
    `${slugify(journeyId)}-${slugify(stepId)}-${String(checkpointIndex).padStart(2, '0')}.png`
  );
}

function mapAxeNodes(resultType, axeItem, pageUrl, screenshotPath, journeyId, stepId, checkpointId) {
  const issues = [];
  for (const node of axeItem.nodes || []) {
    issues.push(addScreenshot({
      scanner: 'stateful',
      rule_id: AXE_TO_STATIC_RULE[axeItem.id] || axeItem.id,
      origin_rule_id: axeItem.id,
      wcag: extractWcag(axeItem.tags),
      file: pageUrl,
      line: 0,
      col: 0,
      snippet: (node.html || '').slice(0, 300),
      message: resultType === 'incomplete'
        ? `${axeItem.help} (needs manual verification)`
        : axeItem.help,
      framework: 'stateful',
      // Unknown axe rules default to 'input' (needs a human decision). We
      // should never autofix a rule we haven't explicitly vetted — severity
      // alone isn't a safety signal. Every 'auto' rule is an opt-in entry
      // in AXE_TRIAGE_HINT with a matching fix template in triage.render_fix.
      triage_hint: resultType === 'incomplete'
        ? 'input'
        : (AXE_TRIAGE_HINT[axeItem.id] || 'input'),
      journey_step_id: stepId,
      fix_data: {
        axe_rule: axeItem.id,
        impact: axeItem.impact || 'unknown',
        target: stringTarget(node.target),
        help_url: axeItem.helpUrl || '',
        failure_summary: node.failureSummary || '',
        result_type: resultType,
        journey_id: journeyId,
        journey_step_id: stepId,
        checkpoint_id: checkpointId,
      },
    }, screenshotPath));
  }
  return issues;
}

function mapAxePasses(result, pageUrl, journeyId, stepId, checkpointId) {
  return (result.passes || []).map((pass) => ({
    scanner: 'stateful',
    rule_id: AXE_TO_STATIC_RULE[pass.id] || pass.id,
    origin_rule_id: pass.id,
    wcag: extractWcag(pass.tags),
    url: pageUrl,
    journey_id: journeyId,
    journey_step_id: stepId,
    checkpoint_id: checkpointId,
    node_count: (pass.nodes || []).length,
  }));
}

async function describeActiveElement(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el) {
      return '';
    }
    const bits = [el.tagName.toLowerCase()];
    if (el.id) {
      bits.push(`#${el.id}`);
    }
    const name = el.getAttribute('name');
    if (name) {
      bits.push(`[name="${name}"]`);
    }
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) {
      bits.push(`[aria-label="${ariaLabel.slice(0, 40)}"]`);
    }
    return bits.join('');
  });
}

async function runCheckpoint(page, journey, step, axeSource, checkpointIndex) {
  await page.addScriptTag({ content: axeSource });
  const result = await page.evaluate(async (runOnlyTags) => {
    /* global axe */
    return axe.run(document, {
      runOnly: { type: 'tag', values: runOnlyTags },
      resultTypes: ['violations', 'incomplete', 'passes'],
    });
  }, RUNTIME_AXE_TAGS);

  const screenshotPath = checkpointScreenshotPath(
    journey.screenshot ? journey.screenshot_dir : '',
    journey.id,
    step.id,
    checkpointIndex
  );
  if (screenshotPath) {
    await page.screenshot({ path: screenshotPath, fullPage: true });
  }

  const pageUrl = page.url();
  const checkpointId = `${journey.id}/${step.id}`;
  const issues = [];
  for (const violation of result.violations || []) {
    issues.push(...mapAxeNodes('violation', violation, pageUrl, screenshotPath, journey.id, step.id, checkpointId));
  }
  for (const incomplete of result.incomplete || []) {
    issues.push(...mapAxeNodes('incomplete', incomplete, pageUrl, screenshotPath, journey.id, step.id, checkpointId));
  }

  return {
    checkpoint: {
      journey_id: journey.id,
      journey_step_id: step.id,
      checkpoint_id: checkpointId,
      url: pageUrl,
      screenshot: screenshotPath,
      counts: {
        issues: countAxeNodes(result.violations) + countAxeNodes(result.incomplete),
        violations: countAxeNodes(result.violations),
        incomplete: countAxeNodes(result.incomplete),
        passes: (result.passes || []).length,
      },
    },
    issues,
    passes: mapAxePasses(result, pageUrl, journey.id, step.id, checkpointId),
  };
}

async function executeStep(page, step, context) {
  if (step.action === 'click') {
    if (!step.selector) {
      throw new Error('click step requires selector.');
    }
    await page.click(step.selector, { timeout: step.timeout });
    return;
  }

  if (step.action === 'press') {
    if (step.selector) {
      await page.locator(step.selector).focus({ timeout: step.timeout });
    }
    if (!step.key) {
      throw new Error('press step requires key.');
    }
    await page.keyboard.press(step.key);
    return;
  }

  if (step.action === 'fill') {
    if (!step.selector) {
      throw new Error('fill step requires selector.');
    }
    await page.fill(step.selector, String(step.value ?? ''), { timeout: step.timeout });
    return;
  }

  if (step.action === 'select') {
    if (!step.selector) {
      throw new Error('select step requires selector.');
    }
    const values = Array.isArray(step.values) ? step.values : [step.value];
    await page.selectOption(step.selector, values.filter((value) => value != null).map(String));
    return;
  }

  if (step.action === 'navigate') {
    const targetUrl = resolveTargetUrl(step.url || step.href || '', {
      baseUrl: journeyBaseUrl(context.journey, page),
      currentUrl: page.url(),
      baseDir: context.baseDir,
    });
    await page.goto(targetUrl, {
      waitUntil: step.wait_until,
      timeout: step.timeout,
    });
    return;
  }

  if (step.action === 'assert') {
    await runAssertStep(page, step);
    return;
  }

  throw new Error(`Unsupported journey action "${step.action}".`);
}

function journeyBaseUrl(journey, page) {
  return journey.base_url || page.url() || journey.start_url;
}

async function runAssertStep(page, step) {
  const timeout = step.timeout;
  if (step.selector) {
    await page.waitForSelector(step.selector, { state: 'visible', timeout });
  }
  if (step.hidden_selector) {
    await page.waitForSelector(step.hidden_selector, { state: 'hidden', timeout });
  }
  if (step.text) {
    await page.getByText(step.text, { exact: false }).waitFor({ state: 'visible', timeout });
  }
  if (step.url_includes && !page.url().includes(step.url_includes)) {
    throw new Error(`Expected URL to include "${step.url_includes}" but got "${page.url()}".`);
  }
  if (step.focused_selector) {
    const handle = await page.locator(step.focused_selector).elementHandle({ timeout });
    if (!handle) {
      throw new Error(`Focused selector not found: ${step.focused_selector}`);
    }
    const isFocused = await handle.evaluate((el) => el === document.activeElement);
    if (!isFocused) {
      throw new Error(`Expected focus on ${step.focused_selector}.`);
    }
  }
}

async function runJourney(browser, journey, auth, axeSource, baseDir) {
  const contextOptions = {
    viewport: journey.viewport || { width: 1280, height: 800 },
    reducedMotion: journey.reduced_motion || 'no-preference',
  };
  if (auth.mode === 'storage_state') {
    contextOptions.storageState = auth.storageStatePath;
  }

  const context = await browser.newContext(contextOptions);
  const focusTransitions = [];
  const stepFailures = [];
  const checkpoints = [];
  const issues = [];
  const passes = [];

  try {
    await applyAuth(context, auth);
    const page = await context.newPage();
    await applyRouteBlocking(page, journey.route_blocklist);
    const response = await page.goto(journey.start_url, {
      waitUntil: journey.wait_until,
      timeout: journey.timeout,
    });
    if (auth.mode !== 'none' && response && (response.status() === 401 || response.status() === 403)) {
      throw new Error(
        `Authenticated request failed with HTTP ${response.status()}. ` +
        'Check the auth config or refresh the stored state.'
      );
    }
    await applyWaitConditions(page, journey);

    let checkpointIndex = 0;
    for (const step of journey.steps) {
      const beforeUrl = page.url();
      const focusBefore = await describeActiveElement(page);
      try {
        await executeStep(page, step, { baseDir, journey });
        await applyWaitConditions(page, step);
        const focusAfter = await describeActiveElement(page);
        focusTransitions.push({
          journey_id: journey.id,
          journey_step_id: step.id,
          action: step.action,
          before_url: beforeUrl,
          url: page.url(),
          before: focusBefore,
          after: focusAfter,
        });
        if (step.scan) {
          checkpointIndex += 1;
          const scan = await runCheckpoint(page, journey, step, axeSource, checkpointIndex);
          checkpoints.push(scan.checkpoint);
          issues.push(...scan.issues);
          passes.push(...scan.passes);
        }
      } catch (err) {
        stepFailures.push({
          journey_id: journey.id,
          journey_step_id: step.id,
          action: step.action,
          url: page.url(),
          message: err && err.message ? err.message : String(err),
        });
        break;
      }
    }

    return {
      issues,
      passes,
      checkpoints,
      focusTransitions,
      stepFailures,
      journey: {
        id: journey.id,
        start_url: journey.start_url,
        step_count: journey.steps.length,
        checkpoint_count: checkpoints.length,
      },
    };
  } finally {
    await context.close();
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const { config, baseDir } = loadConfig(args.config, { kind: 'journey' });
  const auth = resolveAuth(config.auth, baseDir);
  const journeys = buildJourneyPlans(args, config, baseDir);

  if (args.validateConfigOnly) {
    console.error(`Validated stateful config for ${journeys.length} journey(s).`);
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
  const allJourneys = [];
  const checkpoints = [];
  const focusTransitions = [];
  const stepFailures = [];
  try {
    for (const journey of journeys) {
      console.error(`Running journey: ${journey.id}`);
      const result = await runJourney(browser, journey, auth, axeSource, baseDir);
      allJourneys.push(result.journey);
      allIssues.push(...result.issues);
      allPasses.push(...result.passes);
      checkpoints.push(...result.checkpoints);
      focusTransitions.push(...result.focusTransitions);
      stepFailures.push(...result.stepFailures);
    }
  } finally {
    await browser.close();
  }

  const output = {
    scanner: 'stateful',
    engine: 'playwright',
    browser: 'chromium',
    issue_count: allIssues.length,
    pass_count: allPasses.length,
    journey_count: allJourneys.length,
    journeys: allJourneys,
    checkpoints,
    focus_transitions: focusTransitions,
    step_failures: stepFailures,
    issues: allIssues,
    passes: allPasses,
  };

  const serialized = JSON.stringify(output, null, 2);
  if (args.output) {
    fs.writeFileSync(args.output, serialized);
    console.error(`Wrote ${allIssues.length} stateful issues to ${args.output}`);
  } else {
    console.log(serialized);
  }
}

main().catch((err) => {
  console.error(formatError(err));
  process.exit(1);
});
