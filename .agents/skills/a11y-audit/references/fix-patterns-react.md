# Fix Patterns — React / Next.js

Load this file only when the detected framework is `react` or `nextjs`. Framework-specific patterns for applying the auto-fixable and human-input violations.

## 1.1.1 — Image missing alt

```diff
- <img src={hero} />
+ <img src={hero} alt="Team collaborating around a whiteboard" />
```

Decorative images get empty alt:

```jsx
<img src={divider} alt="" />
```

In Next.js, prefer `<Image>` from `next/image`:

```diff
- <img src="/hero.jpg" />
+ <Image src="/hero.jpg" alt="..." width={800} height={400} />
```

## 2.1.1 — div with onClick

```diff
- <div onClick={handleClick}>Click me</div>
+ <button type="button" onClick={handleClick}>Click me</button>
```

If it navigates, use a link instead:

```diff
- <div onClick={() => router.push('/signup')}>Get Started</div>
+ <Link href="/signup">Get Started</Link>
```

Note: always add `type="button"` to `<button>` inside a `<form>` — the default is `submit`.

## 1.3.1 — Input missing label

```diff
- <input placeholder="Email" />
+ <label htmlFor="email">Email</label>
+ <input id="email" type="email" autoComplete="email" />
```

For inputs inside styled wrappers, use `aria-label` as a fallback (but visible labels are preferred):

```jsx
<input type="search" aria-label="Search products" />
```

## 2.4.2 — Missing page title (Next.js App Router)

```jsx
// app/products/page.tsx
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Products | Acme',
  description: 'Browse our catalog.',
};
```

For Pages Router:

```jsx
import Head from 'next/head';

export default function ProductsPage() {
  return (
    <>
      <Head><title>Products | Acme</title></Head>
      {/* ... */}
    </>
  );
}
```

## 2.4.3 — Focus management in modals

```jsx
import { useEffect, useRef } from 'react';

function Modal({ isOpen, onClose, children, title }) {
  const modalRef = useRef(null);
  const previousFocus = useRef(null);

  useEffect(() => {
    if (isOpen) {
      previousFocus.current = document.activeElement;
      modalRef.current?.focus();
    } else {
      previousFocus.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      ref={modalRef}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      tabIndex={-1}
    >
      {children}
    </div>
  );
}
```

For production, consider a library that handles focus trapping correctly — `@radix-ui/react-dialog`, `react-aria`, or Headless UI all include it.

## 2.4.11 — Focus appearance (WCAG 2.2, new)

```jsx
// Tailwind
<button className="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
  Submit
</button>
```

```css
/* CSS module or global */
button:focus-visible {
  outline: 2px solid #005fcc;
  outline-offset: 2px;
}
```

## 4.1.3 — Status messages / live regions

```jsx
function Toast({ message }) {
  return (
    <div role="status" aria-live="polite" aria-atomic="true">
      {message}
    </div>
  );
}

// For critical errors
function ErrorAlert({ error }) {
  return (
    <div role="alert" aria-live="assertive">
      {error}
    </div>
  );
}
```

## Route announcements in client-side navigation

Next.js handles this automatically in App Router. For React Router or other client-side routing, add an announcer:

```jsx
function RouteAnnouncer() {
  const [message, setMessage] = useState('');
  const location = useLocation();

  useEffect(() => {
    setMessage(`Navigated to ${document.title}`);
  }, [location]);

  return (
    <div role="status" aria-live="assertive" className="sr-only">
      {message}
    </div>
  );
}
```

## React-specific gotchas

- JSX uses `htmlFor` (not `for`) and `className` (not `class`). The scanner's suggestions account for this — double-check when applying manually.
- `onClick` on non-button elements doesn't fire for keyboard Enter/Space. If you genuinely can't use a `<button>` (rare), add `onKeyDown` handlers for Enter and Space.
- `dangerouslySetInnerHTML` bypasses React's accessibility assumptions. If used, the injected content is your responsibility to keep accessible.
