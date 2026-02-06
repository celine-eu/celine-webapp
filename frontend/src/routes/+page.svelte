<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Overview } from '$lib/api';
  import { meStore } from '$lib/stores';

  let overview: Overview | null = null;
  let err = '';
  let loading = true;

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

<section class="block">
  <h1 class="title is-3">Overview</h1>
  <p class="subtitle is-6">Your renewable energy community participation at a glance.</p>

  {#if $meStore && !$meStore.has_smart_meter}
    <article class="message is-warning" role="status" aria-live="polite">
      <div class="message-body">
        <strong>No smart meter associated.</strong>
        Most features are unavailable.
        <a class="has-text-weight-semibold" href="/no-smart-meter">Learn more</a>.
      </div>
    </article>
  {/if}

  {#if loading}
    <progress class="progress is-small" max="100">Loading</progress>
  {:else if err}
    <article class="message is-danger" role="alert">
      <div class="message-body">{err}</div>
    </article>
  {:else if overview}
    <div class="columns is-multiline">
      <div class="column is-12">
        <div class="box">
          <h2 class="title is-5">Your contribution ({overview.period})</h2>
          <div class="columns is-multiline">
            <div class="column is-4">
              <p class="heading">Consumption</p>
              <p class="title is-4">{overview.user.consumption_kwh.toFixed(1)} kWh</p>
            </div>
            <div class="column is-4">
              <p class="heading">Production</p>
              <p class="title is-4">
                {#if overview.user.production_kwh == null}
                  —
                {:else}
                  {overview.user.production_kwh.toFixed(1)} kWh
                {/if}
              </p>
            </div>
            <div class="column is-4">
              <p class="heading">Self-consumption</p>
              <p class="title is-4">
                {#if overview.user.self_consumption_kwh == null}
                  —
                {:else}
                  {overview.user.self_consumption_kwh.toFixed(1)} kWh
                {/if}
              </p>
              {#if overview.user.self_consumption_rate != null}
                <p class="has-text-grey">{(overview.user.self_consumption_rate * 100).toFixed(0)}%</p>
              {/if}
            </div>
          </div>
          <p class="has-text-grey is-size-7">
            Values are illustrative until the Digital Twin integration is enabled.
          </p>
        </div>
      </div>

      <div class="column is-12">
        <div class="box">
          <h2 class="title is-5">REC trend</h2>
          <div class="table-container">
            <table class="table is-fullwidth is-striped">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Production (kWh)</th>
                  <th scope="col">Consumption (kWh)</th>
                  <th scope="col">Self-consumption (kWh)</th>
                </tr>
              </thead>
              <tbody>
                {#each overview.trend as row}
                  <tr>
                    <td>{row.date}</td>
                    <td>{row.production_kwh.toFixed(1)}</td>
                    <td>{row.consumption_kwh.toFixed(1)}</td>
                    <td>{row.self_consumption_kwh.toFixed(1)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          <p class="has-text-grey is-size-7">
            Charting will be added with an accessible library once real data is available.
          </p>
        </div>
      </div>

      <div class="column is-12">
        <div class="box">
          <h2 class="title is-5">Community totals</h2>
          <div class="columns is-multiline">
            <div class="column is-3">
              <p class="heading">Production</p>
              <p class="title is-5">{overview.rec.production_kwh.toFixed(1)} kWh</p>
            </div>
            <div class="column is-3">
              <p class="heading">Consumption</p>
              <p class="title is-5">{overview.rec.consumption_kwh.toFixed(1)} kWh</p>
            </div>
            <div class="column is-3">
              <p class="heading">Self-consumption</p>
              <p class="title is-5">{overview.rec.self_consumption_kwh.toFixed(1)} kWh</p>
            </div>
            <div class="column is-3">
              <p class="heading">Rate</p>
              <p class="title is-5">{(overview.rec.self_consumption_rate * 100).toFixed(0)}%</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  {/if}
</section>
