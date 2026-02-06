<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Settings } from '$lib/api';
  import { requestAndSubscribeWebPush, unsubscribeWebPush } from '$lib/push';

  let s: Settings | null = null;
  let loading = true;
  let err = '';
  let saved = '';
  let pushMsg = '';

  async function load() {
    loading = true;
    err = '';
    saved = '';
    try {
      s = await api.settingsGet();
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function save() {
    if (!s) return;
    saved = '';
    err = '';
    try {
      s = await api.settingsPut(s);
      saved = 'Saved.';
      document.documentElement.style.setProperty('--rec-font-scale', String(s.font_scale ?? 1));
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    }
  }

  async function enablePush() {
    pushMsg = '';
    try {
      const res = await requestAndSubscribeWebPush();
      pushMsg = res.subscribed ? 'Web push enabled.' : (res.message ?? 'Could not enable web push.');
    } catch (e) {
      pushMsg = e instanceof Error ? e.message : String(e);
    }
  }

  async function disablePush() {
    pushMsg = '';
    try {
      await unsubscribeWebPush();
      pushMsg = 'Web push disabled.';
    } catch (e) {
      pushMsg = e instanceof Error ? e.message : String(e);
    }
  }

  onMount(load);
</script>

<section class="block">
  <h1 class="title is-3">Settings</h1>
  <p class="subtitle is-6">Make the app easier to read and configure notifications.</p>

  {#if loading}
    <progress class="progress is-small" max="100">Loading</progress>
  {:else if err}
    <article class="message is-danger" role="alert"><div class="message-body">{err}</div></article>
  {:else if s}
    <div class="box">
      <h2 class="title is-5">Accessibility</h2>

      <div class="field">
        <label class="checkbox">
          <input type="checkbox" bind:checked={s.simple_mode} />
          Simple mode (reduced layout, actionable info first)
        </label>
      </div>

      <div class="field">
        <label class="label">Text size</label>
        <div class="control">
          <input class="slider is-fullwidth" step="0.05" min="0.9" max="1.3" type="range" bind:value={s.font_scale} aria-label="Text size" />
        </div>
        <p class="help">Adjust for easier reading.</p>
      </div>

      <hr />

      <h2 class="title is-5">Notifications</h2>
      <div class="field">
        <label class="label">Web push</label>
        <div class="buttons">
          <button class="button is-link" type="button" on:click={enablePush}>Enable</button>
          <button class="button" type="button" on:click={disablePush}>Disable</button>
        </div>
        <p class="help">Web push requires browser permission. You can always read notifications in the Notifications page.</p>
        {#if pushMsg}
          <p class="has-text-grey">{pushMsg}</p>
        {/if}
      </div>

      <div class="field">
        <label class="checkbox">
          <input type="checkbox" bind:checked={s.notifications.email_enabled} />
          Email notifications (coming soon)
        </label>
      </div>

      <div class="buttons mt-4">
        <button class="button is-primary" type="button" on:click={save}>Save</button>
        {#if saved}<span class="has-text-success">{saved}</span>{/if}
      </div>
    </div>
  {/if}
</section>
