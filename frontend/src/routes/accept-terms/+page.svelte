<script lang="ts">
  import { goto } from '$app/navigation';
  import { api } from '$lib/api';
  import { meStore } from '$lib/stores';
  import { Icon } from '$lib/components';

  let loading = false;
  let err = '';
  let accepted = false;

  async function accept() {
    if (!accepted) {
      err = 'Please read and accept the terms to continue.';
      return;
    }
    loading = true;
    err = '';
    try {
      await api.acceptTerms();
      const me = await api.me();
      meStore.set(me);
      await goto('/');
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }
</script>

<section class="accept-terms">
  <div class="terms-card">
    <div class="terms-icon">
      <Icon name="leaf" size={48} />
    </div>
    
    <h1 class="terms-title">Welcome to REC</h1>
    <p class="terms-subtitle">
      Before you begin, please review and accept our terms and policies.
    </p>

    <div class="terms-links">
      <a href="/terms" class="terms-link">
        <Icon name="chevron-right" size={18} />
        Legal Terms
      </a>
      <a href="/privacy" class="terms-link">
        <Icon name="chevron-right" size={18} />
        Privacy Policy
      </a>
    </div>

    {#if err}
      <div class="rec-alert rec-alert--danger">
        <Icon name="alert-circle" size={18} />
        <span>{err}</span>
      </div>
    {/if}

    <label class="terms-checkbox">
      <input type="checkbox" bind:checked={accepted} />
      <span class="checkbox-mark"></span>
      <span class="checkbox-label">
        I have read and accept the <a href="/terms">Legal Terms</a> and <a href="/privacy">Privacy Policy</a>
      </span>
    </label>

    <button 
      class="accept-btn" 
      on:click={accept} 
      disabled={loading}
    >
      {#if loading}
        <span class="spinner"></span>
        Processing...
      {:else}
        Continue to REC
        <Icon name="chevron-right" size={18} />
      {/if}
    </button>
  </div>
</section>

<style>
  .accept-terms {
    min-height: 80vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-lg);
  }

  .terms-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-xl);
    padding: var(--space-2xl);
    max-width: 440px;
    width: 100%;
    text-align: center;
  }

  .terms-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 80px;
    height: 80px;
    margin: 0 auto var(--space-lg);
    background: var(--color-primary-light);
    color: var(--color-primary);
    border-radius: 50%;
  }

  .terms-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-text);
    margin: 0 0 var(--space-xs);
  }

  .terms-subtitle {
    font-size: 1rem;
    color: var(--color-text-secondary);
    margin: 0 0 var(--space-xl);
    line-height: 1.5;
  }

  .terms-links {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
    margin-bottom: var(--space-lg);
  }

  .terms-link {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: var(--space-md);
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    color: var(--color-text);
    text-decoration: none;
    font-weight: 500;
    transition: all var(--transition-fast);
  }

  .terms-link:hover {
    background: var(--color-bg-hover);
    color: var(--color-primary);
  }

  .terms-checkbox {
    display: flex;
    align-items: flex-start;
    gap: var(--space-sm);
    text-align: left;
    cursor: pointer;
    margin-bottom: var(--space-lg);
  }

  .terms-checkbox input {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
  }

  .checkbox-mark {
    flex-shrink: 0;
    width: 22px;
    height: 22px;
    border: 2px solid var(--color-border-strong);
    border-radius: var(--radius-sm);
    transition: all var(--transition-fast);
    position: relative;
  }

  .checkbox-mark::after {
    content: '';
    position: absolute;
    left: 6px;
    top: 2px;
    width: 6px;
    height: 12px;
    border: solid white;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  .terms-checkbox input:checked + .checkbox-mark {
    background: var(--color-primary);
    border-color: var(--color-primary);
  }

  .terms-checkbox input:checked + .checkbox-mark::after {
    opacity: 1;
  }

  .checkbox-label {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    line-height: 1.4;
  }

  .checkbox-label a {
    color: var(--color-primary);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .accept-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-sm);
    width: 100%;
    padding: var(--space-md) var(--space-lg);
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-primary-text);
    background: var(--color-primary);
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .accept-btn:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }

  .accept-btn:disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid transparent;
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .rec-alert {
    margin-bottom: var(--space-lg);
    text-align: left;
  }
</style>
