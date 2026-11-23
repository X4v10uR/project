import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { Bell } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { SnoozeButton } from '../finance/NotificationSettings';

const endpoint = '/api/dashboard/notifications/';
const pagePath = '/dashboard/notifications/';

type Notification = {
  id: number;
  title: string;
  body: string;
  link_url: string;
  is_read: boolean;
  created_at: string;
};

type UnreadCount = { unread_count: number };
type NotificationList = UnreadCount & {
  notifications: Notification[];
  notifications_ws_enabled: boolean;
  next: string | null;
};

type NotificationsState = {
  data: NotificationList | null;
  error: string;
  saving: boolean;
  loadingOlder: boolean;
  refresh: () => Promise<void>;
  loadOlder: () => Promise<void>;
  markRead: (id?: number) => Promise<void>;
};

const NotificationsContext = createContext<NotificationsState | null>(null);

export function NotificationsProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<NotificationList | null>(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const requestNumber = useRef(0);
  const pageCount = useRef(1);
  const loadingOlderRef = useRef(false);
  const [loadingOlder, setLoadingOlder] = useState(false);

  const refresh = useCallback(async () => {
    const thisRequest = ++requestNumber.current;
    try {
      let result = await api<NotificationList>(endpoint);
      for (let page = 1; page < pageCount.current && result.next; page++) {
        if (thisRequest !== requestNumber.current) return;
        // The API may return its backend origin when running behind Vite.
        const query = new URL(result.next, window.location.origin).search;
        const older = await api<NotificationList>(endpoint + query);
        const notifications = [...new Map([...result.notifications, ...older.notifications].map((item) => [item.id, item])).values()];
        result = { ...result, next: older.next, notifications };
      }
      if (thisRequest !== requestNumber.current) return;
      setData(result);
      setError('');
    } catch {
      if (thisRequest === requestNumber.current) setError('Could not load notifications.');
    }
  }, []);

  useEffect(() => {
    void refresh();
    // Keep a fallback even with an open socket: timed snoozes and changes made
    // by another process may not emit an event on an in-memory channel layer.
    const poll = window.setInterval(() => void refresh(), 15000);
    const onVisible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('online', onVisible);
    return () => {
      window.clearInterval(poll);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('online', onVisible);
      requestNumber.current++;
    };
  }, [refresh]);

  const wsEnabled = data?.notifications_ws_enabled;
  useEffect(() => {
    if (!wsEnabled || !window.WebSocket) return;

    const url = new URL('/ws/notifications/', window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    let socket: WebSocket | undefined;
    let reconnectTimer: number | undefined;
    let reconnectDelay = 4000;

    function connect() {
      try {
        socket = new WebSocket(url);
      } catch {
        // Browser security settings can reject construction; polling continues.
        return;
      }
      socket.onopen = () => {
        reconnectDelay = 4000;
        void refresh();
      };
      socket.onmessage = () => void refresh();
      socket.onclose = (event) => {
        if (event.code === 4401) return;
        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 60000);
      };
    }

    connect();
    return () => {
      window.clearTimeout(reconnectTimer);
      if (!socket) return;
      socket.onopen = socket.onmessage = socket.onclose = null;
      socket.close();
    };
  }, [refresh, wsEnabled]);

  async function loadOlder() {
    if (!data?.next || loadingOlderRef.current) return;
    loadingOlderRef.current = true;
    setLoadingOlder(true);
    pageCount.current++;
    try {
      await refresh();
    } finally {
      loadingOlderRef.current = false;
      setLoadingOlder(false);
    }
  }

  async function markRead(id?: number) {
    setSaving(true);
    setError('');
    try {
      const path = id === undefined ? 'read-all/' : `${id}/read/`;
      const result = await api<UnreadCount>(`${endpoint}${path}`, { method: 'POST' });
      requestNumber.current++;
      setData((current) => current && {
        ...current,
        ...result,
        notifications: current.notifications.map((item) => (
          id === undefined || item.id === id ? { ...item, is_read: true } : item
        )),
      });
      void refresh();
    } catch {
      setError('Could not mark notifications as read.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <NotificationsContext.Provider value={{ data, error, saving, loadingOlder, refresh, loadOlder, markRead }}>
      {children}
    </NotificationsContext.Provider>
  );
}

function useNotifications() {
  const context = useContext(NotificationsContext);
  if (!context) throw new Error('NotificationsProvider is required.');
  return context;
}

function NotificationContents({ item }: { item: Notification }) {
  return (
    <>
      <p className="wrap-anywhere font-semibold text-slate-900">{item.title}</p>
      {item.body && <p className="mt-1 wrap-anywhere text-sm text-slate-600">{item.body}</p>}
      <time className="mt-2 block text-xs text-slate-500" dateTime={item.created_at}>
        {new Date(item.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
      </time>
    </>
  );
}

export function NotificationBell() {
  const { data, error, saving, refresh, markRead } = useNotifications();
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const count = data?.unread_count ?? 0;

  useEffect(() => {
    if (!open) return;
    function handleOutside(event: PointerEvent) {
      if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false);
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false);
        button.current?.focus();
      }
    }
    document.addEventListener('pointerdown', handleOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('pointerdown', handleOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  async function openNotification(item: Notification) {
    if (!item.is_read) await markRead(item.id);
    if (item.link_url) {
      setOpen(false);
      navigate(item.link_url);
    }
  }

  return (
    <div className="relative" ref={container}>
      <button
        aria-expanded={open}
        aria-label={count ? `Notifications, ${count} unread` : 'Notifications'}
        className="relative inline-flex size-10 items-center justify-center rounded-full text-slate-700 hover:bg-slate-100"
        onClick={() => {
          setOpen(!open);
          if (!open) void refresh();
        }}
        ref={button}
        type="button"
      >
        <Bell aria-hidden="true" className="size-5" />
        {count > 0 && (
          <span aria-hidden="true" className="absolute -right-1 top-0 min-w-4 rounded-full bg-emerald-700 px-1 text-center text-[10px] font-bold leading-4 text-white">
            {count > 99 ? '99+' : count}
          </span>
        )}
      </button>
      {open && (
        <section aria-label="Recent notifications" className="absolute right-0 z-30 mt-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 p-3">
            <h2 className="font-semibold text-slate-900">Notifications</h2>
            <button className="text-sm font-medium text-emerald-800 hover:underline disabled:opacity-50" disabled={saving || !count} onClick={() => void markRead()} type="button">Mark all as read</button>
          </div>
          {error && <p className="px-3 py-2 text-sm text-red-800" role="alert">{error}</p>}
          <div className="max-h-80 overflow-auto">
            {data?.notifications.slice(0, 20).map((item) => (
              <button className={`block w-full border-b border-slate-100 px-3 py-2 text-left text-sm hover:bg-slate-100 disabled:opacity-70 ${item.is_read ? '' : 'bg-emerald-50'}`} disabled={saving} key={item.id} onClick={() => void openNotification(item)} type="button">
                <NotificationContents item={item} />
              </button>
            ))}
            {data?.notifications.length === 0 && <p className="p-3 text-sm text-slate-500">No notifications yet.</p>}
            {!data && !error && <p className="p-3 text-sm text-slate-500" role="status">Loading notifications…</p>}
          </div>
          <Link className="block p-3 text-center text-sm font-semibold text-emerald-800 hover:underline" onClick={() => setOpen(false)} to={pagePath}>View all notifications</Link>
        </section>
      )}
    </div>
  );
}

export function NotificationsPage() {
  const { data, error, saving, loadingOlder, markRead, refresh, loadOlder } = useNotifications();
  return (
    <section className="mx-auto w-[calc(100%-2rem)] max-w-4xl rounded-3xl border border-slate-200 bg-white p-5 sm:p-7">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Notifications</h1>
        <Link className="text-sm font-semibold text-indigo-700 underline" to="/planning/alerts/">Notification preferences</Link>
        <button className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50" disabled={saving || !data?.unread_count} onClick={() => void markRead()} type="button">
          Mark all as read
        </button>
      </div>
      {error && (
        <div className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-800" role="alert">
          {error} <button className="font-semibold underline" onClick={() => void refresh()} type="button">Refresh</button>
        </div>
      )}
      {!data && !error && <p className="text-sm text-slate-500" role="status">Loading notifications…</p>}
      {data?.notifications.length === 0 && <p className="text-sm text-slate-500">No notifications yet.</p>}
      <div className="space-y-3">
        {data?.notifications.map((item) => (
          <article className={`rounded-2xl border p-4 ${item.is_read ? 'border-slate-200 bg-white' : 'border-emerald-100 bg-emerald-50'}`} key={item.id}>
            <NotificationContents item={item} />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2 text-sm font-semibold text-emerald-800">
              {item.link_url && <Link className="hover:underline" onClick={() => { if (!item.is_read) void markRead(item.id); }} to={item.link_url}>Open</Link>}
              {!item.is_read && <button className="hover:underline disabled:opacity-50" disabled={saving} onClick={() => void markRead(item.id)} type="button">Mark as read</button>}
              {!item.is_read && <SnoozeButton id={item.id} onSnooze={() => void refresh()} />}
            </div>
          </article>
        ))}
      </div>
      {data?.next && <button className="mt-4 rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold disabled:opacity-50" disabled={loadingOlder} onClick={() => void loadOlder()} type="button">{loadingOlder ? 'Loading…' : 'Load older notifications'}</button>}
    </section>
  );
}
