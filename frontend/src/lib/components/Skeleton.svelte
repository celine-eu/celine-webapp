<script lang="ts">
  /**
   * Skeleton component for loading states
   */
  export let variant: 'text' | 'heading' | 'stat' | 'chart' | 'card' | 'circle' | 'avatar' = 'text';
  export let width: string = '';
  export let height: string = '';
  export let lines: number = 1;
</script>

{#if variant === 'card'}
  <div class="rec-skeleton-card">
    <div class="rec-skeleton rec-skeleton--heading" style="width: 40%"></div>
    <div class="rec-skeleton-card__stats">
      {#each Array(3) as _}
        <div class="rec-skeleton-stat">
          <div class="rec-skeleton rec-skeleton--text" style="width: 60%; height: 0.75rem;"></div>
          <div class="rec-skeleton rec-skeleton--stat"></div>
        </div>
      {/each}
    </div>
  </div>
{:else if variant === 'chart'}
  <div class="rec-skeleton rec-skeleton--chart" style:height></div>
{:else if variant === 'stat'}
  <div class="rec-skeleton-stat">
    <div class="rec-skeleton rec-skeleton--text" style="width: 50%; height: 0.75rem; margin: 0 auto;"></div>
    <div class="rec-skeleton rec-skeleton--stat" style="margin-top: 0.5rem;"></div>
  </div>
{:else if variant === 'circle' || variant === 'avatar'}
  <div 
    class="rec-skeleton" 
    style="width: {width || '40px'}; height: {height || '40px'}; border-radius: 50%;"
  ></div>
{:else if variant === 'heading'}
  <div class="rec-skeleton rec-skeleton--heading" style:width></div>
{:else}
  <!-- Text lines -->
  {#each Array(lines) as _, i}
    <div 
      class="rec-skeleton rec-skeleton--text" 
      style="width: {i === lines - 1 && lines > 1 ? '70%' : width || '100%'}; margin-bottom: {i < lines - 1 ? '0.5rem' : '0'};"
    ></div>
  {/each}
{/if}

<style>
  .rec-skeleton-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
  }

  .rec-skeleton-card__stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-md);
    margin-top: var(--space-lg);
  }

  .rec-skeleton-stat {
    text-align: center;
  }

  @media (max-width: 640px) {
    .rec-skeleton-card__stats {
      grid-template-columns: 1fr;
    }
  }
</style>
