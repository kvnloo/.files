<script lang="ts">
  import { eqProfile, switchEqProfile, loading } from '$lib/stores/dsp';
  import { EQ_PROFILES, type EqProfile } from '@aural/shared';

  const profiles: EqProfile[] = ['monarch', 'hd800s'];

  let switching = $state(false);

  async function handleSwitch(profile: EqProfile) {
    if (profile === $eqProfile || switching) return;
    switching = true;
    await switchEqProfile(profile);
    switching = false;
  }
</script>

<div class="space-y-2">
  <h3 class="text-xs font-medium text-text-tertiary uppercase tracking-wider px-1">Headphones</h3>
  <div class="space-y-1.5">
    {#each profiles as profile (profile)}
      {@const info = EQ_PROFILES[profile]}
      {@const isActive = $eqProfile === profile}
      <button
        onclick={() => handleSwitch(profile)}
        disabled={$loading || switching}
        class="w-full text-left px-3 py-2.5 rounded-lg transition-all duration-300 group
               {isActive
                 ? 'glass glow-amber border-amber-dim/30'
                 : 'hover:bg-surface-2/50 border border-transparent'}"
      >
        <div class="text-sm font-medium {isActive ? 'text-text-primary' : 'text-text-secondary'} transition-colors">
          {info.name}
        </div>
        <div class="text-[10px] {isActive ? 'text-amber-dim' : 'text-text-tertiary'} transition-colors">
          {info.character}
        </div>
      </button>
    {/each}
  </div>

  {#if switching}
    <div class="text-[10px] text-amber-dim/70 px-1 animate-pulse">
      Restarting PipeWire...
    </div>
  {/if}
</div>
