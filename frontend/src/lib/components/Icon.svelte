<script lang="ts">
  /**
   * Icon component - renders inline SVG icons
   * Uses a subset of Lucide icons, embedded for zero dependencies
   */
  export let name: 
    | 'home' | 'bell' | 'bot' | 'settings' | 'sun' | 'moon'
    | 'zap' | 'plug' | 'battery-charging' | 'leaf'
    | 'trending-up' | 'trending-down' | 'activity'
    | 'check' | 'x' | 'alert-circle' | 'info' | 'alert-triangle'
    | 'chevron-right' | 'chevron-down' | 'filter' | 'search'
    | 'clock' | 'calendar' | 'refresh-cw' | 'eye' | 'eye-off'
    | 'circle' | 'check-circle' | 'x-circle';
  
  export let size: number = 24;
  export let strokeWidth: number = 2;
  export let className: string = '';

  const icons: Record<string, string> = {
    // Navigation
    'home': 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22V12h6v10',
    'bell': 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9 M13.73 21a2 2 0 0 1-3.46 0',
    'bot': 'M12 8V4H8 M12 8V4h4 M12 8a4 4 0 0 0-4 4v4a4 4 0 0 0 8 0v-4a4 4 0 0 0-4-4z M6 12h.01 M18 12h.01 M9 16h6',
    'settings': 'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    'sun': 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M12 2v2 M12 20v2 M4.93 4.93l1.41 1.41 M17.66 17.66l1.41 1.41 M2 12h2 M20 12h2 M6.34 17.66l-1.41 1.41 M19.07 4.93l-1.41 1.41',
    'moon': 'M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z',

    // Energy
    'zap': 'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
    'plug': 'M12 22v-5 M9 8V2 M15 8V2 M18 8H6a2 2 0 0 0-2 2v2c0 4 3.5 7 8 7s8-3 8-7v-2a2 2 0 0 0-2-2z',
    'battery-charging': 'M15 7h1a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-1 M6 7H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2 M22 11v2 M7 10l3 2-3 2v-4z M13 7v10',
    'leaf': 'M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12',

    // Trends
    'trending-up': 'M23 6l-9.5 9.5-5-5L1 18 M17 6h6v6',
    'trending-down': 'M23 18l-9.5-9.5-5 5L1 6 M17 18h6v-6',
    'activity': 'M22 12h-4l-3 9L9 3l-3 9H2',

    // Status
    'check': 'M20 6L9 17l-5-5',
    'x': 'M18 6L6 18 M6 6l12 12',
    'alert-circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 8v4 M12 16h.01',
    'info': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 16v-4 M12 8h.01',
    'alert-triangle': 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z M12 9v4 M12 17h.01',
    
    // Circles
    'circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z',
    'check-circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M9 12l2 2 4-4',
    'x-circle': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M15 9l-6 6 M9 9l6 6',

    // UI
    'chevron-right': 'M9 18l6-6-6-6',
    'chevron-down': 'M6 9l6 6 6-6',
    'filter': 'M22 3H2l8 9.46V19l4 2v-8.54L22 3z',
    'search': 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35',
    'clock': 'M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z M12 6v6l4 2',
    'calendar': 'M19 4H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z M16 2v4 M8 2v4 M3 10h18',
    'refresh-cw': 'M23 4v6h-6 M1 20v-6h6 M3.51 9a9 9 0 0 1 14.85-3.36L23 10 M1 14l4.64 4.36A9 9 0 0 0 20.49 15',
    'eye': 'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    'eye-off': 'M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94 M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19 M1 1l22 22 M14.12 14.12a3 3 0 1 1-4.24-4.24',
  };
</script>

<svg
  class="rec-icon {className}"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={strokeWidth}
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  <path d={icons[name] || icons['circle']} />
</svg>

<style>
  .rec-icon {
    flex-shrink: 0;
    display: inline-block;
    vertical-align: middle;
  }
</style>
