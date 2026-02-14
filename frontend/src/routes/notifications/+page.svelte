<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type NotificationItem } from '$lib/api';
  import { requestAndSubscribeWebPush } from '$lib/push';
  import { Icon, Skeleton } from '$lib/components';

  let items: NotificationItem[] = [];
  let loading = true;
  let err = '';
  let pushBanner = '';
  
  // Filtering
  type FilterType = 'all' | 'unread' | 'info' | 'warning' | 'critical';
  let activeFilter: FilterType = 'all';

  // Computed filtered items
  $: filteredItems = items.filter(n => {
    if (activeFilter === 'all') return true;
    if (activeFilter === 'unread') return !n.read_at;
    return n.severity === activeFilter;
  });

  $: unreadCount = items.filter(n => !n.read_at).length;

  async function loadAll() {
    loading = true;
    err = '';
    try {
      items = await api.notifications();
    } catch (e) {
      err = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }

  async function markAsRead(id: string) {
    try {
      await api.notificationMarkRead(id);
      // Update local state
      items = items.map(n => n.id === id ? { ...n, read_at: new Date().toISOString() } : n);
    } catch (e) {
      // Silently fail - the API might not support this yet
      console.warn('Mark as read not supported:', e);
      // Still update locally for better UX
      items = items.map(n => n.id === id ? { ...n, read_at: new Date().toISOString() } : n);
    }
  }

  async function markAllAsRead() {
    try {
      await api.notificationMarkAllRead();
      items = items.map(n => ({ ...n, read_at: n.read_at || new Date().toISOString() }));
    } catch (e) {
      // Silently fail - update locally
      console.warn('Mark all as read not supported:', e);
      items = items.map(n => ({ ...n, read_at: n.read_at || new Date().toISOString() }));
    }
  }

  async function enablePush() {
    pushBanner = '';
    try {
      const res = await requestAndSubscribeWebPush();
      if (!res.subscribed) pushBanner = res.message ?? 'Could not enable web push.';
      else pushBanner = 'Push notifications enabled!';
      await loadAll();
    } catch (e) {
      pushBanner = e instanceof Error ? e.message : String(e);
    }
  }

  function formatDate(dateStr: string): string {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function getSeverityIcon(severity: NotificationItem['severity']): 'info' | 'alert-triangle' | 'alert-circle' {
    switch (severity) {
      case 'critical': return 'alert-circle';
      case 'warning': return 'alert-triangle';
      default: return 'info';
    }
  }

  onMount(loadAll);
</script>

<section class="notifications">
  <header class="page-header">
    <div class="page-header__main">
      <h1 class="page-title">Notifications</h1>
      <p class="page-subtitle">Consumption guidance and REC updates</p>
    </div>
    {#if unreadCount > 0}
      <button class="mark-all-btn" on:click={markAllAsRead}>
        <Icon name="check" size={16} />
        Mark all read
      </button>
    {/if}
  </header>

  <!-- Push notification prompts -->
  {#if typeof Notification !== 'undefined'}
    {#if Notification.permission === 'denied'}
      <div class="rec-alert rec-alert--warning">
        <Icon name="bell" size={20} />
        <div>
          <strong>Push notifications blocked</strong>
          <p>Re-enable in your browser settings to receive alerts.</p>
        </div>
      </div>
    {:else if Notification.permission !== 'granted'}
      <div class="rec-alert rec-alert--info push-prompt">
        <Icon name="bell" size={20} />
        <div class="push-prompt__content">
          <strong>Enable push notifications</strong>
          <p>Get real-time alerts for optimal energy consumption times.</p>
        </div>
        <button class="rec-btn rec-btn--primary rec-btn--sm" on:click={enablePush}>
          Enable
        </button>
      </div>
    {/if}
  {/if}

  {#if pushBanner}
    <div class="rec-alert rec-alert--success" role="status" aria-live="polite">
      <Icon name="check-circle" size={20} />
      <span>{pushBanner}</span>
    </div>
  {/if}

  <!-- Filter tabs -->
  <div class="filter-bar">
    <div class="filter-tabs" role="tablist">
      <button 
        class="filter-tab" 
        class:filter-tab--active={activeFilter === 'all'}
        role="tab"
        aria-selected={activeFilter === 'all'}
        on:click={() => activeFilter = 'all'}
      >
        All
        <span class="filter-count">{items.length}</span>
      </button>
      <button 
        class="filter-tab" 
        class:filter-tab--active={activeFilter === 'unread'}
        role="tab"
        aria-selected={activeFilter === 'unread'}
        on:click={() => activeFilter = 'unread'}
      >
        Unread
        {#if unreadCount > 0}
          <span class="filter-count filter-count--badge">{unreadCount}</span>
        {/if}
      </button>
      <button 
        class="filter-tab filter-tab--critical" 
        class:filter-tab--active={activeFilter === 'critical'}
        role="tab"
        aria-selected={activeFilter === 'critical'}
        on:click={() => activeFilter = 'critical'}
      >
        <Icon name="alert-circle" size={14} />
        Critical
      </button>
      <button 
        class="filter-tab filter-tab--warning" 
        class:filter-tab--active={activeFilter === 'warning'}
        role="tab"
        aria-selected={activeFilter === 'warning'}
        on:click={() => activeFilter = 'warning'}
      >
        <Icon name="alert-triangle" size={14} />
        Warning
      </button>
    </div>
  </div>

  <!-- Content -->
  {#if loading}
    <div class="notification-list">
      {#each Array(4) as _}
        <div class="notification-card">
          <div class="notification-card__header">
            <Skeleton variant="avatar" width="32px" height="32px" />
            <div style="flex: 1;">
              <Skeleton variant="text" width="60%" />
              <Skeleton variant="text" width="30%" />
            </div>
          </div>
          <Skeleton variant="text" lines={2} />
        </div>
      {/each}
    </div>
  {:else if err}
    <div class="rec-alert rec-alert--danger" role="alert">
      <Icon name="x-circle" size={20} />
      <div>
        <strong>Error loading notifications</strong>
        <p>{err}</p>
      </div>
    </div>
  {:else if filteredItems.length === 0}
    <div class="empty-state">
      <div class="empty-icon-wrap">
        <Icon name="bell" size={48} />
      </div>
      {#if activeFilter !== 'all'}
        <p class="empty-title">No {activeFilter} notifications</p>
        <p class="empty-text">Try selecting a different filter above.</p>
        <button class="rec-btn rec-btn--secondary rec-btn--sm" on:click={() => activeFilter = 'all'}>
          Show all
        </button>
      {:else}
        <p class="empty-title">No notifications yet</p>
        <p class="empty-text">You'll receive updates about your energy community here.</p>
      {/if}
    </div>
  {:else}
    <div class="notification-list">
      {#each filteredItems as n (n.id)}
        <article 
          class="notification-card notification-card--{n.severity}"
          class:notification-card--unread={!n.read_at}
          role="article"
        >
          <div class="notification-card__indicator"></div>
          
          <div class="notification-card__icon">
            <Icon name={getSeverityIcon(n.severity)} size={20} />
          </div>

          <div class="notification-card__content">
            <header class="notification-card__header">
              <h3 class="notification-card__title">{n.title}</h3>
              <time class="notification-card__time" datetime={n.created_at}>
                {formatDate(n.created_at)}
              </time>
            </header>
            
            <p class="notification-card__body">{n.body}</p>
            
            <footer class="notification-card__footer">
              <span class="rec-badge rec-badge--{n.severity}">
                {n.severity}
              </span>
              
              {#if !n.read_at}
                <button 
                  class="mark-read-btn" 
                  on:click={() => markAsRead(n.id)}
                  aria-label="Mark as read"
                >
                  <Icon name="check" size={14} />
                  Mark read
                </button>
              {:else}
                <span class="read-indicator">
                  <Icon name="check-circle" size={14} />
                  Read
                </span>
              {/if}
            </footer>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .notifications {
    display: flex;
    flex-direction: column;
    gap: var(--space-md);
  }

  /* Page Header */
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-md);
    flex-wrap: wrap;
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

  .mark-all-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.375em;
    padding: 0.5em 0.875em;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    background: var(--color-bg-hover);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .mark-all-btn:hover {
    color: var(--color-text);
    background: var(--color-bg-sunken);
  }

  /* Push Prompt */
  .push-prompt {
    display: flex;
    align-items: center;
    gap: var(--space-md);
  }

  .push-prompt__content {
    flex: 1;
  }

  .push-prompt__content p {
    margin: 0.25rem 0 0;
    font-size: 0.875rem;
  }

  /* Filter Bar */
  .filter-bar {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin: 0 calc(var(--space-md) * -1);
    padding: 0 var(--space-md);
  }

  .filter-tabs {
    display: flex;
    gap: var(--space-xs);
    min-width: max-content;
  }

  .filter-tab {
    display: inline-flex;
    align-items: center;
    gap: 0.375em;
    padding: 0.5em 0.875em;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--color-text-secondary);
    background: transparent;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    cursor: pointer;
    transition: all var(--transition-fast);
    white-space: nowrap;
  }

  .filter-tab:hover {
    color: var(--color-text);
    background: var(--color-bg-hover);
  }

  .filter-tab--active {
    color: var(--color-primary-text);
    background: var(--color-primary);
    border-color: var(--color-primary);
  }

  .filter-tab--active:hover {
    color: var(--color-primary-text);
    background: var(--color-primary-hover);
  }

  .filter-count {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  .filter-tab--active .filter-count {
    color: inherit;
    opacity: 0.8;
  }

  .filter-count--badge {
    background: var(--color-danger);
    color: white;
    padding: 0.125em 0.5em;
    border-radius: var(--radius-full);
    font-weight: 600;
  }

  .filter-tab--active .filter-count--badge {
    background: rgba(255, 255, 255, 0.25);
  }

  /* Notification List */
  .notification-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
  }

  /* Notification Card */
  .notification-card {
    position: relative;
    display: flex;
    gap: var(--space-sm);
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: var(--radius-lg);
    padding: var(--space-md);
    transition: all var(--transition-fast);
  }

  .notification-card:hover {
    box-shadow: var(--shadow-md);
  }

  .notification-card--unread {
    background: var(--color-bg-elevated);
    border-color: var(--color-primary);
    border-left-width: 3px;
  }

  .notification-card__indicator {
    display: none;
  }

  .notification-card__icon {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-md);
    background: var(--color-bg-sunken);
  }

  .notification-card--info .notification-card__icon {
    background: var(--color-info-bg);
    color: var(--color-info-text);
  }

  .notification-card--warning .notification-card__icon {
    background: var(--color-warning-bg);
    color: var(--color-warning-text);
  }

  .notification-card--critical .notification-card__icon {
    background: var(--color-danger-bg);
    color: var(--color-danger-text);
  }

  .notification-card__content {
    flex: 1;
    min-width: 0;
  }

  .notification-card__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-sm);
    margin-bottom: var(--space-xs);
  }

  .notification-card__title {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
    line-height: 1.3;
  }

  .notification-card__time {
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
    white-space: nowrap;
  }

  .notification-card__body {
    font-size: 0.875rem;
    color: var(--color-text-secondary);
    margin: 0 0 var(--space-sm);
    line-height: 1.5;
  }

  .notification-card__footer {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
  }

  .mark-read-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.25em;
    padding: 0.25em 0.5em;
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--color-primary);
    background: transparent;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: all var(--transition-fast);
  }

  .mark-read-btn:hover {
    background: var(--color-primary-light);
  }

  .read-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.25em;
    font-size: 0.75rem;
    color: var(--color-text-tertiary);
  }

  /* Empty State */
  .empty-state {
    text-align: center;
    padding: var(--space-2xl) var(--space-md);
  }

  .empty-icon-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 80px;
    height: 80px;
    margin: 0 auto var(--space-md);
    border-radius: 50%;
    background: var(--color-bg-sunken);
    color: var(--color-text-tertiary);
  }

  .empty-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--color-text);
    margin: 0 0 var(--space-xs);
  }

  .empty-text {
    font-size: 0.9375rem;
    color: var(--color-text-secondary);
    margin: 0 0 var(--space-md);
  }

  /* Responsive */
  @media (min-width: 640px) {
    .page-title {
      font-size: 1.75rem;
    }

    .notification-card {
      padding: var(--space-lg);
    }
  }
</style>
