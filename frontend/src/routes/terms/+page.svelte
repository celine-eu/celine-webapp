<script lang="ts">
  import { Icon } from '$lib/components';
</script>

<section class="terms-page">
  <header class="page-header">
    <a href="/" class="back-link">
      <Icon name="chevron-right" size={18} className="back-icon" />
      Back
    </a>
    <h1 class="page-title">Legal Terms</h1>
  </header>

  <div class="content-card">
    <p class="placeholder-text">
      This is a stub page. Replace with your official Legal Terms text.
    </p>
    
    <p class="placeholder-text">
      Your terms of service should include information about:
    </p>
    
    <ul class="placeholder-list">
      <li>Acceptance of terms</li>
      <li>User responsibilities</li>
      <li>Service description</li>
      <li>Intellectual property</li>
      <li>Limitation of liability</li>
      <li>Termination conditions</li>
      <li>Governing law</li>
    </ul>
  </div>
</section>

<style>
  .terms-page {
    display: flex;
    flex-direction: column;
    gap: var(--space-lg);
  }

  .back-link {
    display: inline-flex;
    align-items: center;
    gap: var(--space-xs);
    font-size: 0.875rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    text-decoration: none;
    margin-bottom: var(--space-sm);
  }

  .back-link:hover {
    color: var(--color-primary);
  }

  :global(.back-icon) {
    transform: rotate(180deg);
  }

  .page-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--color-text);
    margin: 0;
  }

  .content-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-xl);
  }

  .placeholder-text {
    font-size: 1rem;
    color: var(--color-text-secondary);
    line-height: 1.6;
    margin: 0 0 var(--space-md);
  }

  .placeholder-list {
    color: var(--color-text-secondary);
    padding-left: var(--space-lg);
    margin: 0;
  }

  .placeholder-list li {
    margin-bottom: var(--space-sm);
  }

  @media (min-width: 640px) {
    .page-title {
      font-size: 1.75rem;
    }
  }
</style>
