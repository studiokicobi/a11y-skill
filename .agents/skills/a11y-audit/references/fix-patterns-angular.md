# Fix Patterns — Angular

Load this file only when the detected framework is `angular`. Angular templates have a few binding syntaxes that differ from other frameworks, and the CDK provides strong a11y primitives that are worth using.

## 1.1.1 — Image missing alt

```diff
- <img [src]="hero" />
+ <img [src]="hero" alt="Team collaborating around a whiteboard" />
```

For dynamic alt:

```html
<img [src]="product.image" [alt]="product.imageAlt || product.name" />
```

## 2.1.1 — div with click handler

```diff
- <div (click)="handleClick()">Click me</div>
+ <button type="button" (click)="handleClick()">Click me</button>
```

For navigation:

```diff
- <div (click)="router.navigate(['/signup'])">Get Started</div>
+ <a routerLink="/signup">Get Started</a>
```

## 1.3.1 — Input missing label

```diff
- <input type="email" [(ngModel)]="email" placeholder="Email" />
+ <label for="email">Email</label>
+ <input id="email" type="email" [(ngModel)]="email" autocomplete="email" />
```

With reactive forms:

```html
<label for="email">Email</label>
<input id="email" type="email" formControlName="email" autocomplete="email" />
<span *ngIf="form.get('email')?.errors?.['required']" id="email-error" role="alert">
  Email is required
</span>
```

Wire the error up via `aria-describedby`:

```html
<input
  id="email"
  type="email"
  formControlName="email"
  [attr.aria-describedby]="hasEmailError ? 'email-error' : null"
  [attr.aria-invalid]="hasEmailError"
/>
```

Note: Angular uses `[attr.aria-*]` to bind ARIA attributes dynamically. `[aria-expanded]="isOpen"` won't work as expected — use `[attr.aria-expanded]="isOpen"`.

## 2.4.3 — Focus management (use CDK)

Angular CDK provides `cdkTrapFocus` and `FocusMonitor`. Use them rather than rolling your own:

```ts
// app.module.ts (or standalone component imports)
import { A11yModule } from '@angular/cdk/a11y';

@NgModule({ imports: [A11yModule] })
```

```html
<!-- Dialog with focus trap -->
<div cdkTrapFocus cdkTrapFocusAutoCapture role="dialog" [attr.aria-label]="title">
  <h2>{{ title }}</h2>
  <!-- content -->
  <button (click)="close()">Close</button>
</div>
```

For Angular Material, `MatDialog` handles this correctly out of the box — prefer it over custom dialogs.

## 4.1.2 — Custom widgets need ARIA

Tabs, dropdowns, and accordions need full ARIA. Here's the tablist pattern:

```html
<div role="tablist" aria-label="Dashboard sections">
  <button
    *ngFor="let tab of tabs; let i = index"
    role="tab"
    [id]="'tab-' + tab.id"
    [attr.aria-selected]="tab.active"
    [attr.aria-controls]="'panel-' + tab.id"
    [attr.tabindex]="tab.active ? 0 : -1"
    (click)="selectTab(tab)"
    (keydown)="handleTabKeydown($event, i)"
  >
    {{ tab.label }}
  </button>
</div>
<div
  *ngIf="selectedTab"
  role="tabpanel"
  [id]="'panel-' + selectedTab.id"
  [attr.aria-labelledby]="'tab-' + selectedTab.id"
  tabindex="0"
>
  {{ selectedTab.content }}
</div>
```

Component keyboard handling:

```ts
handleTabKeydown(event: KeyboardEvent, index: number): void {
  const tabCount = this.tabs.length;
  let newIndex = index;

  switch (event.key) {
    case 'ArrowRight': newIndex = (index + 1) % tabCount; break;
    case 'ArrowLeft':  newIndex = (index - 1 + tabCount) % tabCount; break;
    case 'Home':       newIndex = 0; break;
    case 'End':        newIndex = tabCount - 1; break;
    default: return;
  }

  event.preventDefault();
  this.selectTab(this.tabs[newIndex]);
  document.getElementById(`tab-${this.tabs[newIndex].id}`)?.focus();
}
```

Angular CDK also ships a `ListKeyManager` that handles this pattern for you — worth adopting if you have more than one keyboard-navigable widget.

## 4.1.3 — Live regions

```html
<!-- Polite (default, non-urgent) -->
<div role="status" aria-live="polite" aria-atomic="true">
  {{ statusMessage }}
</div>

<!-- Assertive (errors, urgent alerts) -->
<div *ngIf="error" role="alert" aria-live="assertive">
  {{ error }}
</div>
```

CDK's `LiveAnnouncer` is cleaner for imperative announcements:

```ts
import { LiveAnnouncer } from '@angular/cdk/a11y';

constructor(private announcer: LiveAnnouncer) {}

saveForm() {
  // ... save logic ...
  this.announcer.announce('Form saved successfully');
}
```

## Route announcements

Subscribe to `NavigationEnd` in the root component:

```ts
import { filter } from 'rxjs/operators';
import { Router, NavigationEnd } from '@angular/router';
import { LiveAnnouncer } from '@angular/cdk/a11y';

constructor(private router: Router, private announcer: LiveAnnouncer, private titleService: Title) {
  this.router.events.pipe(
    filter(e => e instanceof NavigationEnd)
  ).subscribe(() => {
    // Let the title update first
    setTimeout(() => this.announcer.announce(`Navigated to ${this.titleService.getTitle()}`), 100);
  });
}
```

## Angular-specific gotchas

- `[aria-expanded]="isOpen"` — doesn't bind correctly. Use `[attr.aria-expanded]="isOpen"`.
- `[attr.disabled]="isDisabled"` — Angular applies `disabled=""` if `isDisabled` is truthy and removes the attribute if falsy. `[disabled]="isDisabled"` works on form controls via Angular's property binding, but `[attr.disabled]` is more reliable for non-form elements.
- Wrapping an `<input>` inside a `<mat-form-field>` handles labeling automatically via `<mat-label>`. Don't add a separate `<label for="...">` on top of it.
- `ngClass` and `ngStyle` don't cause accessibility issues directly, but dynamic class changes that change a visible label without changing the accessible name do. Keep `aria-label` in sync with visible text when it changes.
