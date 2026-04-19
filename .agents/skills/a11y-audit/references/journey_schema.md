# Journey Schema

`scripts/a11y_stateful.js` reads a JSON or YAML config with this shape:

```yaml
auth:
  mode: storage_state | headers | cookies
  storage_state_path: .secrets/playwright-auth.json
  headers:
    Authorization: env:ACCESS_TOKEN
  cookies_path: .secrets/cookies.json

defaults:
  wait_until: networkidle
  timeout: 30000
  viewport:
    width: 1280
    height: 800
  reduced_motion: no-preference | reduce
  route_blocklist:
    - "**/analytics/**"
  screenshot: true
  screenshot_dir: .artifacts/stateful

base_url: http://localhost:3000

journeys:
  - id: settings-modal
    start_url: /settings
    steps:
      - id: open-modal
        action: click
        selector: "#open-modal"
        wait_for:
          selector: "[role='dialog']"
        scan: true
      - id: close-modal
        action: press
        key: Escape
        wait_for:
          hidden_selector: "[role='dialog']"
        scan: true
```

## Supported step actions

- `click`
  - required: `selector`
- `press`
  - required: `key`
  - optional: `selector` to focus before the key press
- `fill`
  - required: `selector`, `value`
- `select`
  - required: `selector`
  - accepts `value` or `values`
- `navigate`
  - required: `url` or `href`
- `assert`
  - supports `selector`, `hidden_selector`, `text`, `url_includes`, and `focused_selector`

## Wait settings

Each journey and step can override:

- `wait_until`
- `timeout`
- `wait_for.selector`
- `wait_for.hidden_selector`
- `wait_for.load_state`
- `wait_for.timeout_ms`

## Output notes

- `scan: true` runs an axe checkpoint after the step completes.
- Stateful findings carry `scanner: "stateful"` and `journey_step_id`.
- The runner records `focus_transitions`, `step_failures`, and checkpoint screenshots.
