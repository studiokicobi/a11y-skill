#!/usr/bin/env node
/**
 * a11y_runtime.js — runtime accessibility scanner using Puppeteer + axe-core.
 *
 * Launches a headless browser, loads the target URL, injects axe-core, runs
 * the full WCAG 2.2 AA rule set, and emits JSON findings aligned with the
 * static scanner's format.
 *
 * Auto-installs puppeteer and axe-core on first run if missing.
 *
 * Usage:
 *   node a11y_runtime.js --url http://localhost:3000 [--output results.json]
 *   node a11y_runtime.js --urls url1,url2,url3 --output results.json
 *
 * Output JSON shape matches the static scanner's "issues" array, with these
 * extras on each issue: `origin_rule_id` (the original axe rule ID), `html`
 * (element outer HTML), `target` (CSS selector path), and `impact`
 * (axe severity: critical/serious/moderate/minor).
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ----- Dependency resolution -----------------------------------------------

function ensureDeps() {
  const required = ['puppeteer', 'axe-core'];
  const missing = [];
  for (const dep of required) {
    try {
      require.resolve(dep);
    } catch {
      missing.push(dep);
    }
  }
  if (missing.length === 0) return;

  console.error(`Installing required packages: ${missing.join(', ')}...`);
  // Install to a local .a11y-audit-deps directory to avoid polluting the
  // target project's node_modules.
  const cacheDir = path.join(__dirname, '..', '.a11y-audit-deps');
  if (!fs.existsSync(cacheDir)) {
    fs.mkdirSync(cacheDir, { recursive: true });
    fs.writeFileSync(path.join(cacheDir, 'package.json'),
      JSON.stringify({ name: 'a11y-audit-deps', version: '1.0.0', private: true }));
  }
  execSync(`npm install --no-audit --no-fund --loglevel=error ${missing.join(' ')}`, {
    cwd: cacheDir, stdio: 'inherit',
  });
  // Add the cache dir to module paths so require() finds the installed packages
  module.paths.unshift(path.join(cacheDir, 'node_modules'));
}

ensureDeps();

const puppeteer = require('puppeteer');
const axeSource = fs.readFileSync(
  require.resolve('axe-core/axe.min.js'), 'utf-8');


// ----- Args ----------------------------------------------------------------

function parseArgs(argv) {
  const args = { urls: [], output: null, waitFor: 'networkidle2', timeout: 30000 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--url') { args.urls.push(argv[++i]); }
    else if (a === '--urls') { args.urls.push(...argv[++i].split(',').map(s => s.trim()).filter(Boolean)); }
    else if (a === '--output') { args.output = argv[++i]; }
    else if (a === '--wait-for') { args.waitFor = argv[++i]; }
    else if (a === '--timeout') { args.timeout = parseInt(argv[++i], 10); }
    else if (a === '--help' || a === '-h') {
      console.log('Usage: node a11y_runtime.js --url <url> [--output results.json]');
      process.exit(0);
    }
  }
  if (args.urls.length === 0) {
    console.error('Error: provide at least one URL via --url or --urls');
    process.exit(2);
  }
  return args;
}


// ----- axe → our format mapper ---------------------------------------------

// Map axe rule IDs to our static-scanner rule IDs where they overlap, so the
// triage step can deduplicate. For axe rules with no static equivalent, we
// use the axe rule ID directly.
const AXE_TO_STATIC_RULE = {
  'image-alt': 'img-missing-alt',
  'label': 'input-missing-label',
  'html-has-lang': 'html-missing-lang',
  'aria-hidden-focus': 'aria-hidden-focusable',
  'link-in-text-block': 'link-in-text-block',
  'duplicate-id': 'duplicate-id',
  'tabindex': 'positive-tabindex',
};

// axe impact → our triage hint. Runtime-detected contrast and computed issues
// often need a design decision, so we lean toward "input" for contrast and
// "auto" for clear-cut violations.
const AXE_TRIAGE_HINT = {
  'image-alt': 'input',        // alt text content needs human decision
  'label': 'input',            // label text content needs human decision
  'color-contrast': 'input',   // color choice often needs brand review
  'html-has-lang': 'auto',
  'aria-hidden-focus': 'auto',
  'duplicate-id': 'auto',
  'tabindex': 'input',
  'region': 'manual',          // landmark regions often need structural review
  'landmark-one-main': 'manual',
  'page-has-heading-one': 'manual',
  'heading-order': 'input',
  'focus-order-semantics': 'manual',
};

function mapAxeResult(result, pageUrl) {
  const issues = [];

  // Violations — confirmed failures. Route by impact and rule mapping.
  for (const violation of result.violations) {
    for (const node of violation.nodes) {
      issues.push({
        rule_id: AXE_TO_STATIC_RULE[violation.id] || violation.id,
        origin_rule_id: violation.id,
        wcag: (violation.tags || [])
          .filter(t => t.startsWith('wcag'))
          .map(t => t.replace('wcag', '').match(/.{1,3}/g)?.join('.'))
          .find(t => /^\d/.test(t)) || '',
        file: pageUrl,
        line: 0,
        col: 0,
        snippet: (node.html || '').slice(0, 300),
        message: violation.help,
        framework: 'runtime',
        triage_hint: AXE_TRIAGE_HINT[violation.id] || (
          violation.impact === 'critical' || violation.impact === 'serious'
            ? 'auto' : 'input'
        ),
        fix_data: {
          axe_rule: violation.id,
          impact: violation.impact,
          target: Array.isArray(node.target) ? node.target.join(' > ') : String(node.target),
          help_url: violation.helpUrl,
          failure_summary: node.failureSummary,
          result_type: 'violation',
        },
      });
    }
  }

  // Incomplete — axe couldn't determine pass/fail. These always need a human
  // to verify, so they route to Group 2 regardless of the rule's usual hint.
  for (const incomplete of (result.incomplete || [])) {
    for (const node of incomplete.nodes) {
      issues.push({
        rule_id: AXE_TO_STATIC_RULE[incomplete.id] || incomplete.id,
        origin_rule_id: incomplete.id,
        wcag: (incomplete.tags || [])
          .filter(t => t.startsWith('wcag'))
          .map(t => t.replace('wcag', '').match(/.{1,3}/g)?.join('.'))
          .find(t => /^\d/.test(t)) || '',
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
          target: Array.isArray(node.target) ? node.target.join(' > ') : String(node.target),
          help_url: incomplete.helpUrl,
          failure_summary: node.failureSummary,
          result_type: 'incomplete',
        },
      });
    }
  }

  return issues;
}


// ----- Scan ----------------------------------------------------------------

async function scanUrl(browser, url, opts) {
  const page = await browser.newPage();
  try {
    await page.setViewport({ width: 1280, height: 800 });
    await page.goto(url, { waitUntil: opts.waitFor, timeout: opts.timeout });
    await page.evaluate(axeSource);
    const result = await page.evaluate(async () => {
      /* global axe */
      return await axe.run(document, {
        runOnly: {
          type: 'tag',
          values: [
            'wcag2a', 'wcag2aa',
            'wcag21a', 'wcag21aa',
            'wcag22a', 'wcag22aa',
            'best-practice',
          ],
        },
        resultTypes: ['violations', 'incomplete'],
      });
    });
    return mapAxeResult(result, url);
  } finally {
    await page.close();
  }
}

async function main() {
  const args = parseArgs(process.argv);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  const allIssues = [];
  const perUrl = {};
  try {
    for (const url of args.urls) {
      console.error(`Scanning: ${url}`);
      try {
        const issues = await scanUrl(browser, url, args);
        perUrl[url] = issues.length;
        allIssues.push(...issues);
      } catch (err) {
        console.error(`  Failed: ${err.message}`);
        perUrl[url] = `error: ${err.message}`;
      }
    }
  } finally {
    await browser.close();
  }

  const result = {
    scanner: 'runtime',
    urls: args.urls,
    per_url_counts: perUrl,
    issue_count: allIssues.length,
    issues: allIssues,
  };

  const out = JSON.stringify(result, null, 2);
  if (args.output) {
    fs.writeFileSync(args.output, out);
    console.error(`Wrote ${allIssues.length} issues to ${args.output}`);
  } else {
    console.log(out);
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
