import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { Home, KanbanSquare, Layers, CalendarRange, BarChart3, CheckSquare, Users, Settings, Sparkles, PanelLeftClose, PanelLeftOpen, Sun, Moon, LogOut, Search, ArrowRight } from "lucide-react";
import { useUI, label } from "@/lib/store";
import { useMe, useProjects, useLogout, useWorkspace } from "@/api/queries";
import { useLiveEvents } from "@/lib/live";
import { Avatar, Kbd, Menu, Select, Toaster, cn } from "@/components/ui";
import { CommandPalette, useCommandPalette } from "./CommandPalette";
import { ShortcutHelp, useShortcutHelp } from "./ShortcutHelp";
import { AgentDrawer } from "@/features/chat/AgentDrawer";

const NAV = [
  { key: "home", to: "/", icon: Home, end: true },
  { key: "board", to: "/board", icon: KanbanSquare },
  { key: "backlog", to: "/backlog", icon: Layers },
  { key: "sprints", to: "/sprints", icon: CalendarRange },
  { key: "reports", to: "/reports", icon: BarChart3 },
  { key: "actionItems", to: "/action-items", icon: CheckSquare },
  { key: "people", to: "/people", icon: Users },
] as const;

/** One bar for everything: type a question and press Enter to ask the assistant, or Ctrl+K to jump anywhere. */
function AskBar() {
  const ui = useUI();
  const palette = useCommandPalette();
  const [q, setQ] = useState("");
  const submit = () => {
    const text = q.trim();
    if (!text) { palette.toggle(); return; }
    ui.setAgentOpen(true, { prefill: text, nonce: Date.now() });
    setQ("");
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="flex-1 max-w-[680px] mx-auto">
      <div className="group flex items-center gap-2 h-10 pl-3 pr-1.5 rounded-full bg-surface border border-border-strong/50 shadow-sm focus-within:border-purple focus-within:shadow-[0_0_0_3px_var(--purple-tint)] transition-all">
        <Sparkles size={16} className="text-purple shrink-0" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask anything, or search… (Enter asks the assistant · Ctrl K jumps)" className="flex-1 bg-transparent outline-none text-sm placeholder:text-text-3 min-w-0" />
        <button type="button" onClick={palette.toggle} className="hidden md:inline-flex items-center gap-1 text-text-3 hover:text-text px-1" title="Search & jump (Ctrl K)"><Search size={14} /></button>
        <button type="submit" className="h-7 w-7 rounded-full bg-purple text-cream inline-flex items-center justify-center hover:brightness-110" title="Ask the assistant"><ArrowRight size={14} /></button>
      </div>
    </form>
  );
}

export function AppShell() {
  useLiveEvents();
  const ui = useUI();
  const { data: me } = useMe();
  const { data: projects } = useProjects();
  const { data: ws } = useWorkspace();
  const logout = useLogout();
  const nav = useNavigate();
  const loc = useLocation();
  const palette = useCommandPalette();
  const help = useShortcutHelp();

  useEffect(() => { document.documentElement.dataset.theme = ui.theme; }, [ui.theme]);
  useEffect(() => {
    if (projects?.length && (!ui.projectId || !projects.some((p) => p.id === ui.projectId))) ui.setProjectId(projects[0].id);
  }, [projects, ui.projectId]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette.toggle(); }
      if (!typing && e.key === "/") { e.preventDefault(); ui.setAgentOpen(!ui.agentOpen); }
      if (!typing && e.key === "?") { e.preventDefault(); help.toggle(); }
      const w = window as unknown as { __g?: number };
      if (!typing && !e.ctrlKey && !e.metaKey && e.key === "g") { w.__g = Date.now(); }
      else if (!typing && w.__g && Date.now() - (w.__g ?? 0) < 800) {
        const map: Record<string, string> = { h: "/", b: "/board", l: "/backlog", s: "/sprints", r: "/reports", i: "/backlog", a: "/action-items", p: "/people" };
        if (map[e.key]) nav(map[e.key]);
        w.__g = 0;
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [palette, ui, nav, help]);

  const collapsed = ui.sidebarCollapsed;
  const project = projects?.find((p) => p.id === ui.projectId);

  return (
    <div className="h-screen flex overflow-hidden">
      <aside className={cn("shrink-0 flex flex-col bg-surface-2/70 backdrop-blur border-r border-border transition-[width] duration-200", collapsed ? "w-[64px]" : "w-[228px]")}>
        <div className="h-16 flex items-center gap-2.5 px-4">
          <span className="w-8 h-8 rounded-[10px] bg-[linear-gradient(135deg,var(--purple),var(--rust))] text-cream inline-flex items-center justify-center font-display font-extrabold text-sm shadow-sm">H</span>
          {!collapsed && <div className="min-w-0"><div className="font-display font-bold text-[15px] leading-none">Hyperlane</div><div className="text-[11px] text-text-3 truncate mt-0.5">{ws?.name ?? ""}</div></div>}
        </div>
        <nav className="flex-1 px-2.5 space-y-1 overflow-y-auto">
          {NAV.map((n) => {
            const Icon = n.icon;
            const text = label(n.key, ui.flavor);
            return (
              <NavLink key={n.key} to={n.to} end={"end" in n ? n.end : false} title={collapsed ? text : undefined} className={({ isActive }) => cn("flex items-center gap-3 h-10 px-3 rounded-[12px] text-sm font-display font-semibold transition-colors", isActive ? "bg-purple text-cream shadow-[0_6px_16px_-8px_var(--purple)]" : "text-text-2 hover:text-text hover:bg-surface")}>
                <Icon size={18} className="shrink-0" />
                {!collapsed && <span>{text}</span>}
              </NavLink>
            );
          })}
        </nav>
        <div className="p-2.5 space-y-1 border-t border-border">
          <button onClick={() => ui.setAgentOpen(true)} className={cn("w-full flex items-center gap-3 h-11 px-3 rounded-[12px] text-cream bg-[linear-gradient(135deg,var(--purple),var(--teal))] hover:brightness-110 transition animate-sweep", collapsed && "justify-center px-0")} title="Open the assistant (/)">
            <Sparkles size={17} className="shrink-0" />
            {!collapsed && <span className="flex-1 text-left leading-tight"><span className="block font-display font-bold text-sm">{label("agent", ui.flavor)}</span><span className="block text-[10.5px] opacity-80">Ask, plan, draft stories</span></span>}
          </button>
          <NavLink to="/settings" className={({ isActive }) => cn("flex items-center gap-3 h-9 px-3 rounded-[12px] text-sm font-display font-semibold transition-colors", isActive ? "bg-purple text-cream" : "text-text-2 hover:text-text hover:bg-surface", collapsed && "justify-center px-0")} title="Settings"><Settings size={17} />{!collapsed && label("settings", ui.flavor)}</NavLink>
          <button onClick={ui.toggleSidebar} className="w-full h-7 flex items-center justify-center text-text-3 hover:text-text rounded-[8px]" title="Toggle sidebar">{collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}</button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 shrink-0 flex items-center gap-3 px-5">
          {projects && projects.length > 0 && (
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-lg">{project?.icon ?? "✨"}</span>
              <Select value={ui.projectId ?? ""} onChange={(e) => ui.setProjectId(e.target.value)} className="h-9 !w-auto min-w-[170px] text-sm font-display font-semibold rounded-full !bg-surface">
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </div>
          )}
          <AskBar />
          <button onClick={() => ui.setTheme(ui.theme === "dark" ? "light" : "dark")} className="h-9 w-9 rounded-full inline-flex items-center justify-center text-text-2 hover:bg-surface" title="Toggle theme">{ui.theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}</button>
          {me && (
            <Menu align="right" trigger={<button className="flex items-center gap-2 h-9 pl-1 pr-3 rounded-full bg-surface border border-border hover:border-border-strong"><Avatar user={me} size={26} /><span className="text-sm font-display font-semibold hidden sm:inline">{me.name.split(" ")[0]}</span></button>}
              items={[{ label: "My profile", onClick: () => nav("/people/" + me.id) }, { label: "Switch profile", icon: LogOut, onClick: () => logout.mutate(undefined, { onSuccess: () => nav("/profile") }) }]} />
          )}
        </header>
        <main className="flex-1 overflow-y-auto">
          <div key={loc.pathname.split("/")[1]} className="animate-in px-6 pb-8 pt-1 max-w-[1560px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
      <AgentDrawer />
      <CommandPalette />
      <ShortcutHelp />
      <Toaster />
    </div>
  );
}
