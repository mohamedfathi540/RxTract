import { NavLink, useNavigate } from "react-router-dom";
import {
  ChatBubbleLeftRightIcon,
  MagnifyingGlassIcon,
  DocumentTextIcon,
  ArrowRightStartOnRectangleIcon,
} from "@heroicons/react/24/outline";
import { Menu, X } from "lucide-react";
import { Logo } from "../ui/Logo";
import { useAuthStore } from "../../stores/authStore";
import { Button } from "../ui/Button";
import { QuotaPanel } from "../ui/QuotaPanel";
import { useEffect } from "react";

const navigation = [
  { name: "Prescription", href: "/prescription", icon: DocumentTextIcon },
  { name: "Chat", href: "/", icon: ChatBubbleLeftRightIcon },
  { name: "Search", href: "/search", icon: MagnifyingGlassIcon },
];

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
}

export function Sidebar({ isOpen, onToggle }: SidebarProps) {
  const { userEmail, logout } = useAuthStore();
  const navigate = useNavigate();



  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  // Close sidebar on route change (mobile)
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768 && isOpen) {
        onToggle();
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [isOpen, onToggle]);

  return (
    <>
      {/* Mobile hamburger button — only visible when sidebar is CLOSED */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="fixed top-3 left-3 z-50 md:hidden p-2 rounded-lg bg-bg-secondary border border-border text-text-primary hover:bg-bg-hover transition-colors"
          aria-label="Open menu"
        >
          <Menu className="w-6 h-6" />
        </button>
      )}

      {/* Backdrop overlay (mobile only) */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`
          fixed md:static z-40 top-0 left-0 h-full w-64
          bg-bg-secondary border-r border-border
          flex flex-col shrink-0
          transform transition-transform duration-200 ease-out
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          md:translate-x-0
        `}
      >
        <div className="p-5 border-b border-border">
          <div className="flex items-center gap-2.5">
            <Logo size={36} className="rounded-lg" />
            <div className="flex-1 min-w-0">
              <h1 className="text-xl font-semibold tracking-tight text-white">
                RxTract
              </h1>
              <p className="text-xs text-text-muted mt-0.5">
                Prescription Analyzer
              </p>
            </div>
            {/* Mobile close button — inside sidebar header */}
            <button
              onClick={onToggle}
              className="md:hidden p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
              aria-label="Close menu"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              onClick={() => {
                // Close sidebar on mobile after clicking a link
                if (window.innerWidth < 768) onToggle();
              }}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${isActive
                  ? "bg-primary-600 text-white"
                  : "text-text-secondary hover:bg-bg-hover hover:text-text-primary"
                }`
              }
            >
              <item.icon className="w-5 h-5 shrink-0" />
              <span className="truncate">{item.name}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-border space-y-3">
          {/* Daily usage quotas */}
          <QuotaPanel />

          {/* User info & logout */}
          <div className="flex items-center justify-between gap-2">
            <p
              className="text-xs text-text-secondary truncate flex-1"
              title={userEmail ?? ""}
            >
              {userEmail}
            </p>
            <button
              onClick={handleLogout}
              className="p-1.5 rounded-lg text-text-muted hover:text-error hover:bg-error/10 transition-colors"
              title="Sign out"
            >
              <ArrowRightStartOnRectangleIcon className="w-4 h-4" />
            </button>
          </div>


        </div>
      </aside>
    </>
  );
}
