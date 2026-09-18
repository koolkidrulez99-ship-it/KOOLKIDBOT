export type NotificationAlertKey =
  | 'tradeOpened'
  | 'tradeClosed'
  | 'accountStatus'
  | 'botStatus'
  | 'copyTrader'
  | 'riskAlerts'
  | 'aiAlerts';

export interface NotificationPrefs {
  enabled: boolean;
  tradeOpened: boolean;
  tradeClosed: boolean;
  accountStatus: boolean;
  botStatus: boolean;
  copyTrader: boolean;
  riskAlerts: boolean;
  aiAlerts: boolean;
}

export const DEFAULT_NOTIFICATION_PREFS: NotificationPrefs = {
  enabled: false,
  tradeOpened: true,
  tradeClosed: true,
  accountStatus: true,
  botStatus: true,
  copyTrader: true,
  riskAlerts: true,
  aiAlerts: true,
};
function swUrl() {
  return `${String(import.meta.env.BASE_URL || '/').replace(/\/?$/, '/') }mt5-notification-sw.js`;
}

export async function ensureNotificationRegistration() {
  if (!('serviceWorker' in navigator)) return null;
  try {
    return await navigator.serviceWorker.register(swUrl());
  } catch {
    return null;
  }
}

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (!('Notification' in window)) return 'denied';
  const permission = await Notification.requestPermission();
  if (permission === 'granted') await ensureNotificationRegistration();
  return permission;
}

export function notificationPermission(): NotificationPermission | 'unsupported' {
  if (!('Notification' in window)) return 'unsupported';
  return Notification.permission;
}
export async function showBrowserNotification(title: string, body: string, tag?: string) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return false;

  const options: NotificationOptions = {
    body,
    tag,
    icon: `${String(import.meta.env.BASE_URL || '/').replace(/\/?$/, '/') }favicon.svg`,
    badge: `${String(import.meta.env.BASE_URL || '/').replace(/\/?$/, '/') }favicon.svg`,
  };

  const registration = await ensureNotificationRegistration();
  if (registration) {
    await registration.showNotification(title, options);
    return true;
  }

  new Notification(title, options);
  return true;
}
