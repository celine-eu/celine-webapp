<script lang="ts">
  import { Icon } from '$lib/components';
</script>

<section class="assistant">
  <header class="page-header">
    <h1 class="page-title">AI Assistant</h1>
    <p class="page-subtitle">Your energy management companion</p>
  </header>

  <div class="assistant-placeholder">
    <div class="placeholder-icon">
      <Icon name="bot" size={64} />
    </div>
    <h2 class="placeholder-title">Coming Soon</h2>
    <p class="placeholder-text">
      The AI assistant will help you optimize your energy consumption, 
      answer questions about your community, and provide personalized recommendations.
    </p>
    
    <div class="feature-preview">
      <h3 class="feature-preview__title">What you'll be able to do:</h3>
      <ul class="feature-list">
        <li class="feature-item">
          <Icon name="zap" size={18} />
          <span>Get real-time energy optimization tips</span>
        </li>
        <li class="feature-item">
          <Icon name="trending-up" size={18} />
          <span>Analyze your consumption patterns</span>
        </li>
        <li class="feature-item">
          <Icon name="leaf" size={18} />
          <span>Learn about your community's impact</span>
        </li>
        <li class="feature-item">
          <Icon name="bell" size={18} />
          <span>Set up smart alerts and reminders</span>
        </li>
      </ul>
    </div>
  </div>
</section>

<style>
  .assistant {
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

  .assistant-placeholder {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-2xl) var(--space-lg);
    text-align: center;
  }

  .placeholder-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 120px;
    height: 120px;
    margin: 0 auto var(--space-lg);
    background: linear-gradient(135deg, var(--color-primary-light), var(--color-bg-sunken));
    border-radius: 50%;
    color: var(--color-primary);
  }

  .placeholder-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-text);
    margin: 0 0 var(--space-sm);
  }

  .placeholder-text {
    font-size: 1rem;
    color: var(--color-text-secondary);
    max-width: 480px;
    margin: 0 auto var(--space-xl);
    line-height: 1.6;
  }

  .feature-preview {
    background: var(--color-bg-sunken);
    border-radius: var(--radius-md);
    padding: var(--space-lg);
    text-align: left;
    max-width: 400px;
    margin: 0 auto;
  }

  .feature-preview__title {
    font-size: 0.875rem;
    font-weight: 600;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin: 0 0 var(--space-md);
  }

  .feature-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  .feature-item {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    font-size: 0.9375rem;
    color: var(--color-text);
  }

  .feature-item :global(svg) {
    color: var(--color-primary);
    flex-shrink: 0;
  }

  @media (min-width: 640px) {
    .page-title {
      font-size: 1.75rem;
    }

    .assistant-placeholder {
      padding: var(--space-2xl);
    }
  }
</style>
