self.addEventListener("push", (event) => {
  let message = {
    title: "Subly reminder",
    body: "Open Subly to review your subscriptions.",
    url: "/dashboard/notifications/",
  };
  try {
    if (event.data) message = { ...message, ...event.data.json() };
  } catch {}
  event.waitUntil(
    self.registration.showNotification(message.title, {
      body: message.body,
      icon: "/subly-icon-192.png",
      data: { url: message.url },
    }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(
    event.notification.data?.url || "/dashboard/notifications/",
    self.location.origin,
  );
  if (target.origin !== self.location.origin) return;
  event.waitUntil(
    clients.matchAll({ type: "window" }).then((windows) => {
      const window = windows.find(
        (w) => new URL(w.url).origin === target.origin,
      );
      if (window)
        return window.navigate(target.href).then(() => window.focus());
      return clients.openWindow(target.href);
    }),
  );
});
