<script lang="ts">
  import { spatialMode, activeChain, bypassed, dspState, audioFormat } from '$lib/stores/dsp';
  import { SPATIAL_SINK_NAMES } from '@aural/shared';

  let { onopen }: { onopen: () => void } = $props();

  let sinkName = $derived($dspState ? SPATIAL_SINK_NAMES[$spatialMode] : null);
  let filterCount = $derived($activeChain.length);
  let bypassedCount = $derived(($bypassed ?? []).length);
  let formatLabel = $derived.by(() => {
    const fmt = $audioFormat;
    if (!fmt) return null;
    const rate = fmt.sampleRate >= 1000
      ? `${(fmt.sampleRate / 1000).toFixed(fmt.sampleRate % 1000 ? 1 : 0)}kHz`
      : `${fmt.sampleRate}Hz`;
    return `${rate}/${fmt.bitDepth}bit`;
  });
</script>

<button
  onclick={onopen}
  class="w-full glass-subtle rounded-lg px-4 py-2 flex items-center justify-between
         text-[11px] font-mono text-text-tertiary
         hover:text-text-secondary hover:border-amber-dim/30 transition-all duration-300 cursor-pointer group"
>
  <div class="flex items-center gap-2 min-w-0">
    <span class="text-amber-dim group-hover:text-amber-glow transition-colors shrink-0">&#9674;</span>
    <span class="truncate">
      PipeWire
      {#if sinkName}
        <span class="text-text-tertiary/60">&middot;</span>
        {sinkName.replace('effect_input.headphone_dsp', '').replace('_', '') || 'clean'}
      {/if}
      {#if formatLabel}
        <span class="text-text-tertiary/60">&middot;</span>
        <span class="text-amber-dim/80">{formatLabel}</span>
      {/if}
      <span class="text-text-tertiary/60">&middot;</span>
      {filterCount} filter{filterCount !== 1 ? 's' : ''}
      {#if bypassedCount > 0}
        <span class="text-text-tertiary/60">&middot;</span>
        <span class="text-amber-dim/60">{bypassedCount} bypassed</span>
      {/if}
    </span>
  </div>
  <span class="text-text-tertiary/40 group-hover:text-text-tertiary/80 transition-colors shrink-0 ml-2">details &rarr;</span>
</button>
