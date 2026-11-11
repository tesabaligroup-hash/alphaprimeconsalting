import { useCallback, useEffect, useState } from "react";
import { api, type Me } from "./api";
import { tg } from "./tg";
import { AppCtx, Nav, type Route } from "./ui";
import Home from "./screens/Home";
import Services from "./screens/Services";
import ServiceDetail from "./screens/ServiceDetail";
import Documents from "./screens/Documents";
import Partner from "./screens/Partner";
import Referrals from "./screens/Referrals";
import Share from "./screens/Share";
import Profile from "./screens/Profile";
import NewsDetail from "./screens/NewsDetail";

export default function App() {
  const [stack, setStack] = useState<Route[]>([{ name: "home" }]);
  const [me, setMe] = useState<Me | null>(null);
  const [toastText, setToastText] = useState<string | null>(null);
  const route = stack[stack.length - 1];

  const reloadMe = useCallback(() => { api.get<Me>("/api/me").then(setMe).catch(() => setMe(null)); }, []);
  useEffect(reloadMe, [reloadMe]);

  const go = useCallback((r: Route) => {
    const tabRoots = ["home", "services", "documents", "partner", "profile"];
    setStack((s) => (tabRoots.includes(r.name) ? [r] : [...s, r]));
    window.scrollTo(0, 0);
  }, []);
  const back = useCallback(() => { setStack((s) => (s.length > 1 ? s.slice(0, -1) : [{ name: "home" }])); window.scrollTo(0, 0); }, []);
  const toast = useCallback((t: string) => { setToastText(t); setTimeout(() => setToastText(null), 2400); }, []);

  // Системная кнопка «Назад» Telegram
  useEffect(() => {
    const bb = tg?.BackButton;
    if (!bb) return;
    if (stack.length > 1) { bb.show(); bb.onClick(back); } else bb.hide();
    return () => bb.offClick(back);
  }, [stack.length, back]);

  let screen;
  switch (route.name) {
    case "home": screen = <Home />; break;
    case "news": screen = <NewsDetail item={route.item} />; break;
    case "services": screen = <Services initialTab={route.tab} />; break;
    case "service": screen = <ServiceDetail id={route.id} />; break;
    case "documents": screen = <Documents />; break;
    case "partner": screen = <Partner />; break;
    case "referrals": screen = <Referrals />; break;
    case "share": screen = <Share />; break;
    case "profile": screen = <Profile />; break;
  }

  return (
    <AppCtx.Provider value={{ route, go, back, me, reloadMe, toast }}>
      <div className="app">
        {screen}
        <Nav />
        {toastText && <div className="toast" role="status">{toastText}</div>}
      </div>
    </AppCtx.Provider>
  );
}
