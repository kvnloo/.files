<script lang="ts">
  import { fullChain, activeChain, dspState, bypassed, toggleBypass } from '$lib/stores/dsp';
  import { dspStages } from '$lib/content/dsp-stages';
  import { audioStack } from '$lib/content/audio-stack';
  import type { DspStageContent } from '$lib/content/dsp-stages';
  import type { AudioPlugin } from '$lib/content/audio-stack';
  import type { DspStageId, BypassableStageId } from '@aural/shared';

  const BYPASSABLE: BypassableStageId[] = ['crossfeed', 'brir', 'loudness', 'mbc'];

  let expandedStage: DspStageId | null = $state(null);
  let contextMenu: { x: number; y: number; stageId: DspStageId } | null = $state(null);

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

  function isBypassed(stageId: DspStageId): boolean {
    return ($bypassed ?? []).includes(stageId as BypassableStageId);
  }

  function canBypass(stageId: DspStageId): boolean {
    return BYPASSABLE.includes(stageId as BypassableStageId);
  }

  function handleContextMenu(e: MouseEvent, stageId: DspStageId) {
    if (!canBypass(stageId)) return;
    e.preventDefault();
    contextMenu = { x: e.clientX, y: e.clientY, stageId };
  }

  function handleBypassClick(stageId: DspStageId) {
    contextMenu = null;
    toggleBypass(stageId as BypassableStageId);
  }

  function closeContextMenu() {
    contextMenu = null;
  }

  function getExpandedContent(stageId: DspStageId | null): DspStageContent | null {
    return stageId ? dspStages[stageId] : null;
  }

  function getExpandedPlugin(stageId: DspStageId | null): AudioPlugin | null {
    return stageId ? audioStack.plugins[stageId] : null;
  }

  let expandedContent: DspStageContent | null = $derived(getExpandedContent(expandedStage));
  let expandedPlugin: AudioPlugin | null = $derived(getExpandedPlugin(expandedStage));
</script>

<svelte:window onclick={closeContextMenu} />

<div class="relative">
  <!-- Chain node row -->
  <div class="flex items-center gap-2 overflow-x-auto py-4 px-2 scrollbar-none">
    {#each $fullChain as stageId, i (stageId)}
      {@const stage = dspStages[stageId]}
      {@const isExpanded = expandedStage === stageId}
      {@const isBp = isBypassed(stageId)}

      {#if i > 0}
        <div class="flex items-center shrink-0">
          <svg width="24" height="12" viewBox="0 0 24 12" class="{isBp ? 'text-text-tertiary/30' : 'text-amber-dim'}">
            <line x1="0" y1="6" x2="18" y2="6" stroke="currentColor" stroke-width="1.5" stroke-dasharray="4 3" />
            <polygon points="17,2 23,6 17,10" fill="currentColor" />
          </svg>
        </div>
      {/if}

      <button
        onclick={() => toggleStage(stageId)}
        oncontextmenu={(e) => handleContextMenu(e, stageId)}
        class="group relative shrink-0 glass rounded-lg px-4 py-3 transition-all duration-300 cursor-pointer
               hover:border-amber-dim/50 {isExpanded ? 'glow-amber border-amber-dim/40' : ''}
               {isBp ? 'opacity-35 border-dashed !border-text-tertiary/30' : ''}"
        style="--stage-color: {stage.color}"
      >
        <!-- Active indicator dot -->
        {#if !isBp}
          <div class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full animate-pulse-glow"
               style="background: {stage.color}"></div>
        {/if}

        <div class="text-xs font-medium {isBp ? 'text-text-tertiary line-through' : 'text-text-primary'}">{stage.shortName}</div>
        <div class="text-[10px] text-text-tertiary mt-0.5 font-mono">{isBp ? 'bypassed' : getStageLabel(stageId)}</div>

        {#if canBypass(stageId)}
          <div class="absolute -bottom-1 left-1/2 -translate-x-1/2 text-[8px] text-text-tertiary/0 group-hover:text-text-tertiary/60 transition-all">
            right-click
          </div>
        {/if}
      </button>
    {/each}
  </div>

  <!-- Context menu -->
  {#if contextMenu}
    {@const isBp = isBypassed(contextMenu.stageId)}
    <div
      class="fixed z-50 glass rounded-lg border border-amber-dim/30 shadow-xl shadow-black/60 py-1 min-w-[160px]"
      style="left: {contextMenu.x}px; top: {contextMenu.y}px"
      role="menu"
    >
      <button
        class="w-full text-left px-3 py-2 text-xs hover:bg-amber-ghost/30 transition-colors cursor-pointer flex items-center gap-2"
        onclick={() => handleBypassClick(contextMenu!.stageId)}
        role="menuitem"
      >
        {#if isBp}
          <span class="text-green-400">&#10003;</span>
          <span class="text-text-secondary">Enable {dspStages[contextMenu.stageId].shortName}</span>
        {:else}
          <span class="text-red-400">&#10007;</span>
          <span class="text-text-secondary">Bypass {dspStages[contextMenu.stageId].shortName}</span>
        {/if}
      </button>
      <div class="px-3 py-1.5 text-[10px] text-text-tertiary border-t border-surface-2/50">
        Rewrites PipeWire filter chain in real-time
      </div>
    </div>
  {/if}

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

      <!-- Audio Stack — plugin details -->
      {#if expandedPlugin}
        {@const plugin = expandedPlugin}
        <div class="mt-4 pt-3 border-t border-border/30">
          <div class="text-[10px] font-medium text-amber-dim uppercase tracking-wider mb-2">Audio Stack</div>
          <div class="flex items-center gap-2 mb-1.5">
            <span class="text-xs text-text-primary font-medium">{plugin.pluginName}</span>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-surface-2/80 text-text-tertiary font-mono">
              {plugin.pluginType === 'lv2' ? 'LV2' : plugin.pluginType === 'ladspa' ? 'LADSPA' : 'Built-in'}
            </span>
          </div>
          <div class="text-[10px] text-text-tertiary mb-2">{plugin.developer}</div>
          <p class="text-[11px] text-text-secondary leading-relaxed mb-2">{plugin.whyChosen}</p>
          <div class="grid grid-cols-2 gap-1.5">
            {#each plugin.keyParameters as param}
              <div class="bg-surface-0/50 rounded px-2 py-1">
                <span class="text-[9px] text-text-tertiary">{param.name}:</span>
                <span class="text-[10px] text-text-primary font-mono ml-1">{param.value}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>
