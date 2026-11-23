function notificationTarget(value) {
  try {
    const target = new URL(value || "/dashboard/notifications/", self.location.origin);
    if (target.origin === self.location.origin) return target;
  } catch {}
  return new URL("/dashboard/notifications/", self.location.origin);
}

self.addEventListener("push", (event) => {
  let message = {
    title: "Subly reminder",
    body: "Open Subly to review your subscriptions.",
    url: "/dashboard/notifications/",
  };
  try {
    if (event.data) {
      const payload = event.data.json();
      for (const key of ["title", "body", "url"]) {
        if (typeof payload?.[key] === "string" && payload[key]) message[key] = payload[key];
      }
    }
  } catch {}
  event.waitUntil(
    self.registration.showNotification(message.title, {
      body: message.body,
      icon: "/subly-icon-192.png",
      data: { url: notificationTarget(message.url).href },
    }),
  );
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = notificationTarget(event.notification.data?.url);
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const window = windows.find(
        (w) => new URL(w.url).origin === target.origin,
      );
      if (window)
        return window.navigate(target.href).then((navigated) => navigated ? navigated.focus() : clients.openWindow(target.href));
      return clients.openWindow(target.href);
    }),
  );
});
