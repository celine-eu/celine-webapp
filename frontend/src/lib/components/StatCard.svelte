<script lang="ts">
  import Icon from './Icon.svelte';

  export let label: string;
  export let value: string;
  export let unit: string = 'kWh';
  export let subtext: string = '';
  export let variant: 'default' | 'production' | 'consumption' | 'self-consumption' = 'default';
  export let icon: 'zap' | 'plug' | 'battery-charging' | 'leaf' | 'activity' | 'trending-up' = 'activity';
  export let trend: 'up' | 'down' | 'neutral' | null = null;
  export let trendValue: string = '';
</script>

<div class="stat-card stat-card--{variant}">
  <div class="stat-card__header">
    <span class="stat-card__icon">
      <Icon name={icon} size={18} />
    </span>
    <span class="stat-card__label">{label}</span>
  </div>
  
  <div class="stat-card__value-row">
    <span class="stat-card__value">{value}</span>
    <span class="stat-card__unit">{unit}</span>
  </div>

  {#if subtext || (trend && trendValue)}
    <div class="stat-card__footer">
      {#if trend && trendValue}
        <span class="stat-card__trend stat-card__trend--{trend}">
          <Icon name={trend === 'up' ? 'trending-up' : trend === 'down' ? 'trending-down' : 'activity'} size={14} />
          {trendValue}
        </span>
      {/if}
      {#if subtext}
        <span class="stat-card__subtext">{subtext}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .stat-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-md);
    transition: all var(--transition-base);
  }

  .stat-card:hover {
    box-shadow: var(--shadow-md);
  }

  .stat-card__header {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    margin-bottom: var(--space-sm);
  }

  .stat-card__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border-radius: var(--radius-sm);
    background: var(--color-bg-sunken);
    color: var(--color-text-secondary);
  }

  .stat-card__label {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--color-text-tertiary);
  }

  .stat-card__value-row {
    display: flex;
    align-items: baseline;
    gap: 0.25em;
  }

  .stat-card__value {
    font-size: 1.75rem;
    font-weight: 700;
    line-height: 1.1;
    color: var(--color-text);
  }

  .stat-card__unit {
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-secondary);
  }

  .stat-card__footer {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin-top: var(--space-sm);
    font-size: 0.8125rem;
  }

  .stat-card__subtext {
    color: var(--color-text-secondary);
  }

  .stat-card__trend {
    display: inline-flex;
    align-items: center;
    gap: 0.25em;
    font-weight: 500;
  }

  .stat-card__trend--up {
    color: var(--color-success);
  }

  .stat-card__trend--down {
    color: var(--color-danger);
  }

  .stat-card__trend--neutral {
    color: var(--color-text-secondary);
  }

  /* Variant colors */
  .stat-card--production .stat-card__icon {
    background: rgba(16, 185, 129, 0.12);
    color: var(--chart-production);
  }
  .stat-card--production .stat-card__value {
    color: var(--chart-production);
  }

  .stat-card--consumption .stat-card__icon {
    background: rgba(245, 158, 11, 0.12);
    color: var(--chart-consumption);
  }
  .stat-card--consumption .stat-card__value {
    color: var(--chart-consumption);
  }

  .stat-card--self-consumption .stat-card__icon {
    background: rgba(59, 130, 246, 0.12);
    color: var(--chart-self-consumption);
  }
  .stat-card--self-consumption .stat-card__value {
    color: var(--chart-self-consumption);
  }

  /* Responsive */
  @media (min-width: 768px) {
    .stat-card {
      padding: var(--space-lg);
    }

    .stat-card__value {
      font-size: 2rem;
    }
  }
</style>
