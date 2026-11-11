type P = { color?: string; size?: number };
const base = (size = 22, color = "currentColor") => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth: 2,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true,
});

export const IHome = (p: P) => <svg {...base(p.size, p.color)}><path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z" /></svg>;
export const IBag = (p: P) => <svg {...base(p.size, p.color)}><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>;
export const IDoc = (p: P) => <svg {...base(p.size, p.color)}><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></svg>;
export const IPeople = (p: P) => <svg {...base(p.size, p.color)}><circle cx="9" cy="8" r="3" /><circle cx="17" cy="10" r="2.5" /><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M15 20c0-2 1-4 4-4" /></svg>;
export const IUser = (p: P) => <svg {...base(p.size, p.color)}><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8" /></svg>;
export const IBack = (p: P) => <svg {...base(p.size, p.color)}><path d="M15 18l-6-6 6-6" /></svg>;
export const INext = (p: P) => <svg {...base(p.size ?? 18, p.color)}><path d="M9 6l6 6-6 6" /></svg>;
export const IDown = (p: P) => <svg {...base(p.size ?? 18, p.color)}><path d="M6 9l6 6 6-6" /></svg>;
export const ICheck = (p: P) => <svg {...base(p.size ?? 14, p.color)} strokeWidth={3}><path d="M5 12l5 5 9-10" /></svg>;
export const ICal = (p: P) => <svg {...base(p.size ?? 16, p.color)}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>;
export const IDownload = (p: P) => <svg {...base(p.size ?? 18, p.color)}><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>;
export const ICopy = (p: P) => <svg {...base(p.size ?? 18, p.color)}><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></svg>;
export const IQr = (p: P) => <svg {...base(p.size ?? 18, p.color)}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><path d="M14 14h3v3M21 14v7h-7" /></svg>;
export const IAddUser = (p: P) => <svg {...base(p.size ?? 18, p.color)}><circle cx="10" cy="8" r="4" /><path d="M3 21c0-3.9 3.1-7 7-7M19 14v6M16 17h6" /></svg>;
export const IClock = (p: P) => <svg {...base(p.size, p.color)}><circle cx="12" cy="12" r="8" /><path d="M12 8v4l3 2" /></svg>;
