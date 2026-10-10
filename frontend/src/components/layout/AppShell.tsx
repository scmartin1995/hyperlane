import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { Home, KanbanSquare, Layers, Flag, BarChart3, Inbox, CheckSquare, Users, Settings, Sparkles, PanelLeftClose, PanelLeftOpen, Sun, Moon, LogOut, Search } from "lucide-react";
import { useUI, label } from "@/lib/store";
import { useMe, useProjects, useLogout, useWorkspace } from "@/api/queries";
import { useLiveEvents } from "@/lib/live";
import { Avatar, Button, IconButton, Kbd, Menu, Select, Toaster, cn } from "@/components/ui";
import { CommandPalette, useCommandPalette } from "./CommandPalette";
import { AgentDrawer } from "@/features/chat/AgentDrawer";

const NAV = [
  { key: "home", to: "/", icon: Home, end: true },
  { key: "board", to: "/board", icon: KanbanSquare },
  { key: "backlog", to: "/backlog", icon: Layers },
  { key: "sprints", to: "/sprints", icon: Flag },
  { key: "reports", to: "/reports", icon: BarChart3 },
  { key: "intake", to: "/intake", icon: Inbox },
  { key: "actionItems", to: "/action-items", icon: CheckSquare },
  { key: "people", to: "/people", icon: Users },
  { key: "settings", to: "/settings", icon: Settings },
] as const;

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

  useEffect(() => { document.documentElement.dataset.theme = ui.theme; }, [ui.theme]);
  useEffect(() => {
    if (projects?.length && (!ui.projectId || !projects.some((p) => p.id === ui.projectId))) ui.setProjectId(projects[0].id);
  }, [projects, ui.projectId]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      const typing = tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); palette.toggle(); }
      if (!typing && e.key === "/" ) { e.preventDefault(); ui.setAgentOpen(!ui.agentOpen); }
      if (!typing && !e.ctrlKey && !e.metaKey && e.key === "g") { (window as unknown as { __g?: number }).__g = Date.now(); }
      else if (!typing && (window as unknown as { __g?: number }).__g && Date.now() - ((window as unknown as { __g?: number }).__g ?? 0) < 800) {
        const map: Record<string, string> = { h: "/", b: "/board", l: "/backlog", s: "/sprints", r: "/reports", i: "/intake", a: "/action-items", p: "/people" };
        if (map[e.key]) nav(map[e.key]);
        (window as unknown as { __g?: number }).__g = 0;
      }
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [palette, ui, nav]);

  const collapsed = ui.sidebarCollapsed;
  const project = projects?.find((p) => p.id === ui.projectId);

  return (
    <div className="h-screen flex overflow-hidden">
      <aside className={cn("shrink-0 flex flex-col border-r border-border bg-bg-2/80 backdrop-blur transition-[width] duration-200", collapsed ? "w-[60px]" : "w-[232px]")}>
        <div className="h-14 flex items-center gap-2 px-3 border-b border-border">
          <span className="text-xl">🏁</span>
          {!collapsed && <div className="min-w-0"><div className="font-display font-black uppercase tracking-[0.12em] text-sm leading-none text-gold">Hyperlane</div><div className="text-[10px] text-text-3 truncate">{ws?.name ?? ""}</div></div>}
        </div>
        <nav className="flex-1 py-2 px-2 space-y-0.5 overflow-y-auto">
          {NAV.map((n) => {
            const Icon = n.icon;
            const fun = label(n.key, ui.flavor); const plain = label(n.key, false);
            return (
              <NavLink key={n.key} to={n.to} end={"end" in n ? n.end : false} title={collapsed ? `${fun} · ${plain}` : undefined} className={({ isActive }) => cn("flex items-center gap-2.5 h-9 px-2.5 rounded-[8px] text-sm transition-colors", isActive ? "bg-surface-2 text-gold shadow-[inset_2px_0_0_var(--gold)]" : "text-text-2 hover:text-text hover:bg-surface-2/60")}>
                <Icon size={17} className="shrink-0" />
                {!collapsed && <span className="flex flex-col leading-tight"><span className="font-display font-semibold tracking-wide">{fun}</span>{ui.flavor && fun !== plain && <span className="text-[10px] text-text-3">{plain}</span>}</span>}
              </NavLink>
            );
          })}
        </nav>
        <div className="p-2 border-t border-border">
          <button onClick={() => ui.setAgentOpen(true)} className={cn("w-full flex items-center gap-2.5 h-10 px-2.5 rounded-[8px] bg-gradient-to-r from-purple/40 to-teal-deep/40 border border-border hover:border-gold transition-colors animate-sweep", collapsed && "justify-center")} title="Open the agent (/)">
            <Sparkles size={16} className="text-gold shrink-0" />
            {!collapsed && <span className="flex-1 text-left leading-tight"><span className="block font-display font-semibold text-sm">{label("agent", ui.flavor)}</span><span className="block text-[10px] text-text-3">Ask, plan, build backlog</span></span>}
            {!collapsed && <Kbd>/</Kbd>}
          </button>
          <button onClick={ui.toggleSidebar} className="mt-1 w-full h-8 flex items-center justify-center text-text-3 hover:text-text rounded-[6px]" title="Toggle sidebar">{collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}</button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 shrink-0 flex items-center gap-3 px-4 border-b border-border bg-bg-2/60 backdrop-blur">
          {projects && projects.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-lg">{project?.icon ?? "🏁"}</span>
              <Select value={ui.projectId ?? ""} onChange={(e) => ui.setProjectId(e.target.value)} className="h-8 !w-auto min-w-[180px] text-sm font-display font-semibold">
                {projects.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.key}</option>)}
              </Select>
            </div>
          )}
          <button onClick={palette.toggle} className="hidden md:flex items-center gap-2 h-8 px-3 rounded-[8px] border border-border bg-surface-2/60 text-text-3 text-xs hover:border-border-strong min-w-[220px]"><Search size={13} /><span className="flex-1 text-left">Search or jump to…</span><Kbd>Ctrl</Kbd><Kbd>K</Kbd></button>
          <div className="flex-1" />
          <IconButton icon={ui.theme === "dark" ? Sun : Moon} label="Toggle theme" onClick={() => ui.setTheme(ui.theme === "dark" ? "light" : "dark")} />
          {me && (
            <Menu align="right" trigger={<button className="flex items-center gap-2 h-8 pl-1 pr-2 rounded-full hover:bg-surface-2"><Avatar user={me} size={26} /><span className="text-sm font-display font-semibold hidden sm:inline">{me.name}</span></button>}
              items={[{ label: "My profile", onClick: () => nav("/people/" + me.id) }, { label: "Switch profile", icon: LogOut, onClick: () => logout.mutate(undefined, { onSuccess: () => nav("/profile") }) }]} />
          )}
        </header>
        <main className="flex-1 overflow-y-auto">
          <div key={loc.pathname.split("/")[1]} className="animate-in p-5 max-w-[1600px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
      <AgentDrawer />
      <CommandPalette />
      <Toaster />
    </div>
  );
}
