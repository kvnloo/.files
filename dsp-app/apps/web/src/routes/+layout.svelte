<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { fetchState } from '$lib/stores/dsp';

  let { children } = $props();

  onMount(() => {
    fetchState();
  });
</script>

<div class="min-h-screen bg-void text-text-primary">
  {@render children()}
</div>
