<script lang="ts">
  import { api, type Overview } from "$lib/api";
  import { meStore } from "$lib/stores";
  import { onMount } from "svelte";
  import { Icon, Skeleton, StatCard, EnergyChart } from "$lib/components";

  let overview: Overview | null = null;
  let err = "";
  let loading = true;

  /** Format a number to 1 decimal place, or return "—" for null/undefined */
  function fmt(value: number | null | undefined): string {
    return value != null ? value.toFixed(1) : "—";
  }

  /** Format a percentage (0-1 scale) to whole number with %, or return "—" for null */
  function fmtPct(value: number | null | undefined): string {
    return value != null ? `${(value * 100).toFixed(0)}%` : "—";
  }

  /** Check if user has any data */
  function hasUserData(user: Overview['user']): boolean {
    return user.consumption_kwh !== null || 
           user.production_kwh !== null || 
           user.self_consumption_kwh !== null;
  }

  /** Check if REC has any data */
  function hasRecData(rec: Overview['rec']): boolean {
    return rec.consumption_kwh !== null || 
           rec.production_kwh !== null || 
           rec.self_consumption_kwh !== null;
  }

  onMount(async () => {
    try {
      overview = await api.overview();
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });
</script>

<section class="overview">
  <header class="page-header">
    <h1 class="page-title">Overview</h1>
    <p class="page-subtitle">
      Your renewable energy community at a glance
    </p>
  </header>

  {#if $meStore && !$meStore.has_smart_meter}
    <div class="rec-alert rec-alert--warning" role="status" aria-live="polite">
      <Icon name="alert-triangle" size={20} />
      <div>
        <strong>No smart meter associated.</strong>
        Most features are unavailable.
        <a href="/no-smart-meter" class="alert-link">Learn more →</a>
      </div>
    </div>
  {/if}

  {#if loading}
    <!-- Loading skeletons -->
    <div class="section-card">
      <Skeleton variant="heading" width="50%" />
      <div class="stats-grid" style="margin-top: var(--space-lg);">
        <Skeleton variant="stat" />
        <Skeleton variant="stat" />
        <Skeleton variant="stat" />
      </div>
    </div>

    <div class="section-card" style="margin-top: var(--space-lg);">
      <Skeleton variant="heading" width="40%" />
      <div style="margin-top: var(--space-lg);">
        <Skeleton variant="chart" height="280px" />
      </div>
    </div>

  {:else if err}
    <div class="rec-alert rec-alert--danger" role="alert">
      <Icon name="x-circle" size={20} />
      <div>
        <strong>Error loading data</strong>
        <p style="margin: 0.25rem 0 0;">{err}</p>
      </div>
    </div>

  {:else if overview}
    <!-- User Stats Section -->
    <section class="section-card">
      <header class="section-header">
        <Icon name="zap" size={22} className="section-icon" />
        <div>
          <h2 class="section-title">Your Contribution</h2>
          <p class="section-period">{overview.period}</p>
        </div>
      </header>

      {#if hasUserData(overview.user)}
        <div class="stats-grid">
          <StatCard
            label="Consumption"
            value={fmt(overview.user.consumption_kwh)}
            unit="kWh"
            variant="consumption"
            icon="plug"
          />
          <StatCard
            label="Production"
            value={fmt(overview.user.production_kwh)}
            unit="kWh"
            variant="production"
            icon="zap"
          />
          <StatCard
            label="Self-consumption"
            value={fmt(overview.user.self_consumption_kwh)}
            unit="kWh"
            variant="self-consumption"
            icon="battery-charging"
            subtext={overview.user.self_consumption_rate != null 
              ? `${fmtPct(overview.user.self_consumption_rate)} of consumption` 
              : ''}
          />
        </div>
      {:else}
        <div class="empty-state">
          <Icon name="activity" size={40} className="empty-icon" />
          <p class="empty-title">No personal data available</p>
          <p class="empty-text">Your energy data will appear here once your smart meter is connected.</p>
        </div>
      {/if}
    </section>

    <!-- REC Trend Section -->
    <section class="section-card">
      <header class="section-header">
        <Icon name="trending-up" size={22} className="section-icon" />
        <div>
          <h2 class="section-title">Community Trend</h2>
          <p class="section-period">Last 7 days</p>
        </div>
      </header>

      {#if overview.trend.length > 0}
        <div class="chart-container">
          <EnergyChart data={overview.trend} height="280px" />
        </div>

        <!-- Trend Table (collapsible on mobile) -->
        <details class="trend-details">
          <summary class="trend-summary">
            <Icon name="chevron-right" size={18} className="trend-chevron" />
            <span>View detailed data</span>
          </summary>
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th class="num">Production</th>
                  <th class="num">Consumption</th>
                  <th class="num">Self-cons.</th>
                </tr>
              </thead>
              <tbody>
                {#each overview.trend as row}
                  <tr>
                    <td>{new Date(row.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</td>
                    <td class="num production">{fmt(row.production_kwh)}</td>
                    <td class="num consumption">{fmt(row.consumption_kwh)}</td>
                    <td class="num self-consumption">{fmt(row.self_consumption_kwh)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </details>
      {:else}
        <div class="empty-state">
          <Icon name="activity" size={40} className="empty-icon" />
          <p class="empty-title">No trend data available</p>
          <p class="empty-text">Historical data will appear here as it becomes available.</p>
        </div>
      {/if}
    </section>

    <!-- Community Totals Section -->
    <section class="section-card">
      <header class="section-header">
        <Icon name="leaf" size={22} className="section-icon" />
        <div>
          <h2 class="section-title">Community Totals</h2>
          <p class="section-period">{overview.period}</p>
        </div>
      </header>

      {#if hasRecData(overview.rec)}
        <div class="stats-grid stats-grid--4">
          <StatCard
            label="Production"
            value={fmt(overview.rec.production_kwh)}
            unit="kWh"
            variant="production"
            icon="zap"
          />
          <StatCard
            label="Consumption"
            value={fmt(overview.rec.consumption_kwh)}
            unit="kWh"
            variant="consumption"
            icon="plug"
          />
          <StatCard
            label="Self-consumed"
            value={fmt(overview.rec.self_consumption_kwh)}
            unit="kWh"
            variant="self-consumption"
            icon="battery-charging"
          />
          <StatCard
            label="SC Rate"
            value={fmtPct(overview.rec.self_consumption_rate)}
            unit=""
            variant="self-consumption"
            icon="activity"
          />
        </div>
      {:else}
        <div class="empty-state">
          <Icon name="leaf" size={40} className="empty-icon" />
          <p class="empty-title">No community data available</p>
          <p class="empty-text">Community energy data will appear here.</p>
        </div>
      {/if}
    </section>
  {/if}
</section>

<style>
  .overview {
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
  }

  /* Page Header */
  .page-header {
    margin-bottom: var(--space-sm);
  }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-text);
    margin: 0 0 var(--space-xs);
    line-height: 1.2;
  }

  .page-subtitle {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    margin: 0;
  }

  /* Section Card */
  .section-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-md);
  }

  .section-header {
    display: flex;
    align-items: flex-start;
    gap: var(--space-sm);
    margin-bottom: var(--space-lg);
  }

  :global(.section-icon) {
    color: var(--color-primary);
    margin-top: 2px;
  }

  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
    line-height: 1.3;
  }

  .section-period {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin: 2px 0 0;
  }

  /* Stats Grid */
  .stats-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--space-md);
  }

  /* Chart */
  .chart-container {
    margin-top: var(--space-sm);
  }

  /* Trend Details */
  .trend-details {
    margin-top: var(--space-lg);
    border-top: 1px solid var(--color-border);
    padding-top: var(--space-md);
  }

  .trend-summary {
    display: flex;
    align-items: center;
    gap: var(--space-xs);
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    list-style: none;
  }

  .trend-summary::-webkit-details-marker {
    display: none;
  }

  :global(.trend-chevron) {
    transition: transform var(--transition-fast);
  }

  .trend-details[open] :global(.trend-chevron) {
    transform: rotate(90deg);
  }

  .trend-summary:hover {
    color: var(--color-text);
  }

  .table-wrapper {
    margin-top: var(--space-md);
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  /* Data Table */
  .data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.8125rem;
  }

  .data-table th,
  .data-table td {
    padding: var(--space-sm);
    text-align: left;
    border-bottom: 1px solid var(--color-border);
  }

  .data-table th {
    font-weight: 600;
    color: var(--color-text-secondary);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .data-table td {
    color: var(--color-text);
  }

  .data-table .num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }

  .data-table .production { color: var(--chart-production); }
  .data-table .consumption { color: var(--chart-consumption); }
  .data-table .self-consumption { color: var(--chart-self-consumption); }

  /* Empty State */
  .empty-state {
    text-align: center;
    padding: var(--space-xl) var(--space-md);
  }

  :global(.empty-icon) {
    color: var(--color-text-tertiary);
    opacity: 0.5;
    margin-bottom: var(--space-sm);
  }

  .empty-title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0 0 var(--space-xs);
  }

  .empty-text {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin: 0;
  }

  /* Alert Link */
  .alert-link {
    color: inherit;
    font-weight: 600;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .alert-link:hover {
    text-decoration: none;
  }

  /* Responsive */
  @media (min-width: 640px) {
    .stats-grid {
      grid-template-columns: repeat(3, 1fr);
    }

    .stats-grid--4 {
      grid-template-columns: repeat(4, 1fr);
    }

    .section-card {
      padding: var(--space-lg);
    }

    .page-title {
      font-size: 1.75rem;
    }
  }

  @media (min-width: 768px) {
    .section-card {
      padding: var(--space-xl);
    }

    .section-title {
      font-size: 1.125rem;
    }
  }
</style>
