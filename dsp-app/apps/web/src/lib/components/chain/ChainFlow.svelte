<script lang="ts">
  import { activeChain, dspState } from '$lib/stores/dsp';
  import { dspStages } from '$lib/content/dsp-stages';
  import type { DspStageId } from '@aural/shared';

  let expandedStage: DspStageId | null = $state(null);

  function toggleStage(id: DspStageId) {
    expandedStage = expandedStage === id ? null : id;
  }

  function getStageLabel(id: DspStageId): string {
    const s = $dspState;
    if (!s) return '';
    switch (id) {
      case 'autoeq': return s.eqProfile === 'monarch' ? 'Monarch MKII' : 'HD800S';
      case 'crossfeed': return 'bs2b 700 Hz';
      case 'brir': return s.brirRoom === 'R02' ? 'WDR Control Room' : 'ASH Listening Room';
      case 'loudness': return 'ISO 226';
      case 'mbc': return '8-band Bark';
      case 'limiter': return `${s.limiter.ceiling} dB`;
      default: return '';
    }
  }

  let expandedContent = $derived(expandedStage ? dspStages[expandedStage] : null);
</script>

<div class="relative">
  <!-- Chain node row -->
  <div class="flex items-center gap-2 overflow-x-auto py-4 px-2 scrollbar-none">
    {#each $activeChain as stageId, i (stageId)}
      {@const stage = dspStages[stageId]}
      {@const isExpanded = expandedStage === stageId}

      {#if i > 0}
        <div class="flex items-center shrink-0">
          <svg width="24" height="12" viewBox="0 0 24 12" class="text-amber-dim">
            <line x1="0" y1="6" x2="18" y2="6" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" />
            <polygon points="17,2 23,6 17,10" fill="currentColor" />
          </svg>
        </div>
      {/if}

      <button
        onclick={() => toggleStage(stageId)}
        class="group relative shrink-0 glass rounded-lg px-4 py-3 transition-all duration-300 cursor-pointer
               hover:border-amber-dim/50 {isExpanded ? 'glow-amber border-amber-dim/40' : ''}"
        style="--stage-color: {stage.color}"
      >
        <!-- Active indicator dot -->
        <div class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full animate-pulse-glow"
             style="background: {stage.color}"></div>

        <div class="text-xs font-medium text-text-primary">{stage.shortName}</div>
        <div class="text-[10px] text-text-tertiary mt-0.5 font-mono">{getStageLabel(stageId)}</div>
      </button>
    {/each}
  </div>

  <!-- Expanded detail panel — rendered outside the flex row -->
  {#if expandedContent}
    {@const stage = expandedContent}
    <div class="glass rounded-xl p-5 mt-1 border-amber-dim/20 shadow-lg shadow-black/40">
      <div class="flex items-start justify-between mb-3">
        <div>
          <h3 class="text-sm font-semibold text-text-primary">{stage.name}</h3>
          <p class="text-xs text-text-secondary mt-1 max-w-lg">{stage.whatItDoes}</p>
        </div>
        <button onclick={() => expandedStage = null} class="text-text-tertiary hover:text-text-primary transition-colors text-lg leading-none cursor-pointer">&times;</button>
      </div>

      <div class="mt-3 space-y-2">
        <div class="text-xs font-medium text-amber-glow">What to listen for:</div>
        <ul class="space-y-1">
          {#each stage.listenFor as prompt}
            <li class="text-xs text-text-secondary flex items-start gap-2">
              <span class="text-amber-dim mt-0.5 shrink-0">&#9834;</span>
              <span>{prompt}</span>
            </li>
          {/each}
        </ul>
      </div>

      <div class="mt-3 flex flex-wrap gap-1.5">
        {#each stage.vocabulary as term}
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-amber-ghost text-amber-warm border border-amber-dim/20">
            {term}
          </span>
        {/each}
      </div>

      <div class="mt-3 grid grid-cols-2 gap-3 text-xs">
        <div class="bg-surface-1/50 rounded-lg p-2.5">
          <div class="text-text-tertiary mb-1">You gain</div>
          <div class="text-text-secondary">{stage.tradeoff.gain}</div>
        </div>
        <div class="bg-surface-1/50 rounded-lg p-2.5">
          <div class="text-text-tertiary mb-1">You trade</div>
          <div class="text-text-secondary">{stage.tradeoff.sacrifice}</div>
        </div>
      </div>
    </div>
  {/if}
</div>
