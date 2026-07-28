<script lang="ts">
  import { audioStack } from '$lib/content/audio-stack';
  import { fullChain, bypassed, spatialMode, dspState } from '$lib/stores/dsp';
  import { SPATIAL_SINK_NAMES } from '@aural/shared';
  import type { DspStageId } from '@aural/shared';

  let { open = $bindable(false) }: { open: boolean } = $props();

  function close() { open = false; }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') close();
  }

  function isBypassed(id: DspStageId): boolean {
    return ($bypassed ?? []).includes(id as any);
  }

  let activeSink = $derived($dspState ? SPATIAL_SINK_NAMES[$spatialMode] : 'unknown');
  let routedStreams = $derived($dspState?.system.streams ?? []);
  let virtualSinks = $derived(($dspState?.system.sinks ?? []).filter((sink) => sink.role === 'music' || sink.role === 'movie'));

  const typeLabel: Record<string, string> = {
    lv2: 'LV2',
    ladspa: 'LADSPA',
    builtin: 'Built-in',
  };
</script>

<svelte:window onkeydown={handleKeydown} />

{#if open}
  <!-- Backdrop -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 bg-void/80 backdrop-blur-sm"
    onclick={close}
    onkeydown={(e) => e.key === 'Escape' && close()}
  ></div>

  <!-- Modal -->
  <div class="fixed inset-4 md:inset-8 lg:inset-y-8 lg:inset-x-[12%] z-50 glass rounded-xl border-amber-dim/20 shadow-2xl shadow-black/60 flex flex-col overflow-hidden" role="dialog" aria-modal="true" aria-label="Audio Processing Stack">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-border/50 shrink-0">
      <div>
        <h2 class="text-sm font-semibold text-text-primary">Audio Processing Stack</h2>
        <p class="text-[10px] text-text-tertiary font-mono mt-0.5">The software running between your music and your ears</p>
      </div>
      <button onclick={close} class="text-text-tertiary hover:text-text-primary transition-colors text-lg leading-none cursor-pointer px-2">&times;</button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto px-6 py-5 space-y-6">
      <!-- Server -->
      <section>
        <div class="flex items-center gap-2 mb-2">
          <div class="w-1.5 h-1.5 rounded-full bg-green-500/80 animate-breathe"></div>
          <h3 class="text-xs font-semibold text-text-primary uppercase tracking-wider">Server: {audioStack.server.name}</h3>
        </div>
        <p class="text-xs text-text-secondary leading-relaxed">{audioStack.server.description}</p>
        <p class="text-xs text-text-secondary/80 leading-relaxed mt-2 italic">{audioStack.server.whyChosen}</p>
      </section>

      <!-- Architecture -->
      <section>
        <h3 class="text-xs font-semibold text-text-primary uppercase tracking-wider mb-2">Architecture: Virtual Sinks + Hardware Route</h3>
        <p class="text-xs text-text-secondary leading-relaxed">{audioStack.sinkArchitecture}</p>
        <div class="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
          <div class="text-[10px] font-mono text-text-tertiary bg-surface-1/50 rounded-lg px-3 py-2">
            Default music sink: <span class="text-amber-glow">{activeSink}</span>
          </div>
          <div class="text-[10px] font-mono text-text-tertiary bg-surface-1/50 rounded-lg px-3 py-2">
            Live app streams: <span class="text-amber-glow">{routedStreams.length}</span>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap gap-1.5">
          {#each virtualSinks as sink (sink.id)}
            <span class="text-[10px] px-2 py-1 rounded-full border border-border bg-surface-1/60 text-text-secondary">
              {sink.description}
              {#if sink.activeStreams > 0}
                <span class="text-green-400/80 ml-1">{sink.activeStreams}</span>
              {/if}
            </span>
          {/each}
        </div>
      </section>

      <!-- Signal Path -->
      <section>
        <h3 class="text-xs font-semibold text-text-primary uppercase tracking-wider mb-3">Signal Path</h3>
        <div class="space-y-1">
          {#each $fullChain as stageId, i (stageId)}
            {@const plugin = audioStack.plugins[stageId]}
            {@const bp = isBypassed(stageId)}

            {#if i > 0}
              <div class="flex items-center pl-5">
                <svg width="16" height="20" viewBox="0 0 16 20" class="{bp ? 'text-text-tertiary/20' : 'text-amber-dim/50'}">
                  <line x1="8" y1="0" x2="8" y2="14" stroke="currentColor" stroke-width="1.5" stroke-dasharray="3 2" />
                  <polygon points="4,13 8,19 12,13" fill="currentColor" />
                </svg>
              </div>
            {/if}

            <div class="rounded-lg border {bp ? 'border-text-tertiary/15 opacity-40' : 'border-border'} bg-surface-1/30 p-4 transition-all">
              <!-- Plugin header -->
              <div class="flex items-start justify-between gap-3 mb-2">
                <div class="min-w-0">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-xs font-semibold {bp ? 'text-text-tertiary line-through' : 'text-text-primary'}">{plugin.pluginName}</span>
                    <span class="text-[9px] px-1.5 py-0.5 rounded bg-surface-2/80 text-text-tertiary font-mono">{typeLabel[plugin.pluginType]}</span>
                    {#if bp}
                      <span class="text-[9px] px-1.5 py-0.5 rounded bg-red-400/10 text-red-400/70 font-mono">bypassed</span>
                    {/if}
                  </div>
                  <div class="text-[10px] text-text-tertiary mt-0.5">{plugin.developer}</div>
                  {#if plugin.pluginUri}
                    <div class="text-[9px] text-text-tertiary/60 font-mono mt-0.5 truncate">{plugin.pluginUri}</div>
                  {/if}
                </div>
              </div>

              <!-- Why chosen -->
              <div class="mb-3">
                <div class="text-[10px] font-medium text-amber-dim mb-1">Why this plugin:</div>
                <p class="text-[11px] text-text-secondary leading-relaxed">{plugin.whyChosen}</p>
              </div>

              <!-- Key parameters -->
              <div class="grid grid-cols-2 gap-2">
                {#each plugin.keyParameters as param}
                  <div class="bg-surface-0/50 rounded px-2.5 py-1.5">
                    <div class="text-[9px] text-text-tertiary">{param.name}</div>
                    <div class="text-[10px] text-text-primary font-mono">{param.value}</div>
                  </div>
                {/each}
              </div>

              <!-- Technical note -->
              {#if plugin.technicalNote}
                <div class="mt-3 text-[10px] text-text-tertiary/80 leading-relaxed border-t border-border/30 pt-2">
                  {plugin.technicalNote}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      </section>
    </div>
  </div>
{/if}
