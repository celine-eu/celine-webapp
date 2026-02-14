<script lang="ts">
  import { page } from "$app/stores";
  import type { Me } from "$lib/api";
  import { meStore } from "$lib/stores";
  import "$lib/styles/bulma";
  import "$lib/styles/theme.css";
  import { onMount } from "svelte";
  import { Icon, ThemeToggle } from "$lib/components";

  export let data: { me: Me | null; needs_terms: boolean };

  $: meStore.set(data.me);

  // Navigation items with icons
  const navItems = [
    { href: '/', label: 'Overview', icon: 'home' as const },
    { href: '/notifications', label: 'Alerts', icon: 'bell' as const },
    { href: '/assistant', label: 'Assistant', icon: 'bot' as const },
    { href: '/settings', label: 'Settings', icon: 'settings' as const },
  ];

  function isActive(href: string, pathname: string): boolean {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  }

  onMount(() => {
    const root = document.documentElement;
    const me = data.me;
    if (me) {
      root.style.setProperty("--rec-font-scale", String(me.font_scale ?? 1));
    } else {
      root.style.setProperty("--rec-font-scale", "1");
    }
  });
</script>

<svelte:head>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap" rel="stylesheet">
</svelte:head>

<div class="app-shell">
  <!-- Top header bar (mobile) -->
  <header class="top-header">
    <div class="top-header__content">
      <div class="top-header__brand">
        <Icon name="leaf" size={24} className="brand-icon" />
        <span class="brand-text">REC</span>
      </div>
      <ThemeToggle />
    </div>
  </header>

  <div class="content-wrap">
    {#if data.me === null}
      <div class="rec-alert rec-alert--warning" role="status" aria-live="polite">
        <Icon name="alert-circle" size={20} className="rec-alert__icon" />
        <div>
          <strong>Backend not reachable.</strong>
          The UI shell is loaded, but data is unavailable.
        </div>
      </div>
    {/if}
    <slot />
  </div>

  <!-- Bottom navigation -->
  <nav class="bottom-nav" aria-label="Primary">
    <div class="bottom-nav__container">
      {#each navItems as item}
        {@const active = isActive(item.href, $page.url.pathname)}
        <a 
          href={item.href} 
          class="nav-item" 
          class:nav-item--active={active}
          aria-current={active ? "page" : undefined}
        >
          <span class="nav-item__icon">
            <Icon name={item.icon} size={22} />
          </span>
          <span class="nav-item__label">{item.label}</span>
        </a>
      {/each}
    </div>
  </nav>
</div>

<style>
  :global(html) {
    font-size: calc(16px * var(--rec-font-scale, 1));
  }

  :global(body) {
    font-family: var(--font-body, 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif);
    background-color: var(--color-bg);
    color: var(--color-text);
    margin: 0;
    padding: 0;
  }

  .app-shell {
    min-height: 100vh;
    min-height: 100dvh;
    padding-top: 56px; /* Header height */
    padding-bottom: 72px; /* Nav height */
  }

  /* Top Header */
  .top-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 56px;
    background: var(--nav-bg);
    border-bottom: 1px solid var(--nav-border);
    z-index: 20;
  }

  .top-header__content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 900px;
    height: 100%;
    margin: 0 auto;
    padding: 0 var(--space-md);
  }

  .top-header__brand {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
  }

  :global(.brand-icon) {
    color: var(--color-primary);
  }

  .brand-text {
    font-size: 1.125rem;
    font-weight: 700;
    color: var(--color-text);
    letter-spacing: -0.01em;
  }

  /* Content */
  .content-wrap {
    max-width: 900px;
    margin: 0 auto;
    padding: var(--space-md);
    padding-top: var(--space-lg);
  }

  /* Bottom Navigation */
  .bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--nav-bg);
    border-top: 1px solid var(--nav-border);
    z-index: 20;
    padding-bottom: env(safe-area-inset-bottom, 0);
  }

  .bottom-nav__container {
    display: flex;
    justify-content: space-around;
    max-width: 500px;
    margin: 0 auto;
  }

  .nav-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: var(--space-sm) var(--space-md);
    text-decoration: none;
    color: var(--nav-text);
    transition: color var(--transition-fast);
    min-width: 64px;
  }

  .nav-item:hover {
    color: var(--color-text);
  }

  .nav-item--active {
    color: var(--nav-text-active);
  }

  .nav-item__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-md);
    transition: background var(--transition-fast);
  }

  .nav-item--active .nav-item__icon {
    background: var(--color-primary-light);
  }

  .nav-item__label {
    font-size: 0.6875rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.02em;
  }

  /* Responsive */
  @media (min-width: 768px) {
    .content-wrap {
      padding: var(--space-xl);
    }

    .nav-item {
      padding: var(--space-sm) var(--space-lg);
    }

    .nav-item__label {
      font-size: 0.75rem;
    }
  }
</style>
