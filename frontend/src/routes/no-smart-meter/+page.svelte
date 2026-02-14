<script lang="ts">
  import { Icon } from '$lib/components';
</script>

<section class="no-meter">
  <header class="page-header">
    <h1 class="page-title">Smart Meter Required</h1>
    <p class="page-subtitle">Connect your meter to unlock all features</p>
  </header>

  <div class="info-card">
    <div class="info-icon">
      <Icon name="plug" size={48} />
    </div>
    
    <p class="info-text">
      Most features in this app require a smart meter associated with your account. 
      A smart meter enables real-time energy monitoring and helps you participate 
      fully in your renewable energy community.
    </p>

    <div class="steps">
      <h2 class="steps-title">How to get connected:</h2>
      
      <div class="step">
        <div class="step-number">1</div>
        <div class="step-content">
          <h3 class="step-title">Contact your energy provider</h3>
          <p class="step-text">Request a smart meter installation or check if you already have one.</p>
        </div>
      </div>

      <div class="step">
        <div class="step-number">2</div>
        <div class="step-content">
          <h3 class="step-title">Register your meter</h3>
          <p class="step-text">Once installed, contact your REC administrator with your meter ID.</p>
        </div>
      </div>

      <div class="step">
        <div class="step-number">3</div>
        <div class="step-content">
          <h3 class="step-title">Start monitoring</h3>
          <p class="step-text">Your energy data will appear in the app within 24-48 hours.</p>
        </div>
      </div>
    </div>

    <div class="help-box">
      <Icon name="info" size={20} />
      <div>
        <strong>Need help?</strong>
        <p>Contact your community administrator for assistance with smart meter setup.</p>
      </div>
    </div>
  </div>
</section>

<style>
  .no-meter {
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
  }

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

  .info-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-xl);
  }

  .info-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 80px;
    height: 80px;
    margin: 0 auto var(--space-lg);
    background: var(--color-warning-bg);
    color: var(--color-warning-text);
    border-radius: 50%;
  }

  .info-text {
    font-size: 1rem;
    color: var(--color-text-secondary);
    text-align: center;
    max-width: 540px;
    margin: 0 auto var(--space-xl);
    line-height: 1.6;
  }

  .steps {
    margin-bottom: var(--space-xl);
  }

  .steps-title {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 0 0 var(--space-md);
  }

  .step {
    display: flex;
    gap: var(--space-md);
    padding: var(--space-md) 0;
    border-bottom: 1px solid var(--color-border);
  }

  .step:last-child {
    border-bottom: none;
  }

  .step-number {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: var(--color-primary);
    color: var(--color-primary-text);
    font-weight: 700;
    font-size: 0.875rem;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .step-content {
    flex: 1;
  }

  .step-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0 0 var(--space-xs);
  }

  .step-text {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    margin: 0;
    line-height: 1.5;
  }

  .help-box {
    display: flex;
    gap: var(--space-sm);
    padding: var(--space-md);
    background: var(--color-info-bg);
    border-radius: var(--radius-md);
    color: var(--color-info-text);
  }

  .help-box strong {
    display: block;
    margin-bottom: 2px;
  }

  .help-box p {
    font-size: 0.875rem;
    margin: 0;
    opacity: 0.9;
  }

  @media (min-width: 640px) {
    .page-title {
      font-size: 1.75rem;
    }
  }
</style>
