<script lang="ts">
  import { eqProfile, switchEqProfile, loading, profiles, removeHeadphone } from '$lib/stores/dsp';

  let switching = $state(false);
  let removing = $state<string | null>(null);

  async function handleSwitch(profileId: string) {
    if (profileId === $eqProfile || switching) return;
    switching = true;
    await switchEqProfile(profileId);
    switching = false;
  }

  async function handleRemove(e: Event, profileId: string) {
    e.stopPropagation();
    removing = profileId;
    await removeHeadphone(profileId);
    removing = null;
  }
</script>

<div class="space-y-2">
  <h3 class="text-xs font-medium text-text-tertiary uppercase tracking-wider px-1">Headphones</h3>
  <div class="space-y-1.5">
    {#each $profiles as profile (profile.id)}
      {@const isActive = $eqProfile === profile.id}
      <div class="relative group rounded-lg transition-all duration-300
                  {isActive
                    ? 'glass glow-amber border-amber-dim/30'
                    : 'hover:bg-surface-2/50 border border-transparent'}">
        <button
          onclick={() => handleSwitch(profile.id)}
          disabled={$loading || switching}
          class="w-full text-left px-3 py-2.5"
        >
          <div class="flex items-center gap-1.5">
            <div class="text-sm font-medium {isActive ? 'text-text-primary' : 'text-text-secondary'} transition-colors truncate">
              {profile.name}
            </div>
            {#if !profile.builtin}
              <span class="shrink-0 text-[9px] px-1 py-0.5 rounded bg-amber-dim/15 text-amber-dim/70">custom</span>
            {/if}
          </div>
          <div class="text-[10px] {isActive ? 'text-amber-dim' : 'text-text-tertiary'} transition-colors truncate">
            {profile.character}
          </div>
        </button>
        {#if !profile.builtin}
          <button
            onclick={(e) => handleRemove(e, profile.id)}
            disabled={removing === profile.id}
            class="absolute top-1.5 right-1.5 text-[10px] text-text-tertiary hover:text-red-400
                   opacity-0 group-hover:opacity-100 transition-opacity p-1"
            title="Remove profile"
          >
            {#if removing === profile.id}
              ...
            {:else}
              ✕
            {/if}
          </button>
        {/if}
      </div>
    {/each}
  </div>

  {#if switching}
    <div class="text-[10px] text-amber-dim/70 px-1 animate-pulse">
      Restarting PipeWire...
    </div>
  {/if}
</div>
