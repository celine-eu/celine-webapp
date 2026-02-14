<script lang="ts">
  import { onMount } from 'svelte';
  import { browser } from '$app/environment';
  import Icon from './Icon.svelte';

  let theme: 'light' | 'dark' = 'light';

  function setTheme(newTheme: 'light' | 'dark') {
    theme = newTheme;
    if (browser) {
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('rec-theme', theme);
    }
  }

  function toggle() {
    setTheme(theme === 'light' ? 'dark' : 'light');
  }

  onMount(() => {
    // Check saved preference or system preference
    const saved = localStorage.getItem('rec-theme');
    if (saved === 'dark' || saved === 'light') {
      setTheme(saved);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark');
    }

    // Listen for system preference changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('rec-theme')) {
        setTheme(e.matches ? 'dark' : 'light');
      }
    };
    mediaQuery.addEventListener('change', handler);

    return () => mediaQuery.removeEventListener('change', handler);
  });
</script>

<button
  class="theme-toggle"
  on:click={toggle}
  aria-label="Toggle {theme === 'light' ? 'dark' : 'light'} mode"
  title="Toggle {theme === 'light' ? 'dark' : 'light'} mode"
>
  {#if theme === 'light'}
    <Icon name="moon" size={20} />
  {:else}
    <Icon name="sun" size={20} />
  {/if}
</button>

<style>
  .theme-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-bg-hover);
    color: var(--color-text-secondary);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .theme-toggle:hover {
    background: var(--color-bg-sunken);
    color: var(--color-text);
  }

  .theme-toggle:focus-visible {
    outline: 2px solid var(--color-primary);
    outline-offset: 2px;
  }
</style>
