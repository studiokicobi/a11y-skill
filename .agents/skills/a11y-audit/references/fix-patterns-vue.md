# Fix Patterns — Vue / Nuxt

Load this file only when the detected framework is `vue`. Patterns for applying auto-fixable and human-input violations in Vue SFCs and Nuxt apps.

## 1.1.1 — Image missing alt

```diff
- <img :src="hero" />
+ <img :src="hero" alt="Team collaborating around a whiteboard" />
```

For Nuxt Image:

```diff
- <NuxtImg src="/hero.jpg" />
+ <NuxtImg src="/hero.jpg" alt="..." />
```

Decorative images use empty alt:

```vue
<img :src="divider" alt="" />
```

## 2.1.1 — div with click handler

```diff
- <div @click="handleClick">Click me</div>
+ <button type="button" @click="handleClick">Click me</button>
```

For navigation, use `<NuxtLink>` or `<router-link>`:

```diff
- <div @click="$router.push('/signup')">Get Started</div>
+ <NuxtLink to="/signup">Get Started</NuxtLink>
```

## 1.3.1 — Input missing label

```diff
- <input type="email" v-model="email" placeholder="Email" />
+ <label for="email">Email</label>
+ <input id="email" type="email" v-model="email" autocomplete="email" />
```

Note: Vue uses `for` (not `htmlFor` like React).

For complex forms, a labeled-input component is worth extracting:

```vue
<!-- LabeledInput.vue -->
<template>
  <div class="field">
    <label :for="id">{{ label }}</label>
    <input :id="id" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" v-bind="$attrs" />
    <span v-if="error" :id="`${id}-error`" role="alert">{{ error }}</span>
  </div>
</template>

<script setup>
defineProps(['id', 'label', 'modelValue', 'error']);
defineEmits(['update:modelValue']);
</script>
```

## 2.4.2 — Missing page title (Nuxt)

```vue
<script setup>
useHead({
  title: 'Products | Acme',
  meta: [{ name: 'description', content: 'Browse our catalog.' }],
});
</script>
```

For Vue Router without Nuxt, set in route meta and apply via a navigation guard:

```js
// router/index.js
router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} | My App` : 'My App';
});
```

## 4.1.3 — Status messages / live regions

```vue
<template>
  <div role="status" aria-live="polite" aria-atomic="true">
    {{ statusMessage }}
  </div>

  <!-- For critical errors -->
  <div v-if="error" role="alert" aria-live="assertive">
    {{ error }}
  </div>
</template>
```

## Route announcements in SPAs

Add a live region at the app root and update it on route change:

```vue
<!-- App.vue -->
<template>
  <div id="route-announcer" role="status" aria-live="assertive" aria-atomic="true" class="sr-only">
    {{ announcement }}
  </div>
  <NuxtPage />
</template>

<script setup>
const announcement = ref('');
const route = useRoute();
watch(() => route.fullPath, () => {
  // Delay so the new page title has rendered
  nextTick(() => {
    announcement.value = `Navigated to ${document.title}`;
  });
});
</script>
```

## 2.4.11 — Focus appearance (WCAG 2.2)

```vue
<template>
  <button class="btn">Submit</button>
</template>

<style scoped>
.btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
```

With Tailwind:

```vue
<button class="focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
  Submit
</button>
```

## Vue-specific gotchas

- `v-if` removes the element from the DOM; screen readers won't announce anything for a removed element. For status changes, use `v-show` with `aria-live` on the container, or keep the live region mounted and toggle its text content.
- `@click.stop` on a non-button element doesn't give you keyboard activation. Switch to a real `<button>`.
- When binding `aria-*` attributes dynamically, remember to use kebab-case in templates: `:aria-expanded="isOpen"`, not `:ariaExpanded`.
- `v-html` injects raw HTML — anything you put there is your responsibility to keep accessible.
