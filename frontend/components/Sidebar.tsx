"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Plus, 
  ChevronDown, 
  ChevronUp, 
  MoreHorizontal, 
  SquarePen
} from "lucide-react";
import { BACKEND_URL } from "@/lib/config";

// Premium styled double-bordered Z logo
const ZLogo = () => (
  <div className="w-8 h-8 rounded-lg border border-[#2F3338] bg-[#0B0D0F] p-[1.5px] flex items-center justify-center flex-shrink-0 shadow-[0_1px_2px_rgba(0,0,0,0.4)]">
    <div className="w-full h-full rounded-[6px] border border-[#2A2E33] bg-[#16181C] flex items-center justify-center font-bold text-white text-sm select-none">
      Z
    </div>
  </div>
);

// Custom face icon inside a rounded square
const AgentFaceIcon = ({ className }: { className?: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="3" y="3" width="18" height="18" rx="2.5" />
    <circle cx="9" cy="10" r="1" fill="currentColor" />
    <circle cx="15" cy="10" r="1" fill="currentColor" />
    <path d="M8 15s1.5 2 4 2 4-2 4-2" />
  </svg>
);

// Custom integrations/drawer icon
const IntegrationsIcon = ({ className }: { className?: string }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="3" y="6" width="18" height="15" rx="2" />
    <path d="M3 10h18" />
    <path d="M10 14h4" />
  </svg>
);

// Custom sidebar toggle icon (split rectangle, line on the left)
const SidebarToggleIcon = ({ className = "text-text-muted hover:text-text-main transition-colors" }: { className?: string }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="3" y="3" width="18" height="18" rx="2.5" />
    <path d="M9 3v18" />
  </svg>
);

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
}

export default function Sidebar({ isOpen, setIsOpen }: SidebarProps) {
  const [notionToken, setNotionToken] = useState("");
  const [notionDbId, setNotionDbId] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [recentSessions, setRecentSessions] = useState<any[]>([]);
  const [isIntegrationsExpanded, setIsIntegrationsExpanded] = useState(false);
  const pathname = usePathname();

  // Load state from localStorage on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("sidebar_open");
      if (saved !== null) {
        setIsOpen(JSON.parse(saved));
      } else {
        const isDesktop = window.innerWidth >= 768;
        setIsOpen(isDesktop);
      }
    }
  }, [setIsOpen]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem("sidebar_open", JSON.stringify(isOpen));
    }
  }, [isOpen]);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("notion_token") || "";
      const dbId = localStorage.getItem("notion_database_id") || "";
      setNotionToken(token);
      setNotionDbId(dbId);
      setIsConnected(!!(token && dbId));
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        const mySessions = JSON.parse(localStorage.getItem("my_sessions") || "[]");
        if (mySessions.length > 0) {
          fetch(`${BACKEND_URL}/sessions/history`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_ids: mySessions }),
          })
            .then((res) => {
              if (!res.ok) throw new Error("Failed to fetch history");
              return res.json();
            })
            .then((data) => {
              if (Array.isArray(data)) {
                setRecentSessions(data);
              }
            })
            .catch((err) => console.error("history fetch error", err));
        } else {
          setRecentSessions([]);
        }
      } catch (e) {
        console.error("loading history error", e);
      }
    }
  }, [pathname]);

  const handleSaveNotion = () => {
    if (typeof window !== "undefined") {
      localStorage.setItem("notion_token", notionToken.trim());
      localStorage.setItem("notion_database_id", notionDbId.trim());
      setIsConnected(!!(notionToken.trim() && notionDbId.trim()));
    }
  };

  const latestSessionId = recentSessions[0]?.session_id;

  return (
    <motion.div
      animate={{ width: isOpen ? 288 : 64 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
      className="fixed top-0 left-0 bottom-0 bg-[#0B0D0F] border-r border-[#1F242A] z-40 flex flex-col p-3 overflow-hidden text-white font-sans"
    >
      {/* Header Row */}
      <div className="h-12 flex items-center justify-between px-1 mb-4 flex-shrink-0 relative">
        {isOpen ? (
          <>
            <ZLogo />
            <button
              onClick={() => setIsOpen(false)}
              className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-[#1C1E22] transition-colors cursor-pointer"
            >
              <SidebarToggleIcon />
            </button>
          </>
        ) : (
          <button
            onClick={() => setIsOpen(true)}
            className="w-10 h-10 mx-auto flex items-center justify-center relative group cursor-pointer"
          >
            <div className="transition-all duration-200 group-hover:scale-90 group-hover:opacity-0">
              <ZLogo />
            </div>
            <div className="absolute opacity-0 scale-75 group-hover:opacity-100 group-hover:scale-100 transition-all duration-200 text-text-muted hover:text-white">
              <SidebarToggleIcon className="w-5 h-5 text-text-muted hover:text-white" />
            </div>
          </button>
        )}
      </div>

      {/* Pill selection container */}
      <div className="flex-shrink-0 mb-4 px-1">
        {isOpen ? (
          <div className="bg-[#16181C] border border-[#23272D] p-1 rounded-xl flex flex-col gap-1 w-full">
            <Link 
              href="/start"
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 ${
                pathname === "/start" 
                  ? "bg-[#22252A] text-white shadow-sm" 
                  : "text-text-muted hover:text-text-main hover:bg-[#1a1d22]/50"
              }`}
            >
              <SquarePen className="w-4 h-4" />
              <span>Chat</span>
            </Link>
            <Link 
              href={latestSessionId ? `/session/${latestSessionId}` : "/start"}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-semibold tracking-wide transition-all duration-200 ${
                pathname.startsWith("/session") 
                  ? "bg-[#22252A] text-white shadow-sm" 
                  : "text-text-muted hover:text-text-main hover:bg-[#1a1d22]/50"
              }`}
            >
              <AgentFaceIcon className="w-4 h-4" />
              <span>Agent</span>
            </Link>
          </div>
        ) : (
          <div className="bg-[#16181C] border border-[#23272D] p-1 rounded-xl flex flex-col gap-1 items-center w-12 py-1 mx-auto">
            <Link 
              href="/start"
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${
                pathname === "/start" 
                  ? "bg-[#22252A] text-white shadow-sm" 
                  : "text-text-muted hover:text-text-main hover:bg-[#1a1d22]/50"
              }`}
            >
              <SquarePen className="w-[18px] h-[18px]" />
            </Link>
            <Link 
              href={latestSessionId ? `/session/${latestSessionId}` : "/start"}
              className={`w-10 h-10 flex items-center justify-center rounded-lg transition-colors ${
                pathname.startsWith("/session") 
                  ? "bg-[#22252A] text-white shadow-sm" 
                  : "text-text-muted hover:text-text-main hover:bg-[#1a1d22]/50"
              }`}
            >
              <AgentFaceIcon className="w-[18px] h-[18px]" />
            </Link>
          </div>
        )}
      </div>

      {/* Action Item: New Chat */}
      <div className="flex-shrink-0 px-1 mb-4">
        {isOpen ? (
          <Link 
            href="/start"
            className="flex items-center gap-3 px-3 py-2 text-xs font-bold text-[#A0A5B0] hover:text-white rounded-lg hover:bg-[#16181C]/50 transition-all duration-200 group"
          >
            <div className="w-5 h-5 rounded-full bg-[#1F2226] border border-[#2A2E33] flex items-center justify-center text-text-muted group-hover:text-white group-hover:bg-[#2A2E33] transition-colors">
              <Plus className="w-3.5 h-3.5" />
            </div>
            <span>New Chat</span>
          </Link>
        ) : (
          <Link 
            href="/start"
            className="w-10 h-10 mx-auto rounded-full bg-[#1F2226] border border-[#2A2E33] hover:bg-[#2A2E33] flex items-center justify-center text-[#A0A5B0] hover:text-white transition-all duration-200"
          >
            <Plus className="w-5 h-5" />
          </Link>
        )}
      </div>

      {/* Action Item: Notion Setup / Integrations (AI PPT) */}
      <div className="flex-shrink-0 px-1 mb-4">
        {isOpen ? (
          <div className="flex flex-col gap-1">
            <div 
              onClick={() => setIsIntegrationsExpanded(!isIntegrationsExpanded)}
              className="flex items-center justify-between w-full px-3 py-2 text-xs font-bold text-[#38BDF8] hover:text-sky-300 rounded-lg hover:bg-[#16181C]/50 transition-all duration-200 cursor-pointer select-none"
            >
              <div className="flex items-center gap-3">
                <IntegrationsIcon className="w-4 h-4 text-text-muted" />
                <span>AI PPT</span>
              </div>
              <div className="text-text-muted">
                {isIntegrationsExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              </div>
            </div>
            
            {/* Smooth dropdown sub-menu */}
            <AnimatePresence>
              {isIntegrationsExpanded && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden bg-[#16181C] border border-[#23272D] rounded-xl p-3 mt-1 space-y-2"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] text-text-muted font-bold">Credentials</span>
                    {isConnected && (
                      <span className="flex h-1.5 w-1.5 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-complete opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-status-complete"></span>
                      </span>
                    )}
                  </div>
                  <input 
                    type="password" 
                    placeholder="Integration Token" 
                    value={notionToken}
                    onChange={(e) => setNotionToken(e.target.value)}
                    className="w-full bg-[#0B0D0F] border border-[#23272D] px-2 py-1 text-white text-[10px] focus:outline-none focus:border-accent rounded-md"
                  />
                  <input 
                    type="text" 
                    placeholder="Database ID" 
                    value={notionDbId}
                    onChange={(e) => setNotionDbId(e.target.value)}
                    className="w-full bg-[#0B0D0F] border border-[#23272D] px-2 py-1 text-white text-[10px] focus:outline-none focus:border-accent rounded-md"
                  />
                  <button 
                    onClick={handleSaveNotion}
                    className="w-full bg-accent text-[#0B0D0F] py-1 text-[9px] font-bold uppercase tracking-widest hover:opacity-90 transition-opacity rounded-md mt-1 cursor-pointer"
                  >
                    {isConnected ? "Update" : "Save"}
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        ) : (
          <button 
            onClick={() => {
              setIsOpen(true);
              setIsIntegrationsExpanded(true);
            }}
            className="w-10 h-10 mx-auto rounded-xl hover:bg-[#16181C] flex items-center justify-center text-[#A0A5B0] hover:text-white transition-all duration-200 cursor-pointer"
          >
            <IntegrationsIcon className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* History Section */}
      {isOpen && (
        <div className="flex-1 overflow-y-auto hide-scrollbar px-1 min-h-0">
          <h3 className="text-[10px] uppercase tracking-wider text-text-muted/50 font-bold mb-2 mt-4 px-3 select-none">Today</h3>
          <div className="space-y-1">
            {recentSessions.length === 0 ? (
              <p className="text-text-muted/40 text-[10px] italic px-3">No history yet.</p>
            ) : (
              recentSessions.map((s: any) => {
                const isActive = pathname === `/session/${s.session_id}`;
                return (
                  <Link 
                    href={`/session/${s.session_id}`} 
                    key={s.session_id} 
                    className={`flex items-center justify-between w-full px-3 py-2 text-xs rounded-lg group transition-all duration-200 ${
                      isActive 
                        ? "bg-[#16181C] text-white border border-[#23272D]" 
                        : "text-text-muted hover:text-white hover:bg-[#16181C]/30 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center min-w-0">
                      <span className="truncate font-medium">{s.startup_name}</span>
                    </div>
                    <MoreHorizontal className="w-3.5 h-3.5 text-text-muted/30 group-hover:text-text-muted opacity-0 group-hover:opacity-100 transition-all duration-200 flex-shrink-0 cursor-pointer hover:bg-panel p-[1px] rounded" />
                  </Link>
                );
              })
            )}
          </div>
        </div>
      )}
    </motion.div>
  );
}
