<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { browser } from '$app/environment';

  type TrendItem = {
    date: string;
    production_kwh: number | null;
    consumption_kwh: number | null;
    self_consumption_kwh: number | null;
  };

  export let data: TrendItem[] = [];
  export let height: string = '280px';

  let canvas: HTMLCanvasElement;
  let chart: any = null;

  // Format date for display
  function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  }

  // Short format for mobile
  function formatDateShort(dateStr: string): string {
    const date = new Date(dateStr);
    return date.toLocaleDateString(undefined, { weekday: 'short' });
  }

  async function createChart() {
    if (!browser || !canvas) return;

    // Dynamically import Chart.js
    const { Chart, registerables } = await import('chart.js');
    Chart.register(...registerables);

    // Get CSS variables for theming
    const styles = getComputedStyle(document.documentElement);
    const productionColor = styles.getPropertyValue('--chart-production').trim() || '#10b981';
    const consumptionColor = styles.getPropertyValue('--chart-consumption').trim() || '#f59e0b';
    const selfConsumptionColor = styles.getPropertyValue('--chart-self-consumption').trim() || '#3b82f6';
    const gridColor = styles.getPropertyValue('--chart-grid').trim() || 'rgba(0,0,0,0.06)';
    const textColor = styles.getPropertyValue('--color-text-secondary').trim() || '#64748b';

    const labels = data.map(d => formatDateShort(d.date));
    const isMobile = window.innerWidth < 640;

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Production',
            data: data.map(d => d.production_kwh),
            backgroundColor: productionColor,
            borderRadius: 4,
            borderSkipped: false,
          },
          {
            label: 'Consumption',
            data: data.map(d => d.consumption_kwh),
            backgroundColor: consumptionColor,
            borderRadius: 4,
            borderSkipped: false,
          },
          {
            label: 'Self-consumption',
            data: data.map(d => d.self_consumption_kwh),
            backgroundColor: selfConsumptionColor,
            borderRadius: 4,
            borderSkipped: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          intersect: false,
          mode: 'index',
        },
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              usePointStyle: true,
              pointStyle: 'circle',
              padding: 16,
              color: textColor,
              font: {
                size: isMobile ? 11 : 12,
                family: "'DM Sans', sans-serif",
              },
            },
          },
          tooltip: {
            backgroundColor: 'rgba(15, 23, 42, 0.9)',
            titleColor: '#f1f5f9',
            bodyColor: '#cbd5e1',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            cornerRadius: 8,
            padding: 12,
            titleFont: {
              size: 13,
              weight: '600',
            },
            bodyFont: {
              size: 12,
            },
            callbacks: {
              title: (items) => {
                const idx = items[0]?.dataIndex;
                if (idx !== undefined) {
                  return formatDate(data[idx].date);
                }
                return '';
              },
              label: (item) => {
                const value = item.raw as number | null;
                if (value === null || value === undefined) return `${item.dataset.label}: —`;
                return `${item.dataset.label}: ${value.toFixed(1)} kWh`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: {
              display: false,
            },
            ticks: {
              color: textColor,
              font: {
                size: isMobile ? 10 : 11,
                family: "'DM Sans', sans-serif",
              },
            },
          },
          y: {
            beginAtZero: true,
            grid: {
              color: gridColor,
            },
            ticks: {
              color: textColor,
              font: {
                size: isMobile ? 10 : 11,
                family: "'DM Sans', sans-serif",
              },
              callback: (value) => `${value} kWh`,
            },
          },
        },
      },
    });
  }

  function destroyChart() {
    if (chart) {
      chart.destroy();
      chart = null;
    }
  }

  // Watch for theme changes
  function handleThemeChange() {
    destroyChart();
    createChart();
  }

  onMount(() => {
    createChart();

    // Listen for theme changes
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'data-theme') {
          handleThemeChange();
        }
      });
    });

    observer.observe(document.documentElement, { attributes: true });

    return () => {
      observer.disconnect();
      destroyChart();
    };
  });

  onDestroy(() => {
    destroyChart();
  });

  // Recreate chart when data changes
  $: if (browser && canvas && data.length > 0) {
    destroyChart();
    createChart();
  }
</script>

<div class="energy-chart" style:height>
  <canvas bind:this={canvas}></canvas>
</div>

<style>
  .energy-chart {
    position: relative;
    width: 100%;
  }

  .energy-chart canvas {
    width: 100% !important;
  }
</style>
