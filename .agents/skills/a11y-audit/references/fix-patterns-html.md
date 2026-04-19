# Fix Patterns — Plain HTML

Load this file only when the detected framework is `html`. Patterns for raw HTML, Jinja/Twig/ERB/Blade templates, static site generators (11ty, Hugo, Jekyll, Statamic), and anywhere HTML is written without a component framework.

## 1.1.1 — Image missing alt

```diff
- <img src="/hero.jpg" />
+ <img src="/hero.jpg" alt="Team collaborating around a whiteboard" />
```

Decorative images:

```html
<img src="/decorative-flourish.svg" alt="" />
```

Complex images (charts, diagrams): short alt + longer description nearby:

```html
<img src="/q3-revenue.png" alt="Bar chart, Q3 revenue by region" aria-describedby="q3-desc" />
<p id="q3-desc">North America $2.1M, Europe $1.8M, Asia-Pacific $1.3M. Full breakdown in the table below.</p>
```

## 2.1.1 — div with onclick (inline handlers)

```diff
- <div onclick="openMenu()">Menu</div>
+ <button type="button" onclick="openMenu()">Menu</button>
```

For links that look like buttons, use `<a>` with `role="button"` only when you genuinely can't use `<button>` — usually you can.

## 2.4.1 — Skip link

Every multi-region page should have a skip link as the first focusable element:

```html
<body>
  <a href="#main-content" class="skip-link">Skip to main content</a>
  <nav aria-label="Main navigation"><!-- long navigation --></nav>
  <main id="main-content" tabindex="-1"><!-- content --></main>
</body>
```

CSS:

```css
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  padding: 8px 16px;
  background: #005fcc;
  color: #fff;
  z-index: 1000;
  transition: top 0.2s;
}
.skip-link:focus {
  top: 0;
}
```

The `tabindex="-1"` on `<main>` lets programmatic focus land on it without making it part of the tab order.

## 1.3.1 — Data tables

```diff
- <table>
-   <tr><td>Name</td><td>Email</td><td>Role</td></tr>
-   <tr><td>Alice</td><td>alice@co.com</td><td>Admin</td></tr>
- </table>
+ <table>
+   <caption>Team members and their roles</caption>
+   <thead>
+     <tr>
+       <th scope="col">Name</th>
+       <th scope="col">Email</th>
+       <th scope="col">Role</th>
+     </tr>
+   </thead>
+   <tbody>
+     <tr>
+       <th scope="row">Alice</th>
+       <td>alice@co.com</td>
+       <td>Admin</td>
+     </tr>
+   </tbody>
+ </table>
```

`scope="col"` on column headers, `scope="row"` on row headers. For complex tables (merged cells, nested headers), use `headers` and `id`.

## 1.3.1 — Landmarks

Wrap page regions in semantic landmarks so screen reader users can navigate by them:

```diff
- <div class="header">...</div>
- <div class="nav">...</div>
- <div class="main">...</div>
- <div class="footer">...</div>
+ <header>...</header>
+ <nav aria-label="Main navigation">...</nav>
+ <main>...</main>
+ <footer>...</footer>
```

If you have multiple `<nav>` landmarks on a page (primary nav, footer nav, breadcrumbs), distinguish them with `aria-label`:

```html
<nav aria-label="Main navigation">...</nav>
<nav aria-label="Breadcrumb">...</nav>
<nav aria-label="Footer">...</nav>
```

## 1.3.1 — Forms

```html
<form>
  <div class="field">
    <label for="email">Email</label>
    <input id="email" type="email" name="email" autocomplete="email" required />
  </div>

  <div class="field">
    <label for="password">Password</label>
    <input id="password" type="password" name="password" autocomplete="current-password" required />
  </div>

  <button type="submit">Sign in</button>
</form>
```

For error messages, use `aria-describedby` and `aria-invalid`:

```html
<label for="email">Email</label>
<input
  id="email"
  type="email"
  aria-describedby="email-error"
  aria-invalid="true"
/>
<span id="email-error" role="alert">Please enter a valid email address.</span>
```

## 2.4.11 — Focus appearance (WCAG 2.2)

```css
:focus-visible {
  outline: 2px solid #005fcc;
  outline-offset: 2px;
}

/* If you really need to remove default outline, provide a replacement */
button:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
  box-shadow: 0 0 0 4px rgba(0, 95, 204, 0.2);
}
```

## Screen-reader-only utility

Include this class in every project — you'll need it:

```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}

/* Visible on focus (for skip links and similar) */
.sr-only-focusable:focus,
.sr-only-focusable:active {
  position: static;
  width: auto;
  height: auto;
  overflow: visible;
  clip: auto;
  white-space: inherit;
}
```

## Common plain-HTML gotchas

- A `<button>` inside a `<form>` defaults to `type="submit"`. Add `type="button"` explicitly for any button that doesn't submit.
- Inline `onclick="..."` attributes still count as click handlers. `<div onclick="...">` is still inaccessible.
- Without a framework's client-side router, route changes are full page loads, so screen readers naturally get the new title — no announcer needed.
- Templating languages (Jinja, Handlebars, ERB, Blade, Twig, Statamic Antlers) compile to HTML; the scanner runs on the compiled output or source, and the fix patterns apply to the rendered markup either way.
- Static site generators often have a base template that's the right place to fix sitewide issues (missing `<html lang>`, skip link, focus styles). Fix once, it applies everywhere.
