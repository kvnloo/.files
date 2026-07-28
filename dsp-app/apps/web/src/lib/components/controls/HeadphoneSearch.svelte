<script lang="ts">
  import { searchHeadphones, installHeadphone } from '$lib/stores/dsp';
  import type { HeadphoneSearchResult } from '@aural/shared';

  let query = $state('');
  let results = $state<HeadphoneSearchResult[]>([]);
  let searching = $state(false);
  let installing = $state<string | null>(null);
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  function handleInput() {
    if (debounceTimer) clearTimeout(debounceTimer);
    if (query.length < 2) {
      results = [];
      return;
    }
    searching = true;
    debounceTimer = setTimeout(async () => {
      results = await searchHeadphones(query);
      searching = false;
    }, 300);
  }

  async function handleInstall(result: HeadphoneSearchResult) {
    const key = `${result.source}/${result.model}`;
    installing = key;
    const profile = await installHeadphone(result.source, result.rig, result.model);
    installing = null;
    if (profile) {
      query = '';
      results = [];
    }
  }
</script>

<div class="space-y-2">
  <h3 class="text-xs font-medium text-text-tertiary uppercase tracking-wider px-1">Search Headphones</h3>
  <div class="relative">
    <input
      type="text"
      placeholder="e.g. HD650, DT 990..."
      bind:value={query}
      oninput={handleInput}
      class="w-full bg-surface-2/50 border border-border/30 rounded-lg px-3 py-2 text-xs text-text-primary
             placeholder:text-text-tertiary/50 focus:outline-none focus:border-amber-dim/50 transition-colors"
    />
    {#if searching}
      <div class="absolute right-2 top-1/2 -translate-y-1/2">
        <div class="w-3 h-3 border border-amber-dim/50 border-t-transparent rounded-full animate-spin"></div>
      </div>
    {/if}
  </div>

  {#if results.length > 0}
    <div class="max-h-48 overflow-y-auto space-y-1 rounded-lg border border-border/20 bg-surface-1/80 p-1">
      {#each results as result (`${result.source}/${result.rig}/${result.model}`)}
        {@const key = `${result.source}/${result.model}`}
        {@const isInstalling = installing === key}
        <div class="flex items-center justify-between gap-2 px-2 py-1.5 rounded hover:bg-surface-2/50 transition-colors">
          <div class="min-w-0 flex-1">
            <div class="text-xs text-text-primary truncate">{result.model}</div>
            <div class="text-[10px] text-text-tertiary truncate">{result.source} · {result.rig}</div>
          </div>
          <button
            onclick={() => handleInstall(result)}
            disabled={installing !== null}
            class="shrink-0 text-[10px] px-2 py-1 rounded bg-amber-dim/20 text-amber-dim hover:bg-amber-dim/30
                   disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {#if isInstalling}
              <span class="animate-pulse">Installing...</span>
            {:else}
              Install
            {/if}
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>
