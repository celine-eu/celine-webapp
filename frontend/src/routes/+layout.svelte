<script lang="ts">
  import { page } from "$app/stores";
  import type { Me } from "$lib/api";
  import { meStore } from "$lib/stores";
  import "$lib/styles/bulma";
  import { onMount } from "svelte";

  export let data: { me: Me | null; needs_terms: boolean };

  $: meStore.set(data.me);

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

<div class="app-shell">
  <div class="content-wrap">
    {#if data.me === null}
      <article class="message is-warning" role="status" aria-live="polite">
        <div class="message-body">
          Backend not reachable. The UI shell is loaded, but data is
          unavailable.
        </div>
      </article>
    {/if}
    <slot />
  </div>

  <nav class="bottom-nav" aria-label="Primary">
    <div class="tabs is-fullwidth is-large">
      <ul>
        <li class:has-text-weight-semibold={$page.url.pathname === "/"}>
          <a
            href="/"
            aria-current={$page.url.pathname === "/" ? "page" : undefined}
            >Overview</a
          >
        </li>
        <li
          class:has-text-weight-semibold={$page.url.pathname.startsWith(
            "/notifications",
          )}
        >
          <a
            href="/notifications"
            aria-current={$page.url.pathname.startsWith("/notifications")
              ? "page"
              : undefined}>Notifications</a
          >
        </li>
        <li
          class:has-text-weight-semibold={$page.url.pathname.startsWith(
            "/assistant",
          )}
        >
          <a
            href="/assistant"
            aria-current={$page.url.pathname.startsWith("/assistant")
              ? "page"
              : undefined}>Assistant</a
          >
        </li>
        <li
          class:has-text-weight-semibold={$page.url.pathname.startsWith(
            "/settings",
          )}
        >
          <a
            href="/settings"
            aria-current={$page.url.pathname.startsWith("/settings")
              ? "page"
              : undefined}>Settings</a
          >
        </li>
      </ul>
    </div>
  </nav>
</div>

<style>
  :global(html) {
    font-size: calc(16px * var(--rec-font-scale, 1));
  }
  .app-shell {
    min-height: 100vh;
    padding-bottom: 4.25rem;
  }
  .bottom-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    border-top: 1px solid #e5e5e5;
    background: white;
    z-index: 10;
  }
  .bottom-nav .tabs {
    margin-bottom: 0;
  }
  .content-wrap {
    max-width: 900px;
    margin: 0 auto;
    padding: 1rem;
  }
</style>
