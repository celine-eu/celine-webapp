export type Me = {
  user: { sub: string; email?: string; name?: string };
  has_smart_meter: boolean;
  terms_required: boolean;
  policy_version: string;
  accepted_policy_version?: string | null;
  simple_mode: boolean;
  font_scale: number;
  notification_permission: 'default' | 'granted' | 'denied';
  webpush_configured: boolean;
};

export type OverviewUser = {
  production_kwh: number | null;
  consumption_kwh: number | null;
  self_consumption_kwh: number | null;
  self_consumption_rate: number | null;
};

export type OverviewRec = {
  production_kwh: number | null;
  consumption_kwh: number | null;
  self_consumption_kwh: number | null;
  self_consumption_rate: number | null;
};

export type TrendItem = {
  date: string;
  production_kwh: number | null;
  consumption_kwh: number | null;
  self_consumption_kwh: number | null;
};

export type Overview = {
  period: string;
  user: OverviewUser;
  rec: OverviewRec;
  trend: TrendItem[];
};

export type NotificationItem = {
  id: string;
  created_at: string;
  title: string;
  body: string;
  severity: 'info' | 'warning' | 'critical';
  read_at?: string | null;
};

export type Settings = {
  simple_mode: boolean;
  font_scale: number;
  notifications: {
    email_enabled: boolean;
  };
};

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    credentials: 'include',
    headers: {
      'content-type': 'application/json',
      ...(init?.headers ?? {})
    }
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}${txt ? `: ${txt}` : ''}`);
  }
  return (await res.json()) as T;
}

export const api = {
  me: () => j<Me>('/api/me'),
  overview: () => j<Overview>('/api/overview'),
  notifications: () => j<NotificationItem[]>('/api/notifications'),
  notificationMarkRead: (id: string) => 
    j<{ ok: true }>(`/api/notifications/${id}/read`, { method: 'POST' }),
  notificationMarkAllRead: () => 
    j<{ ok: true }>('/api/notifications/read-all', { method: 'POST' }),
  acceptTerms: () => j<{ ok: true }>('/api/terms/accept', { method: 'POST', body: JSON.stringify({ accept: true }) }),
  settingsGet: () => j<Settings>('/api/settings'),
  settingsPut: (s: Settings) => j<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(s) }),
  vapidPublicKey: () => j<{ public_key: string }>('/api/notifications/webpush/vapid-public-key'),
  subscribeWebPush: (subscription: PushSubscriptionJSON) =>
    j<{ ok: true }>('/api/notifications/webpush/subscribe', { method: 'POST', body: JSON.stringify(subscription) }),
  unsubscribeWebPush: (endpoint: string) =>
    j<{ ok: true }>('/api/notifications/webpush/unsubscribe', { method: 'POST', body: JSON.stringify({ endpoint }) }),
  enableNotifications: () => j<{ ok: true }>('/api/notifications/enable', { method: 'POST', body: JSON.stringify({ enable: true }) })
};
