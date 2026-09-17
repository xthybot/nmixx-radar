self.addEventListener("push", (event) => {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch (error) {
      payload = { body: event.data.text() };
    }
  }

  const title = payload.title || "NMIXX 情報站有新更新";
  const options = {
    body: payload.body || "有新的官方資訊。",
    icon: "/static/icon.svg",
    badge: "/static/icon.svg",
    tag: payload.url || "nmixx-update",
    data: {
      url: payload.url || "/#updates",
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/#updates", self.location.origin);

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      if (url.origin !== self.location.origin) {
        return clients.openWindow(url.href);
      }

      for (const client of clientList) {
        if ("focus" in client) {
          client.navigate(url.href);
          return client.focus();
        }
      }
      return clients.openWindow(url.href);
    }),
  );
});
