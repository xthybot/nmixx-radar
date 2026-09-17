const carousel = document.querySelector("[data-carousel]");

if (carousel) {
  const slides = [...carousel.querySelectorAll(".hero-slide")];
  const dots = [...carousel.querySelectorAll(".dot")];
  const source = carousel.querySelector("[data-slide-source]");
  const label = carousel.querySelector("[data-slide-label]");
  const count = carousel.querySelector("[data-slide-count]");
  let active = 0;
  let touchStartX = null;
  let carouselTimer = null;

  function showSlide(index) {
    active = (index + slides.length) % slides.length;
    if (slides[active].dataset.src && slides[active].getAttribute("src") !== slides[active].dataset.src) {
      slides[active].src = slides[active].dataset.src;
    }
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === active);
    });
    dots.forEach((dot, dotIndex) => {
      dot.classList.toggle("is-active", dotIndex === active);
    });
    source.textContent = slides[active].dataset.source;
    label.textContent = slides[active].dataset.label;
    count.textContent = `${active + 1}/${slides.length}`;
  }

  function startCarouselTimer() {
    window.clearInterval(carouselTimer);
    carouselTimer = window.setInterval(() => showSlide(active + 1), 4200);
  }

  function manuallyShowSlide(index) {
    showSlide(index);
    startCarouselTimer();
  }

  dots.forEach((dot) => {
    dot.addEventListener("click", () => manuallyShowSlide(Number(dot.dataset.slide)));
  });

  carousel.addEventListener("touchstart", (event) => {
    touchStartX = event.touches[0]?.clientX ?? null;
  }, { passive: true });

  carousel.addEventListener("touchend", (event) => {
    if (touchStartX === null) return;
    const deltaX = event.changedTouches[0].clientX - touchStartX;
    touchStartX = null;
    if (Math.abs(deltaX) < 42) return;
    manuallyShowSlide(active + (deltaX < 0 ? 1 : -1));
  });

  startCarouselTimer();
}

const notifyButton = document.querySelector("[data-notify-toggle]");

function supportsPushNotifications() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

function updateNotifyButton() {
  if (!notifyButton) return;
  if (!("Notification" in window)) {
    notifyButton.hidden = true;
    return;
  }
  const enabled = window.localStorage.getItem("nmixxNotifyEnabled") === "1";
  notifyButton.classList.toggle("is-active", enabled && Notification.permission === "granted");
  if (Notification.permission === "granted") {
    notifyButton.setAttribute("aria-label", enabled ? "更新通知已開啟" : "開啟更新通知");
    notifyButton.textContent = enabled ? "✓" : "!";
  } else {
    notifyButton.setAttribute("aria-label", "開啟更新通知");
    notifyButton.textContent = "!";
  }
}

async function fetchUpdateSnapshot() {
  const response = await fetch("/api/updates", { cache: "no-store" });
  if (!response.ok) throw new Error(`Update check failed: ${response.status}`);
  return response.json();
}

async function registerPushSubscription() {
  if (!supportsPushNotifications()) return false;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;

  const registration = await navigator.serviceWorker.register("/sw.js");
  const keyResponse = await fetch("/api/push/public-key", { cache: "no-store" });
  if (!keyResponse.ok) throw new Error(`Push key failed: ${keyResponse.status}`);
  const { publicKey } = await keyResponse.json();

  let subscription = await registration.pushManager.getSubscription();
  if (subscription && window.localStorage.getItem("nmixxVapidPublicKey") !== publicKey) {
    await subscription.unsubscribe();
    subscription = null;
  }
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
  }

  const response = await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(subscription),
  });
  if (!response.ok) throw new Error(`Push subscribe failed: ${response.status}`);
  window.localStorage.setItem("nmixxVapidPublicKey", publicKey);
  return subscription;
}

async function checkForBrowserNotification() {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  if (window.localStorage.getItem("nmixxNotifyEnabled") !== "1") return;

  try {
    const snapshot = await fetchUpdateSnapshot();
    const previousSignature = window.localStorage.getItem("nmixxUpdateSignature");
    window.localStorage.setItem("nmixxUpdateSignature", snapshot.signature);

    if (!previousSignature || previousSignature === snapshot.signature || !snapshot.latest) return;

    if ("serviceWorker" in navigator) {
      const registration = await navigator.serviceWorker.ready;
      await registration.showNotification("NMIXX 情報站有新更新", {
        body: snapshot.latest.title,
        icon: "/static/icon.svg",
        badge: "/static/icon.svg",
        tag: snapshot.signature,
        data: { url: snapshot.latest.href || "/#updates" },
      });
    } else {
      const notification = new Notification("NMIXX 情報站有新更新", {
        body: snapshot.latest.title,
        tag: snapshot.signature,
      });
      notification.onclick = () => {
        window.focus();
        window.location.href = snapshot.latest.href || "/#updates";
      };
    }
  } catch (error) {
    console.warn(error);
  }
}

if (notifyButton) {
  updateNotifyButton();
  notifyButton.addEventListener("click", async () => {
    if (!("Notification" in window)) return;
    let subscription = null;
    try {
      notifyButton.textContent = "…";
      subscription = await registerPushSubscription();
    } catch (error) {
      console.warn(error);
      if (Notification.permission === "default") {
        await Notification.requestPermission();
      }
    }
    if (subscription || Notification.permission === "granted") {
      window.localStorage.setItem("nmixxNotifyEnabled", "1");
      const snapshot = await fetchUpdateSnapshot();
      window.localStorage.setItem("nmixxUpdateSignature", snapshot.signature);
    }
    updateNotifyButton();
  });
  checkForBrowserNotification();
  window.setInterval(checkForBrowserNotification, 60000);
}
