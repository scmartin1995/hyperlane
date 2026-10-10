// Hyperlane UI kit. Small, consistent, themeable. Everything a feature needs lives here.
import { clsx } from "clsx";
import { X, Loader2, type LucideIcon } from "lucide-react";
import { type ReactNode, type ButtonHTMLAttributes, type InputHTMLAttributes, type TextareaHTMLAttributes, type SelectHTMLAttributes, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { create } from "zustand";
import type { UserBrief } from "@/api/types";
import { initials } from "@/lib/format";

export const cn = clsx;

/* ---------- Button ---------- */
type Variant = "primary" | "secondary" | "ghost" | "danger" | "teal" | "outline";
type Size = "xs" | "sm" | "md" | "lg";
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant; size?: Size; icon?: LucideIcon; loading?: boolean; iconRight?: LucideIcon;
}
const variantCls: Record<Variant, string> = {
  primary: "bg-gold text-ink hover:brightness-110 font-semibold shadow-[0_0_0_1px_rgba(228,185,99,.3)]",
  secondary: "bg-surface-2 text-text hover:bg-surface-3 border border-border",
  ghost: "bg-transparent text-text-2 hover:text-text hover:bg-surface-2",
  danger: "bg-rust text-cream hover:brightness-110",
  teal: "bg-teal text-ink hover:brightness-110 font-semibold",
  outline: "bg-transparent border border-border-strong text-text hover:border-gold hover:text-gold",
};
const sizeCls: Record<Size, string> = { xs: "h-6 px-2 text-[11px] gap-1 rounded-[5px]", sm: "h-8 px-3 text-xs gap-1.5 rounded-[7px]", md: "h-9 px-4 text-sm gap-2 rounded-[8px]", lg: "h-11 px-6 text-base gap-2 rounded-[10px]" };
export function Button({ variant = "secondary", size = "md", icon: Icon, iconRight: IconR, loading, className, children, disabled, ...rest }: ButtonProps) {
  const iconSize = size === "xs" ? 12 : size === "sm" ? 14 : 16;
  return (
    <button className={cn("inline-flex items-center justify-center font-display tracking-wide transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap select-none", variantCls[variant], sizeCls[size], className)} disabled={disabled || loading} {...rest}>
      {loading ? <Loader2 size={iconSize} className="animate-spin" /> : Icon ? <Icon size={iconSize} /> : null}
      {children}
      {IconR ? <IconR size={iconSize} /> : null}
    </button>
  );
}
export function IconButton({ icon: Icon, label, size = "sm", className, ...rest }: { icon: LucideIcon; label: string } & Omit<ButtonProps, "icon" | "children">) {
  return <Button variant="ghost" size={size} aria-label={label} title={label} className={cn("!px-0 aspect-square", className)} {...rest}><Icon size={size === "xs" ? 12 : size === "sm" ? 15 : 18} /></Button>;
}

/* ---------- Panel / Card ---------- */
export function Panel({ className, children, cut, title, eyebrow, actions, padded = true, ...rest }: { className?: string; children?: ReactNode; cut?: boolean; title?: ReactNode; eyebrow?: ReactNode; actions?: ReactNode; padded?: boolean } & React.HTMLAttributes<HTMLDivElement>) {
  return (
    <section className={cn("panel", cut && "panel-cut", padded && "p-4", className)} {...rest}>
      {(title || eyebrow || actions) && (
        <header className={cn("flex items-start justify-between gap-3 mb-3", !padded && "px-4 pt-4")}>
          <div>
            {eyebrow && <div className="eyebrow">{eyebrow}</div>}
            {title && <h2 className="text-base leading-tight">{title}</h2>}
          </div>
          {actions && <div className="flex items-center gap-1 shrink-0">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/* ---------- Badge / Chip ---------- */
export function Badge({ children, color, className, dot, size = "sm", onClick }: { children: ReactNode; color?: string; className?: string; dot?: boolean; size?: "xs" | "sm"; onClick?: () => void }) {
  const style = color ? { color, borderColor: `color-mix(in oklab, ${color} 45%, transparent)`, background: `color-mix(in oklab, ${color} 12%, transparent)` } : undefined;
  return (
    <span onClick={onClick} style={style} className={cn("inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 text-text-2 font-display font-semibold tracking-wide whitespace-nowrap", size === "xs" ? "h-[18px] px-1.5 text-[10px]" : "h-[22px] px-2 text-[11px]", onClick && "cursor-pointer hover:brightness-125", className)}>
      {dot && <span className="w-1.5 h-1.5 rounded-full" style={{ background: color ?? "currentColor" }} />}
      {children}
    </span>
  );
}
export function Kbd({ children }: { children: ReactNode }) { return <kbd className="inline-flex h-5 min-w-5 px-1.5 items-center justify-center rounded border border-border-strong bg-surface-2 text-[10px] text-text-2 font-mono">{children}</kbd>; }

/* ---------- Avatar ---------- */
export function Avatar({ user, size = 24, className, title }: { user: UserBrief | null | undefined; size?: number; className?: string; title?: string }) {
  if (!user) return <span className={cn("inline-flex items-center justify-center rounded-full border border-dashed border-border-strong text-text-3", className)} style={{ width: size, height: size, fontSize: size * 0.45 }} title={title ?? "Unassigned"}>?</span>;
  return (
    <span className={cn("inline-flex items-center justify-center rounded-full font-display font-bold text-ink shrink-0", className)} style={{ width: size, height: size, background: user.color, fontSize: size * 0.5 }} title={title ?? user.name}>
      {user.emoji && size >= 28 ? user.emoji : initials(user.name)}
    </span>
  );
}
export function AvatarStack({ users, max = 4, size = 22 }: { users: UserBrief[]; max?: number; size?: number }) {
  const shown = users.slice(0, max);
  return <span className="inline-flex -space-x-1.5">{shown.map((u) => <Avatar key={u.id} user={u} size={size} className="ring-2 ring-surface" />)}{users.length > max && <span className="inline-flex items-center justify-center rounded-full bg-surface-3 text-[10px] text-text-2 ring-2 ring-surface" style={{ width: size, height: size }}>+{users.length - max}</span>}</span>;
}

/* ---------- Inputs ---------- */
const fieldCls = "w-full bg-surface-2 border border-border rounded-[8px] px-3 text-sm placeholder:text-text-3 transition-colors focus:border-teal focus:outline-none disabled:opacity-60";
export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) { return <input className={cn(fieldCls, "h-9", className)} {...rest} />; }
export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea className={cn(fieldCls, "py-2 min-h-[80px] leading-relaxed", className)} {...rest} />; }
export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) { return <select className={cn(fieldCls, "h-9 pr-8 appearance-none bg-no-repeat bg-[right_0.6rem_center] bg-[length:12px]", className)} style={{ backgroundImage: "url(\"data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3e%3cpath fill='%23869791' d='M3 4.5l3 3 3-3'/%3e%3c/svg%3e\")" }} {...rest}>{children}</select>; }
export function Field({ label, hint, children, className, required }: { label?: ReactNode; hint?: ReactNode; children: ReactNode; className?: string; required?: boolean }) {
  return <label className={cn("block", className)}>{label && <span className="block mb-1 text-xs font-display font-semibold tracking-wide text-text-2 uppercase">{label}{required && <span className="text-rust"> *</span>}</span>}{children}{hint && <span className="block mt-1 text-[11px] text-text-3">{hint}</span>}</label>;
}
export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="inline-flex items-center gap-2 text-sm">
      <span className={cn("relative inline-block w-9 h-5 rounded-full transition-colors", checked ? "bg-teal" : "bg-surface-3 border border-border-strong")}><span className={cn("absolute top-0.5 w-4 h-4 rounded-full bg-cream transition-transform shadow", checked ? "translate-x-[18px]" : "translate-x-0.5")} /></span>
      {label && <span>{label}</span>}
    </button>
  );
}

/* ---------- Progress / Stat ---------- */
export function Progress({ value, max = 100, color = "var(--teal)", className, height = 6 }: { value: number; max?: number; color?: string; className?: string; height?: number }) {
  const p = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  return <div className={cn("w-full rounded-full bg-surface-3 overflow-hidden", className)} style={{ height }}><div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${p}%`, background: color }} /></div>;
}
export function Stat({ label, value, sub, color, className, icon: Icon }: { label: ReactNode; value: ReactNode; sub?: ReactNode; color?: string; className?: string; icon?: LucideIcon }) {
  return (
    <div className={cn("panel p-3.5 min-w-0", className)}>
      <div className="flex items-center justify-between"><span className="eyebrow">{label}</span>{Icon && <Icon size={14} className="text-text-3" />}</div>
      <div className="num text-2xl font-bold mt-1 leading-none" style={{ color }}>{value}</div>
      {sub && <div className="text-[11px] text-text-3 mt-1.5">{sub}</div>}
    </div>
  );
}

/* ---------- Tabs ---------- */
export function Tabs<T extends string>({ tabs, value, onChange, className }: { tabs: { key: T; label: ReactNode; count?: number }[]; value: T; onChange: (t: T) => void; className?: string }) {
  return (
    <div className={cn("inline-flex items-center gap-1 p-1 rounded-[9px] bg-surface-2 border border-border", className)} role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)} className={cn("h-7 px-3 rounded-[6px] text-xs font-display font-semibold tracking-wide transition-colors inline-flex items-center gap-1.5", value === t.key ? "bg-surface text-gold shadow" : "text-text-2 hover:text-text")}>
          {t.label}{t.count != null && <span className="num text-[10px] text-text-3">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------- Modal / Drawer ---------- */
export function Modal({ open, onClose, title, children, width = 560, footer, eyebrow }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; width?: number; footer?: ReactNode; eyebrow?: ReactNode }) {
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[8vh] bg-black/60 backdrop-blur-[2px] animate-in" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="panel panel-cut w-full max-h-[84vh] flex flex-col animate-pop" style={{ maxWidth: width }} role="dialog" aria-modal>
        <div className="hairline" />
        {(title || eyebrow) && <header className="flex items-start justify-between px-5 pt-4 pb-2"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}{title && <h2 className="text-lg">{title}</h2>}</div><IconButton icon={X} label="Close" onClick={onClose} /></header>}
        <div className="px-5 pb-4 overflow-y-auto flex-1">{children}</div>
        {footer && <footer className="px-5 py-3 border-t border-border flex justify-end gap-2 bg-surface-2/50">{footer}</footer>}
      </div>
    </div>, document.body);
}
export function Drawer({ open, onClose, title, children, width = 520, side = "right", eyebrow, actions }: { open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode; width?: number; side?: "right" | "left"; eyebrow?: ReactNode; actions?: ReactNode }) {
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 bg-black/50 animate-in" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside className={cn("absolute top-0 bottom-0 bg-surface border-border flex flex-col shadow-2xl", side === "right" ? "right-0 border-l" : "left-0 border-r")} style={{ width: `min(${width}px, 100vw)` }}>
        <div className="hairline" />
        <header className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0"><div className="min-w-0">{eyebrow && <div className="eyebrow">{eyebrow}</div>}{title && <h2 className="text-base truncate">{title}</h2>}</div><div className="flex items-center gap-1">{actions}<IconButton icon={X} label="Close" onClick={onClose} /></div></header>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </aside>
    </div>, document.body);
}

/* ---------- Menu (simple dropdown) ---------- */
export function Menu({ trigger, items, align = "right" }: { trigger: ReactNode; items: { label: ReactNode; onClick?: () => void; icon?: LucideIcon; danger?: boolean; disabled?: boolean }[]; align?: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!open) return; const h = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); }; window.addEventListener("mousedown", h); return () => window.removeEventListener("mousedown", h); }, [open]);
  return (
    <div className="relative inline-block" ref={ref}>
      <span onClick={() => setOpen((o) => !o)}>{trigger}</span>
      {open && (
        <div className={cn("absolute z-40 mt-1 min-w-[180px] panel p-1 animate-pop", align === "right" ? "right-0" : "left-0")}>
          {items.map((it, i) => (
            <button key={i} disabled={it.disabled} onClick={() => { setOpen(false); it.onClick?.(); }} className={cn("w-full flex items-center gap-2 px-2.5 h-8 rounded-[6px] text-left text-sm hover:bg-surface-2 disabled:opacity-50", it.danger && "text-rust-light")}>{it.icon && <it.icon size={14} />}{it.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Empty / Loading ---------- */
export function EmptyState({ icon, title, body, action, className }: { icon?: ReactNode; title: ReactNode; body?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-12 px-6 rounded-[12px] border border-dashed border-border-strong", className)}>
      {icon && <div className="text-4xl mb-3 animate-float">{icon}</div>}
      <h3 className="font-display font-bold text-base">{title}</h3>
      {body && <p className="text-text-3 text-sm mt-1 max-w-sm">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
export function Skeleton({ className }: { className?: string }) { return <div className={cn("animate-shimmer rounded-[8px] h-4", className)} />; }
export function Spinner({ size = 18, className }: { size?: number; className?: string }) { return <Loader2 size={size} className={cn("animate-spin text-text-3", className)} />; }
export function PageHeader({ eyebrow, title, subtitle, actions, children }: { eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>{eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}<h1 className="text-2xl leading-none">{title}</h1>{subtitle && <p className="text-text-3 text-sm mt-1.5">{subtitle}</p>}{children}</div>
      {actions && <div className="flex items-center gap-2 flex-wrap">{actions}</div>}
    </div>
  );
}

/* ---------- Toasts ---------- */
interface Toast { id: number; title: string; body?: string; kind: "info" | "success" | "error" | "fun" }
interface ToastState { toasts: Toast[]; push: (t: Omit<Toast, "id">) => void; remove: (id: number) => void }
export const useToasts = create<ToastState>((set) => ({
  toasts: [],
  push: (t) => { const id = Date.now() + Math.random(); set((s) => ({ toasts: [...s.toasts, { ...t, id }] })); setTimeout(() => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })), t.kind === "error" ? 7000 : 3800); },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
export const toast = {
  info: (title: string, body?: string) => useToasts.getState().push({ title, body, kind: "info" }),
  success: (title: string, body?: string) => useToasts.getState().push({ title, body, kind: "success" }),
  error: (title: string, body?: string) => useToasts.getState().push({ title, body, kind: "error" }),
  fun: (title: string, body?: string) => useToasts.getState().push({ title, body, kind: "fun" }),
};
export function Toaster() {
  const { toasts, remove } = useToasts();
  const colors = { info: "var(--teal)", success: "var(--green)", error: "var(--rust)", fun: "var(--gold)" };
  return createPortal(
    <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 w-[340px] max-w-[calc(100vw-2rem)]">
      {toasts.map((t) => (
        <div key={t.id} className="panel p-3 pl-4 animate-pop flex items-start gap-3 border-l-[3px]" style={{ borderLeftColor: colors[t.kind] }}>
          <div className="flex-1 min-w-0"><div className="font-display font-semibold text-sm">{t.title}</div>{t.body && <div className="text-xs text-text-2 mt-0.5 whitespace-pre-line">{t.body}</div>}</div>
          <IconButton icon={X} label="Dismiss" size="xs" onClick={() => remove(t.id)} />
        </div>
      ))}
    </div>, document.body);
}

/* ---------- Confetti ---------- */
export async function celebrate(kind: "small" | "big" = "small") {
  const mod = await import("canvas-confetti");
  const confetti = mod.default;
  const colors = ["#e4b963", "#27cfc3", "#f7f2f0", "#6b3a8e"];
  if (kind === "small") confetti({ particleCount: 60, spread: 60, origin: { y: 0.8 }, colors, ticks: 120, scalar: 0.9 });
  else { confetti({ particleCount: 160, spread: 100, origin: { y: 0.6 }, colors }); setTimeout(() => confetti({ particleCount: 120, angle: 60, spread: 70, origin: { x: 0 }, colors }), 250); setTimeout(() => confetti({ particleCount: 120, angle: 120, spread: 70, origin: { x: 1 }, colors }), 400); }
}

/* ---------- Markdown ---------- */
export { Markdown } from "./Markdown";
