# Common Pitfalls

Mistakes to avoid when applying accessibility fixes. Consult this file before auto-applying any fix the pattern files don't explicitly cover.

## ARIA and semantics

**Don't add `role="button"` to a `<div>`.** A `<button>` element gives you keyboard activation (Enter, Space), focus management, disabled state, and form participation for free. `role="button"` gives you none of that — you'd need to re-implement all of it in JS. Always prefer the native element.

**Don't add `tabindex="0"` everywhere.** Only interactive elements should be focusable. Adding `tabindex` to paragraphs, divs, or decorative elements creates a confusing tab order for keyboard users. Native interactive elements (`<a>`, `<button>`, `<input>`, `<select>`, `<textarea>`) are already focusable.

**Don't use `tabindex` values greater than 0.** They override the natural DOM order and create a separate tab sequence that's nearly always wrong. Use `0` to make something focusable in natural order, `-1` to make it focusable only via JS.

**Don't use `aria-label` on generic containers.** Screen readers often ignore `aria-label` on `<div>` or `<span>`. If you need to label a section, use a heading inside it, or give it `role="region"` and use `aria-labelledby` pointing to a visible heading.

**Don't set `aria-hidden="true"` on elements that contain focusable children.** If the user can Tab into something the screen reader is told to ignore, you've created a confusing state. Either remove the `aria-hidden`, or add `tabindex="-1"` to the focusable descendants.

## Visual and hiding

**Don't use `display: none` to hide content from sighted users while keeping it for screen readers.** `display: none` removes the element from the accessibility tree entirely. Use an `.sr-only` class (or Tailwind's built-in `sr-only`) instead:

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
```

**Don't remove `outline` without a replacement.** `outline: none` by itself breaks keyboard navigation. If you want a custom focus style, use `:focus-visible`:

```css
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

Note `:focus-visible` vs `:focus` — the former only shows for keyboard users, the latter shows for mouse clicks too.

## Images

**Empty `alt=""` is not the same as missing `alt`.** Empty alt explicitly marks an image as decorative and tells screen readers to skip it. Missing alt makes screen readers announce the filename or the word "image", which is worse. If the image is informational, write alt text. If it's purely decorative, use `alt=""`.

**Don't repeat nearby text in alt.** If a caption below the image already describes it, the alt can be empty or very brief. Otherwise screen reader users hear the same thing twice.

## Forms

**Don't use `placeholder` as the only label.** Placeholder text disappears as soon as the user starts typing, which fails WCAG 1.3.1 and 3.3.2. Always pair with a visible `<label>`. Placeholder can still be useful as an *example* value ("e.g. jane@example.com") — just not as the label.

**Don't indicate required fields with color alone.** Red asterisks are common and helpful, but a screen reader user won't see them. Add `required` to the input (screen readers announce it), and mention "required" in the label text or use `aria-required="true"`.

**Don't block paste in password fields.** Password managers rely on it, and blocking paste is a common WCAG 2.2 — 3.3.8 Accessible Authentication failure.

## Headings

**Don't skip heading levels for styling reasons.** If you need a small heading, style an `<h2>` to look small — don't use `<h4>` instead. Screen reader users navigate by heading structure, and skipped levels break the outline.

**Don't use `<h1>` more than once per page** (with rare exceptions in some SPA patterns). Each page has one main heading.

## Motion and media

**Never autoplay video or audio with sound.** This violates WCAG 1.4.2 and is broadly hated by users regardless of ability. Muted, silent autoplay is tolerated; audio autoplay is not.

**Wrap animations in `prefers-reduced-motion`.** Users with vestibular disorders get motion-sick from parallax, large transitions, and auto-scrolling carousels:

```css
@media (prefers-reduced-motion: no-preference) {
  .carousel { scroll-behavior: smooth; }
}
```

## Color

**Don't convey information with color alone.** Red/green for status, red text for errors, colored dots for states — all fail WCAG 1.4.1 when they're the only indicator. Add an icon, text label, or pattern.

**Don't trust a single contrast ratio for a gradient or image background.** Test against the lightest and darkest points. If text overlaps images, add a semi-transparent overlay or a shadow behind the text.
