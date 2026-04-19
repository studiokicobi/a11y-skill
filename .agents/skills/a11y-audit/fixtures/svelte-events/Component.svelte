<script>
  import { goto } from '$app/navigation';
</script>

<div
  on:click={() => goto('/signup')}
  class="cta"
>
  Get started
</div>

<button type="button" on:click={() => goto('/pricing')}>
  View pricing
</button>
