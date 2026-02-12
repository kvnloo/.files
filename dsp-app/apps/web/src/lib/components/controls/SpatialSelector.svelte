<script lang="ts">
  import { spatialMode, switchSpatialMode, loading } from '$lib/stores/dsp';
  import { spatialModes } from '$lib/content/spatial-modes';
  import type { SpatialMode } from '@aural/shared';

  const modes: SpatialMode[] = ['clean', 'crossfeed', 'room'];
</script>

<div class="space-y-2">
  <h3 class="text-xs font-medium text-text-tertiary uppercase tracking-wider px-1">Spatial</h3>
  <div class="space-y-1.5">
    {#each modes as mode (mode)}
      {@const content = spatialModes[mode]}
      {@const isActive = $spatialMode === mode}
      <button
        onclick={() => switchSpatialMode(mode)}
        disabled={$loading}
        class="w-full text-left px-3 py-2.5 rounded-lg transition-all duration-300 group
               {isActive
                 ? 'glass glow-amber border-amber-dim/30'
                 : 'hover:bg-surface-2/50 border border-transparent'}"
      >
        <div class="flex items-center gap-2.5">
          <span class="text-base {isActive ? 'text-amber-glow' : 'text-text-tertiary group-hover:text-text-secondary'} transition-colors">
            {content.icon}
          </span>
          <div class="min-w-0">
            <div class="text-sm font-medium {isActive ? 'text-text-primary' : 'text-text-secondary'} transition-colors">
              {content.name}
            </div>
            <div class="text-[10px] {isActive ? 'text-amber-dim' : 'text-text-tertiary'} transition-colors truncate">
              {content.tagline}
            </div>
          </div>
        </div>
      </button>
    {/each}
  </div>
</div>
