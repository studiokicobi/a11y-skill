# Fix Patterns — Svelte / SvelteKit

Load this file only when the detected framework is `svelte`. Svelte has strong built-in a11y warnings at compile time — the scanner here catches things that slip past those warnings or were suppressed.

## 1.1.1 — Image missing alt

Svelte actually warns about this at compile time (`a11y-missing-attribute`). If the warning was suppressed:

```diff
- <img src={hero} />
+ <img src={hero} alt="Team collaborating around a whiteboard" />
```

## 2.1.1 — div with click handler

Svelte warns about `click` handlers on non-interactive elements. The fix is the same as other frameworks:

```diff
- <div on:click={handleClick}>Click me</div>
+ <button type="button" on:click={handleClick}>Click me</button>
```

For navigation in SvelteKit:

```diff
- <div on:click={() => goto('/signup')}>Get Started</div>
+ <a href="/signup">Get Started</a>
```

SvelteKit's client-side navigation intercepts `<a href>` automatically — you don't need `goto()` for internal links.

## 1.3.1 — Input missing label

```diff
- <input type="email" bind:value={email} placeholder="Email" />
+ <label for="email">Email</label>
+ <input id="email" type="email" bind:value={email} autocomplete="email" />
```

## 2.4.2 — Page titles (SvelteKit)

```svelte
<!-- +page.svelte -->
<svelte:head>
  <title>Products | Acme</title>
  <meta name="description" content="Browse our catalog." />
</svelte:head>
```

## 4.1.3 — Live regions

```svelte
<script>
  export let message = '';
</script>

<div role="status" aria-live="polite" aria-atomic="true">
  {message}
</div>

<!-- Critical alerts -->
{#if error}
  <div role="alert" aria-live="assertive">{error}</div>
{/if}
```

## Accordion pattern

Common custom widget that frequently gets built without ARIA. Here's the accessible version:

```svelte
<script>
  export let items = [];
  let openIndex = -1;

  function toggle(i) {
    openIndex = openIndex === i ? -1 : i;
  }
</script>

<div class="accordion">
  {#each items as item, i}
    <h3>
      <button
        class="accordion-header"
        aria-expanded={openIndex === i}
        aria-controls="panel-{i}"
        id="header-{i}"
        on:click={() => toggle(i)}
      >
        {item.title}
        <span class="icon" aria-hidden="true">
          {openIndex === i ? '−' : '+'}
        </span>
      </button>
    </h3>
    <div
      id="panel-{i}"
      role="region"
      aria-labelledby="header-{i}"
      class="accordion-content"
      class:open={openIndex === i}
      hidden={openIndex !== i}
    >
      {item.body}
    </div>
  {/each}
</div>

<style>
  .accordion-header {
    min-height: 44px; /* WCAG 2.5.8 target size */
    width: 100%;
    padding: 12px 16px;
    text-align: left;
  }
  .accordion-header:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
</style>
```

## SvelteKit route announcements

SvelteKit's `$navigating` store fires on client-side navigation. Use it to announce:

```svelte
<!-- +layout.svelte -->
<script>
  import { navigating, page } from '$app/stores';
  import { tick } from 'svelte';

  let announcement = '';

  $: if (!$navigating && $page) {
    tick().then(() => {
      announcement = `Navigated to ${document.title}`;
    });
  }
</script>

<div role="status" aria-live="assertive" aria-atomic="true" class="sr-only">
  {announcement}
</div>

<slot />
```

## Svelte-specific notes

- Svelte's compiler-level a11y warnings are more comprehensive than most frameworks. Don't suppress them without thinking hard — `<!-- svelte-ignore a11y-* -->` should be rare.
- `on:click|preventDefault` and similar modifiers compile to standard event handlers. They don't create a11y issues on their own, but `on:click` on a `<div>` still compiles to a non-keyboard-accessible listener.
- `class:directive` for toggling classes is fine for visual changes. For *semantic* state changes (expanded, selected, checked), update the relevant `aria-*` attribute too.
- `{@html ...}` injects raw HTML — its accessibility is your responsibility.
