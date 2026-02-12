<script lang="ts">
  import Spectrum from '$lib/components/viz/Spectrum.svelte';
  import ChainFlow from '$lib/components/chain/ChainFlow.svelte';
  import SpatialSelector from '$lib/components/controls/SpatialSelector.svelte';
  import HeadphoneSelector from '$lib/components/controls/HeadphoneSelector.svelte';
  import HeadphoneSearch from '$lib/components/controls/HeadphoneSearch.svelte';
  import Guide from '$lib/components/learn/Guide.svelte';
  import AudioStackBadge from '$lib/components/stack/AudioStackBadge.svelte';
  import AudioStackModal from '$lib/components/stack/AudioStackModal.svelte';
  import { dspState, loading, error } from '$lib/stores/dsp';
  import { spectrumConnected } from '$lib/stores/spectrum';

  let stackModalOpen = $state(false);
</script>

<svelte:head>
  <title>Aural — Listening Companion</title>
</svelte:head>

<div class="min-h-screen flex flex-col bg-void">
  <!-- Header — minimal, recedes -->
  <header class="flex items-center justify-between px-6 py-4 shrink-0">
    <div class="flex items-center gap-3">
      <h1 class="text-lg font-semibold tracking-tight text-text-primary">
        <span class="text-amber-glow">A</span>ural
      </h1>
      <span class="text-[10px] text-text-tertiary font-mono">listening companion</span>
    </div>
    <div class="flex items-center gap-3">
      {#if $error}
        <span class="text-[10px] text-red-400/80">{$error}</span>
      {/if}
      <div class="flex items-center gap-1.5">
        <div class="w-1.5 h-1.5 rounded-full {$spectrumConnected ? 'bg-green-500/80 animate-breathe' : 'bg-text-tertiary/40'}"></div>
        <span class="text-[10px] text-text-tertiary font-mono">
          {$spectrumConnected ? 'live' : 'offline'}
        </span>
      </div>
    </div>
  </header>

  <!-- Main content -->
  <main class="flex-1 flex flex-col gap-4 px-6 pb-6 overflow-hidden">
    <!-- Spectrum Visualizer — The ambient backdrop -->
    <section class="h-40 md:h-52 shrink-0 glass rounded-xl overflow-hidden">
      <Spectrum />
    </section>

    <!-- Audio Stack Badge — persistent status strip -->
    {#if $dspState}
      <AudioStackBadge onopen={() => stackModalOpen = true} />
    {/if}

    <!-- Signal Chain Flow — Interactive node graph -->
    <section class="relative shrink-0">
      <div class="text-[10px] text-text-tertiary uppercase tracking-wider mb-1 px-1">Signal Chain</div>
      <ChainFlow />
    </section>

    <!-- Controls + Guide — Side by side -->
    <section class="flex-1 grid grid-cols-1 md:grid-cols-[220px_1fr] gap-4 min-h-0">
      <!-- Left: Controls -->
      <div class="glass rounded-xl p-4 space-y-5 overflow-y-auto">
        <SpatialSelector />
        <div class="border-t border-border/50"></div>
        <HeadphoneSearch />
        <div class="border-t border-border/50"></div>
        <HeadphoneSelector />
      </div>

      <!-- Right: Listening Guide -->
      <div class="glass rounded-xl p-5 overflow-y-auto">
        <div class="text-[10px] text-text-tertiary uppercase tracking-wider mb-3">Listening Guide</div>
        {#if $dspState}
          <Guide />
        {:else if $loading}
          <div class="text-xs text-text-tertiary animate-pulse">Loading DSP state...</div>
        {:else}
          <div class="text-xs text-text-tertiary">
            Connect to the backend to see your listening guide.
          </div>
        {/if}
      </div>
    </section>

  </main>
</div>

<!-- Audio Stack Modal — full stack detail overlay -->
<AudioStackModal bind:open={stackModalOpen} />
