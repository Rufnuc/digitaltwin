"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type NotificationItem } from "@/lib/api";

const SEV_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-yellow-500",
  info: "bg-blue-500",
  low: "bg-muted",
};

function timeAgo(iso: string): string {
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function NotificationBell() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const refreshCount = useCallback(async () => {
    try {
      const c = await api.unreadCount();
      setUnread(c.unread_count);
    } catch {
      /* ignore */
    }
  }, []);

  const loadList = useCallback(async () => {
    try {
      const r = await api.notifications();
      setItems(r.items);
      setUnread(r.unread_count);
    } catch {
      /* ignore */
    }
  }, []);

  // On mount: generate from current conditions, then poll the unread count.
  useEffect(() => {
    api.generateNotifications().then(refreshCount).catch(refreshCount);
    const t = setInterval(refreshCount, 45000);
    return () => clearInterval(t);
  }, [refreshCount]);

  // Close on outside click.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next) loadList();
  }

  async function openItem(n: NotificationItem) {
    if (!n.is_read) {
      api.markNotificationRead(n.id).then(() => {
        setItems((xs) => xs.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)));
        refreshCount();
      });
    }
    setOpen(false);
    if (n.link) router.push(n.link);
  }

  async function markAll() {
    await api.markAllNotificationsRead();
    setItems((xs) => xs.map((x) => ({ ...x, is_read: true })));
    setUnread(0);
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={toggle}
        aria-label="Notifications"
        className="relative flex h-8 w-8 items-center justify-center rounded border border-line hover:bg-wash"
      >
        <span className="text-sm leading-none">🔔</span>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-x-2 top-14 z-40 rounded-lg border border-line bg-paper shadow-lg sm:absolute sm:inset-x-auto sm:right-0 sm:top-10 sm:w-80">
          <div className="flex items-center justify-between border-b border-line px-3 py-2">
            <span className="text-sm font-medium">Notifications</span>
            {items.some((i) => !i.is_read) && (
              <button onClick={markAll} className="text-xs text-muted underline decoration-dotted">
                Mark all read
              </button>
            )}
          </div>
          <div className="max-h-[70vh] overflow-y-auto sm:max-h-96">
            {items.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-muted">You&apos;re all caught up.</div>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => openItem(n)}
                  className={`flex w-full gap-2 border-b border-line px-3 py-2 text-left hover:bg-wash ${
                    n.is_read ? "opacity-60" : ""
                  }`}
                >
                  <span
                    className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEV_DOT[n.severity] ?? "bg-muted"}`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-medium">{n.title}</span>
                    {n.body && <span className="block text-xs text-muted">{n.body}</span>}
                    <span className="mt-0.5 block text-[10px] text-muted">{timeAgo(n.created_at)}</span>
                  </span>
                  {!n.is_read && <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-blue-500" />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
