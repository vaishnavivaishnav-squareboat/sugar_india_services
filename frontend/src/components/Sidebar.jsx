import { NavLink, useLocation } from "react-router-dom";
import { LayoutDashboard, Search, Database, Mail, Leaf, TrendingUp, Users } from "lucide-react";

const navItems = [
  { path: "/", icon: LayoutDashboard, label: "Dashboard" },
  { path: "/discover", icon: Search, label: "Lead Discovery" },
  { path: "/leads", icon: Database, label: "Lead Database" },
  { path: "/outreach", icon: Mail, label: "Outreach Center" },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside
      data-testid="sidebar"
      style={{ backgroundColor: "#143628", minWidth: "260px", maxWidth: "260px" }}
      className="flex flex-col h-screen overflow-hidden"
    >
      {/* Logo */}
      <div className="px-6 py-5 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-[#B85C38]">
            <Leaf size={18} className="text-white" strokeWidth={2} />
          </div>
          <div>
            <p className="font-heading text-white font-bold text-sm leading-tight" style={{ fontFamily: 'Plus Jakarta Sans, sans-serif' }}>
              Dhampur Green
            </p>
            <p className="text-white/50 text-xs leading-tight">HORECA Intelligence</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <p className="text-white/30 uppercase text-xs tracking-widest px-3 mb-3" style={{ letterSpacing: '0.2em' }}>
          Navigation
        </p>
        {navItems.map(({ path, icon: Icon, label }) => {
          const isActive = path === "/" ? location.pathname === "/" : location.pathname.startsWith(path);
          return (
            <NavLink
              key={path}
              to={path}
              data-testid={`nav-${label.toLowerCase().replace(/\s+/g, '-')}`}
              className={`sidebar-nav-item flex items-center gap-3 px-3 py-2.5 rounded-md text-sm ${isActive ? "active text-white font-medium" : "text-white/65 hover:text-white"}`}
            >
              <Icon size={17} strokeWidth={isActive ? 2 : 1.5} />
              {label}
            </NavLink>
          );
        })}
      </nav>

      {/* Stats summary */}
      <div className="px-4 py-4 border-t border-white/10">
        <div className="bg-white/5 rounded-lg p-3 space-y-2">
          <p className="text-white/40 text-xs uppercase tracking-widest" style={{ letterSpacing: '0.15em' }}>Product</p>
          <div className="flex items-center gap-2">
            <TrendingUp size={13} className="text-[#B85C38]" />
            <span className="text-white/70 text-xs">Premium Sugar Supplier</span>
          </div>
          <div className="flex items-center gap-2">
            <Users size={13} className="text-[#B85C38]" />
            <span className="text-white/70 text-xs">B2B HORECA Sales</span>
          </div>
        </div>
      </div>

      {/* User */}
      <div className="px-4 py-4 border-t border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center text-white text-xs font-bold">
            AM
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-sm font-medium truncate">Arjun Mehta</p>
            <p className="text-white/40 text-xs truncate">Regional Sales Manager</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
