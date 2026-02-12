<script lang="ts">
  import { spatialMode } from '$lib/stores/dsp';
  import { spatialModes } from '$lib/content/spatial-modes';

  let currentMode = $derived(spatialModes[$spatialMode]);

  // Characteristic bar visualization
  function charBar(score: number, max = 5): string {
    return '█'.repeat(score) + '░'.repeat(max - score);
  }
</script>

<div class="space-y-4">
  <!-- Mode description -->
  <div>
    <h3 class="text-sm font-semibold text-text-primary mb-1">{currentMode.name}</h3>
    <p class="text-xs text-text-secondary leading-relaxed">{currentMode.description}</p>
  </div>

  <!-- Listen for prompts -->
  <div>
    <div class="flex items-center gap-1.5 mb-2">
      <span class="text-amber-glow text-sm">&#127911;</span>
      <span class="text-xs font-medium text-amber-glow">What to listen for</span>
    </div>
    <ul class="space-y-1.5">
      {#each currentMode.listenFor as prompt}
        <li class="text-xs text-text-secondary flex items-start gap-2 leading-relaxed">
          <span class="text-amber-dim/60 mt-0.5 shrink-0">&#8226;</span>
          <span>{prompt}</span>
        </li>
      {/each}
    </ul>
  </div>

  <!-- Characteristics -->
  <div class="space-y-2">
    <div class="text-xs font-medium text-text-tertiary">Characteristics</div>

    <div class="grid gap-1.5">
      <div class="flex items-center justify-between text-[11px]">
        <span class="text-text-tertiary w-20">Soundstage</span>
        <span class="font-mono text-amber-dim tracking-widest">{charBar(currentMode.characteristics.soundstage.width)}</span>
        <span class="text-text-tertiary text-[10px] w-28 text-right">{currentMode.characteristics.soundstage.label}</span>
      </div>
      <div class="flex items-center justify-between text-[11px]">
        <span class="text-text-tertiary w-20">Detail</span>
        <span class="font-mono text-amber-dim tracking-widest">{charBar(currentMode.characteristics.detail.score)}</span>
        <span class="text-text-tertiary text-[10px] w-28 text-right">{currentMode.characteristics.detail.label}</span>
      </div>
      <div class="flex items-center justify-between text-[11px]">
        <span class="text-text-tertiary w-20">Naturalness</span>
        <span class="font-mono text-amber-dim tracking-widest">{charBar(currentMode.characteristics.naturalness.score)}</span>
        <span class="text-text-tertiary text-[10px] w-28 text-right">{currentMode.characteristics.naturalness.label}</span>
      </div>
      <div class="flex items-center justify-between text-[11px]">
        <span class="text-text-tertiary w-20">Fatigue</span>
        <span class="font-mono text-amber-dim tracking-widest">{charBar(currentMode.characteristics.fatigue.score)}</span>
        <span class="text-text-tertiary text-[10px] w-28 text-right">{currentMode.characteristics.fatigue.label}</span>
      </div>
    </div>
  </div>

  <!-- Vocabulary badges -->
  <div class="flex flex-wrap gap-1.5 pt-1">
    {#each ['Soundstage', 'Imaging', 'Externalization'] as term}
      <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-ghost text-amber-warm border border-amber-dim/20 cursor-help"
            title="Click to learn more">
        {term}
      </span>
    {/each}
  </div>
</div>
