# Contrast Alternatives

When the scanner flags a color that fails WCAG 2.2 AA (4.5:1 for normal text, 3:1 for large text and UI components), use these curated replacements. They preserve the visual intent as closely as possible while meeting the threshold.

**Do not invent replacement colors outside this table.** If a color isn't here, route the issue to **Needs your decision** and ask the user for a brand-aligned alternative.

## CSS hex colors on white backgrounds

| Failing color | Ratio | Replacement | New ratio |
| --- | --- | --- | --- |
| `#aaa` / `#aaaaaa` | 2.32:1 | `#767676` | 4.54:1 (AA) |
| `#bbb` / `#bbbbbb` | 1.79:1 | `#767676` | 4.54:1 (AA) |
| `#ccc` / `#cccccc` | 1.61:1 | `#707070` | 5.00:1 (AA) |
| `#999` / `#999999` | 2.85:1 | `#767676` | 4.54:1 (AA) |
| `#888` / `#888888` | 3.54:1 | `#767676` | 4.54:1 (AA) |
| `#777` / `#777777` | 4.48:1 | `#757575` | 4.60:1 (AA) |
| `#66bb6a` | 3.06:1 | `#2e7d32` | 5.87:1 (AA) |
| `#42a5f5` | 2.81:1 | `#1565c0` | 6.08:1 (AA) |
| `#ef5350` | 3.13:1 | `#c62828` | 5.57:1 (AA) |

## Tailwind classes on white/light backgrounds

Assumes background is white, gray-50, or gray-100. For darker backgrounds, route to **Needs your decision**.

| Failing class | Replacement | Notes |
| --- | --- | --- |
| `text-gray-300` | `text-gray-600` | |
| `text-gray-400` | `text-gray-600` | |
| `text-slate-300` | `text-slate-600` | |
| `text-slate-400` | `text-slate-600` | |
| `text-zinc-300` | `text-zinc-600` | |
| `text-zinc-400` | `text-zinc-600` | |
| `text-neutral-300` | `text-neutral-600` | |
| `text-neutral-400` | `text-neutral-600` | |
| `text-stone-300` | `text-stone-600` | |
| `text-stone-400` | `text-stone-600` | |
| `text-blue-300` | `text-blue-700` | |
| `text-blue-400` | `text-blue-700` | |
| `text-red-300` | `text-red-700` | |
| `text-red-400` | `text-red-700` | |
| `text-green-300` | `text-green-700` | |
| `text-green-400` | `text-green-700` | |
| `text-yellow-300` | `text-yellow-800` | yellow needs extra darkening |
| `text-yellow-400` | `text-yellow-800` | yellow needs extra darkening |
| `text-orange-300` | `text-orange-700` | |
| `text-orange-400` | `text-orange-700` | |

## Gotchas

- **Dark mode**: these mappings assume light mode. For dark backgrounds, the scale flips and 300-level text often works while 700-level fails. When the codebase uses `dark:` variants, check both.
- **Semantic colors**: if the codebase uses CSS custom properties like `--color-muted`, update the variable definition, not individual usages.
- **Large text exception**: WCAG allows 3:1 for text ≥18pt (~24px) or ≥14pt bold (~18.66px bold). If the flagged text is large, a higher class like `-500` may pass. Route to **Needs your decision** if unsure.
