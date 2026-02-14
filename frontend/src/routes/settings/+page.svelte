<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Settings } from '$lib/api';
  import { requestAndSubscribeWebPush, unsubscribeWebPush } from '$lib/push';
  import { Icon } from '$lib/components';

  let s: Settings | null = null;
  let loading = true;
  let err = '';
  let saved = '';
  let saving = false;
  let pushMsg = '';
  let pushLoading = false;

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
    if (!s || saving) return;
    saving = true;
    saved = '';
    err = '';
    try {
      s = await api.settingsPut(s);
      saved = 'Settings saved successfully!';
      document.documentElement.style.setProperty('--rec-font-scale', String(s.font_scale ?? 1));
      // Clear success message after 3s
      setTimeout(() => saved = '', 3000);
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  async function enablePush() {
    pushLoading = true;
    pushMsg = '';
    try {
      const res = await requestAndSubscribeWebPush();
      pushMsg = res.subscribed ? '✓ Push notifications enabled' : (res.message ?? 'Could not enable push notifications.');
    } catch (e) {
      pushMsg = e instanceof Error ? e.message : String(e);
    } finally {
      pushLoading = false;
    }
  }

  async function disablePush() {
    pushLoading = true;
    pushMsg = '';
    try {
      await unsubscribeWebPush();
      pushMsg = '✓ Push notifications disabled';
    } catch (e) {
      pushMsg = e instanceof Error ? e.message : String(e);
    } finally {
      pushLoading = false;
    }
  }

  function getFontSizeLabel(scale: number): string {
    if (scale <= 0.95) return 'Small';
    if (scale <= 1.05) return 'Default';
    if (scale <= 1.15) return 'Large';
    return 'Extra Large';
  }

  onMount(load);
</script>

<section class="settings">
  <header class="page-header">
    <h1 class="page-title">Settings</h1>
    <p class="page-subtitle">Customize your experience and preferences</p>
  </header>

  {#if loading}
    <div class="settings-skeleton">
      <div class="skeleton-card">
        <div class="skeleton-line" style="width: 40%; height: 1.25rem;"></div>
        <div class="skeleton-line" style="width: 100%; height: 2.5rem; margin-top: 1rem;"></div>
        <div class="skeleton-line" style="width: 100%; height: 2.5rem; margin-top: 0.75rem;"></div>
      </div>
    </div>
  {:else if err}
    <div class="rec-alert rec-alert--danger" role="alert">
      <Icon name="x-circle" size={20} />
      <div>
        <strong>Error loading settings</strong>
        <p>{err}</p>
      </div>
    </div>
  {:else if s}
    <!-- Accessibility Section -->
    <section class="settings-section">
      <header class="settings-section__header">
        <div class="settings-section__icon">
          <Icon name="eye" size={20} />
        </div>
        <div>
          <h2 class="settings-section__title">Accessibility</h2>
          <p class="settings-section__desc">Make the app easier to use</p>
        </div>
      </header>

      <div class="settings-section__content">
        <!-- Simple Mode -->
        <label class="setting-toggle">
          <div class="setting-toggle__info">
            <span class="setting-toggle__label">Simple mode</span>
            <span class="setting-toggle__desc">Reduced layout with actionable info first</span>
          </div>
          <div class="toggle-switch">
            <input type="checkbox" bind:checked={s.simple_mode} on:change={save} />
            <span class="toggle-switch__track"></span>
          </div>
        </label>

        <!-- Font Size -->
        <div class="setting-slider">
          <div class="setting-slider__header">
            <span class="setting-slider__label">Text size</span>
            <span class="setting-slider__value">{getFontSizeLabel(s.font_scale)}</span>
          </div>
          <div class="setting-slider__control">
            <span class="setting-slider__icon setting-slider__icon--small">A</span>
            <input 
              type="range" 
              class="slider-input"
              min="0.9" 
              max="1.3" 
              step="0.05" 
              bind:value={s.font_scale}
              on:change={save}
              aria-label="Text size"
            />
            <span class="setting-slider__icon setting-slider__icon--large">A</span>
          </div>
          <p class="setting-slider__hint">Adjust for easier reading</p>
        </div>
      </div>
    </section>

    <!-- Notifications Section -->
    <section class="settings-section">
      <header class="settings-section__header">
        <div class="settings-section__icon">
          <Icon name="bell" size={20} />
        </div>
        <div>
          <h2 class="settings-section__title">Notifications</h2>
          <p class="settings-section__desc">Control how you receive updates</p>
        </div>
      </header>

      <div class="settings-section__content">
        <!-- Web Push -->
        <div class="setting-action">
          <div class="setting-action__info">
            <span class="setting-action__label">Push notifications</span>
            <span class="setting-action__desc">
              Receive browser notifications for energy alerts
            </span>
          </div>
          <div class="setting-action__buttons">
            <button 
              class="rec-btn rec-btn--primary rec-btn--sm"
              on:click={enablePush}
              disabled={pushLoading}
            >
              {#if pushLoading}
                <span class="spinner"></span>
              {:else}
                <Icon name="bell" size={16} />
              {/if}
              Enable
            </button>
            <button 
              class="rec-btn rec-btn--secondary rec-btn--sm"
              on:click={disablePush}
              disabled={pushLoading}
            >
              Disable
            </button>
          </div>
        </div>

        {#if pushMsg}
          <p class="setting-message" class:setting-message--success={pushMsg.startsWith('✓')}>
            {pushMsg}
          </p>
        {/if}

        <!-- Email Notifications -->
        <label class="setting-toggle setting-toggle--disabled">
          <div class="setting-toggle__info">
            <span class="setting-toggle__label">
              Email notifications
              <span class="coming-soon-badge">Coming soon</span>
            </span>
            <span class="setting-toggle__desc">Receive important updates via email</span>
          </div>
          <div class="toggle-switch">
            <input type="checkbox" bind:checked={s.notifications.email_enabled} disabled />
            <span class="toggle-switch__track"></span>
          </div>
        </label>
      </div>
    </section>

    <!-- Save confirmation -->
    {#if saved}
      <div class="save-toast" role="status" aria-live="polite">
        <Icon name="check-circle" size={18} />
        <span>{saved}</span>
      </div>
    {/if}
  {/if}
</section>

<style>
  .settings {
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
  }

  .page-subtitle {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    margin: 0;
  }

  /* Settings Section */
  .settings-section {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    overflow: hidden;
  }

  .settings-section__header {
    display: flex;
    align-items: flex-start;
    gap: var(--space-sm);
    padding: var(--space-md);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-bg-sunken);
  }

  .settings-section__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: var(--color-primary-light);
    color: var(--color-primary);
    border-radius: var(--radius-md);
  }

  .settings-section__title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
  }

  .settings-section__desc {
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    margin: 2px 0 0;
  }

  .settings-section__content {
    padding: var(--space-md);
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
  }

  /* Setting Toggle */
  .setting-toggle {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-md);
    cursor: pointer;
  }

  .setting-toggle--disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .setting-toggle__info {
    flex: 1;
  }

  .setting-toggle__label {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--color-text);
  }

  .setting-toggle__desc {
    display: block;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    margin-top: 2px;
  }

  /* Toggle Switch */
  .toggle-switch {
    position: relative;
    width: 48px;
    height: 28px;
    flex-shrink: 0;
  }

  .toggle-switch input {
    opacity: 0;
    width: 100%;
    height: 100%;
    position: absolute;
    cursor: pointer;
    z-index: 1;
    margin: 0;
  }

  .toggle-switch__track {
    position: absolute;
    inset: 0;
    background: var(--color-border-strong);
    border-radius: var(--radius-full);
    transition: background var(--transition-fast);
  }

  .toggle-switch__track::after {
    content: '';
    position: absolute;
    top: 3px;
    left: 3px;
    width: 22px;
    height: 22px;
    background: white;
    border-radius: 50%;
    box-shadow: var(--shadow-sm);
    transition: transform var(--transition-fast);
  }

  .toggle-switch input:checked + .toggle-switch__track {
    background: var(--color-primary);
  }

  .toggle-switch input:checked + .toggle-switch__track::after {
    transform: translateX(20px);
  }

  .toggle-switch input:disabled + .toggle-switch__track {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* Setting Slider */
  .setting-slider {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  .setting-slider__header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .setting-slider__label {
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--color-text);
  }

  .setting-slider__value {
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-primary);
  }

  .setting-slider__control {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
  }

  .setting-slider__icon {
    color: var(--color-text-tertiary);
    font-weight: 600;
  }

  .setting-slider__icon--small {
    font-size: 0.75rem;
  }

  .setting-slider__icon--large {
    font-size: 1.25rem;
  }

  .slider-input {
    flex: 1;
    -webkit-appearance: none;
    appearance: none;
    height: 6px;
    background: var(--color-border);
    border-radius: var(--radius-full);
    outline: none;
  }

  .slider-input::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 20px;
    height: 20px;
    background: var(--color-primary);
    border-radius: 50%;
    cursor: pointer;
    box-shadow: var(--shadow-md);
    transition: transform var(--transition-fast);
  }

  .slider-input::-webkit-slider-thumb:hover {
    transform: scale(1.1);
  }

  .slider-input::-moz-range-thumb {
    width: 20px;
    height: 20px;
    background: var(--color-primary);
    border: none;
    border-radius: 50%;
    cursor: pointer;
    box-shadow: var(--shadow-md);
  }

  .setting-slider__hint {
    font-size: 0.8125rem;
    color: var(--color-text-tertiary);
    margin: 0;
  }

  /* Setting Action */
  .setting-action {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  .setting-action__label {
    font-size: 0.9375rem;
    font-weight: 500;
    color: var(--color-text);
  }

  .setting-action__desc {
    display: block;
    font-size: 0.8125rem;
    color: var(--color-text-secondary);
    margin-top: 2px;
  }

  .setting-action__buttons {
    display: flex;
    gap: var(--space-sm);
  }

  /* Setting Message */
  .setting-message {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin: 0;
    padding: var(--space-sm) var(--space-md);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
  }

  .setting-message--success {
    background: var(--color-success-bg);
    color: var(--color-success-text);
  }

  /* Coming Soon Badge */
  .coming-soon-badge {
    display: inline-flex;
    padding: 0.125em 0.5em;
    font-size: 0.625rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-tertiary);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-full);
  }

  /* Save Toast */
  .save-toast {
    position: fixed;
    bottom: calc(72px + var(--space-md) + env(safe-area-inset-bottom, 0px));
    left: 50%;
    transform: translateX(-50%);
    display: inline-flex;
    align-items: center;
    gap: var(--space-sm);
    padding: var(--space-sm) var(--space-md);
    background: var(--color-success);
    color: white;
    font-size: 0.875rem;
    font-weight: 500;
    border-radius: var(--radius-full);
    box-shadow: var(--shadow-lg);
    animation: toast-in 0.3s ease;
    z-index: 100;
  }

  @keyframes toast-in {
    from {
      opacity: 0;
      transform: translateX(-50%) translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateX(-50%) translateY(0);
    }
  }

  /* Spinner */
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid transparent;
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Skeleton */
  .settings-skeleton {
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
  }

  .skeleton-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
  }

  .skeleton-line {
    background: linear-gradient(90deg, var(--skeleton-base) 25%, var(--skeleton-shine) 50%, var(--skeleton-base) 75%);
    background-size: 200% 100%;
    animation: skeleton-shimmer 1.5s ease-in-out infinite;
    border-radius: var(--radius-sm);
  }

  @keyframes skeleton-shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }

  /* Responsive */
  @media (min-width: 640px) {
    .page-title {
      font-size: 1.75rem;
    }

    .settings-section__header {
      padding: var(--space-lg);
    }

    .settings-section__content {
      padding: var(--space-lg);
    }

    .setting-action {
      flex-direction: row;
      justify-content: space-between;
      align-items: center;
    }
  }
</style>
