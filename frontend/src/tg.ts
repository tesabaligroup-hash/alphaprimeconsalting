// Обёртка над Telegram WebApp API (https://core.telegram.org/bots/webapps)
type TgWebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  openLink: (url: string) => void;
  openTelegramLink: (url: string) => void;
  requestContact?: (cb?: (ok: boolean) => void) => void;
  HapticFeedback?: { notificationOccurred: (t: "success" | "error" | "warning") => void };
  BackButton?: { show: () => void; hide: () => void; onClick: (cb: () => void) => void; offClick: (cb: () => void) => void };
  setHeaderColor?: (c: string) => void;
  setBackgroundColor?: (c: string) => void;
  showAlert?: (msg: string) => void;
};

export const tg: TgWebApp | undefined = (window as unknown as { Telegram?: { WebApp?: TgWebApp } }).Telegram?.WebApp;

export function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.setHeaderColor?.("#FFFFFF");
  tg.setBackgroundColor?.("#FFFFFF");
}

export function openExternal(url: string) {
  if (tg && url.startsWith("https://t.me/")) tg.openTelegramLink(url);
  else if (tg) tg.openLink(url);
  else window.open(url, "_blank", "noopener");
}

export function haptic(kind: "success" | "error" | "warning" = "success") {
  tg?.HapticFeedback?.notificationOccurred(kind);
}

export function notify(msg: string) {
  if (tg?.showAlert) tg.showAlert(msg);
  else alert(msg);
}
