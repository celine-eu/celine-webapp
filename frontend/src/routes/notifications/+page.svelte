<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type NotificationItem } from '$lib/api';
  import { requestAndSubscribeWebPush } from '$lib/push';

  let items: NotificationItem[] = [];
  let loading = true;
  let err = '';
  let permission: NotificationPermission = 'default';
  let pushBanner = '';

  async function loadAll() {
    loading = true;
    err = '';
    try {
      items = await api.notifications();
      permission = Notification?.permission ?? 'default';
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function enablePush() {
    pushBanner = '';
    try {
      const res = await requestAndSubscribeWebPush();
      if (!res.subscribed) pushBanner = res.message ?? 'Could not enable web push.';
      await loadAll();
    } catch (e) {
      pushBanner = e instanceof Error ? e.message : String(e);
    }
  }

  onMount(loadAll);
</script>

<section class="block">
  <h1 class="title is-3">Notifications</h1>
  <p class="subtitle is-6">Consumption guidance and REC updates.</p>

  {#if typeof Notification !== 'undefined'}
    {#if Notification.permission === 'denied'}
      <article class="message is-warning" role="status" aria-live="polite">
        <div class="message-body">
          <strong>Web push is blocked in your browser.</strong>
          You can still read notifications here, but you won’t receive prompts.
          Re-enable notifications in your browser site settings, then return to this page.
        </div>
      </article>
    {:else if Notification.permission !== 'granted'}
      <article class="message is-info" role="status" aria-live="polite">
        <div class="message-body">
          <strong>Enable web push</strong> to receive “when to consume” indications.
          <button class="button is-link is-small ml-2" on:click={enablePush}>Enable</button>
        </div>
      </article>
    {/if}
  {/if}

  {#if pushBanner}
    <article class="message is-warning" role="status" aria-live="polite">
      <div class="message-body">{pushBanner}</div>
    </article>
  {/if}

  {#if loading}
    <progress class="progress is-small" max="100">Loading</progress>
  {:else if err}
    <article class="message is-danger" role="alert"><div class="message-body">{err}</div></article>
  {:else}
    {#if items.length === 0}
      <div class="box">
        <p class="has-text-grey">No notifications yet.</p>
      </div>
    {:else}
      <div class="block">
        {#each items as n (n.id)}
          <div class="box">
            <div class="level is-mobile">
              <div class="level-left">
                <div class="level-item">
                  <p class="title is-6">{n.title}</p>
                </div>
              </div>
              <div class="level-right">
                <div class="level-item">
                  <span class="tag is-light">{new Date(n.created_at).toLocaleString()}</span>
                </div>
              </div>
            </div>
            <p>{n.body}</p>
            <div class="mt-2">
              {#if n.severity === 'critical'}
                <span class="tag is-danger">Critical</span>
              {:else if n.severity === 'warning'}
                <span class="tag is-warning">Warning</span>
              {:else}
                <span class="tag is-info">Info</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</section>
