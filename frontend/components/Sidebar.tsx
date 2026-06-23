"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { BACKEND_URL, GITHUB_CLIENT_ID } from "@/lib/config";
import { Plus, Github, FileText } from "lucide-react";

export default function Sidebar() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [notionToken, setNotionToken] = useState("");
  const [notionDbId, setNotionDbId] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [githubConnected, setGithubConnected] = useState(false);
  const [recentSessions, setRecentSessions] = useState<any[]>([]);
  const pathname = usePathname();
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // Load Notion creds
    const token = localStorage.getItem("notion_token");
    const dbId = localStorage.getItem("notion_database_id");
    if (token && dbId) {
      setNotionToken(token);
      setNotionDbId(dbId);
      setIsConnected(true);
    }

    // Load GitHub token
    const ghToken = localStorage.getItem("github_token");
    if (ghToken) {
      setGithubConnected(true);
    } else {
      setGithubConnected(false);
    }

    // Load Recent Sessions
    const mySessions = JSON.parse(localStorage.getItem("my_sessions") || "[]");
    if (mySessions.length > 0) {
      fetch(`${BACKEND_URL}/sessions/history`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_ids: mySessions }),
      })
        .then(res => res.json())
        .then(data => {
          if (Array.isArray(data)) setRecentSessions(data);
        })
        .catch(console.error);
    }
  }, [pathname]);

  const handleMouseEnter = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    setIsExpanded(true);
  };

  const handleMouseLeave = () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    timeoutRef.current = setTimeout(() => {
      setIsExpanded(false);
    }, 200);
  };

  const handleSaveNotion = () => {
    localStorage.setItem("notion_token", notionToken);
    localStorage.setItem("notion_database_id", notionDbId);
    setIsConnected(true);
  };

  const handleConnectGithub = () => {
    const redirectUri = window.location.origin + "/auth/github/callback";
    window.location.href = `https://github.com/login/oauth/authorize?client_id=${GITHUB_CLIENT_ID}&redirect_uri=${redirectUri}&scope=repo`;
  };

  const handleDisconnectGithub = () => {
    localStorage.removeItem("github_token");
    setGithubConnected(false);
  };

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return (
    <motion.div
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      animate={{ width: isExpanded ? 260 : 56 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="fixed top-0 left-0 bottom-0 bg-base border-r border-border-subtle z-40 flex flex-col overflow-y-auto hide-scrollbar overflow-x-hidden select-none"
    >
      {/* Brand logo at the top */}
      <div className="flex items-center justify-center w-14 h-16 shrink-0 relative">
        <img 
          src="/logo-dark.png" 
          alt="Logo" 
          className="w-11 h-11 object-contain transition-opacity duration-200 block dark:hidden" 
        />
        <img 
          src="/logo-light.png" 
          alt="Logo" 
          className="w-11 h-11 object-contain transition-opacity duration-200 hidden dark:block" 
        />
      </div>

      {/* Collapsed State Icon Dock (Fades out when expanded) */}
      <div
        className={`w-14 flex-1 flex flex-col items-center justify-between pb-4 transition-opacity duration-200 ${
          isExpanded ? "opacity-0 absolute top-16 left-0 pointer-events-none" : "opacity-100"
        }`}
      >
        {/* Middle: New Session */}
        <div className="flex-1 flex items-center justify-center">
          <Link
            href="/start"
            className="flex items-center justify-center w-10 h-10 rounded-sm hover:bg-panel transition-colors text-[#3b82f6] dark:text-[#E8A33D]"
            title="New Session"
          >
            <Plus className="w-5 h-5" />
          </Link>
        </div>

        {/* Bottom: Integrations (GitHub & Notion) */}
        <div className="flex flex-col items-center gap-4">
          {/* GitHub Icon Button */}
          <div className="relative">
            <button
              onClick={githubConnected ? handleDisconnectGithub : handleConnectGithub}
              className="flex items-center justify-center w-10 h-10 rounded-sm hover:bg-panel transition-colors text-[#3b82f6] dark:text-[#E8A33D]"
              title={githubConnected ? "Disconnect GitHub" : "Connect GitHub"}
            >
              <Github className="w-5 h-5" />
            </button>
            {githubConnected && (
              <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-status-complete rounded-full border-2 border-base animate-pulse"></span>
            )}
          </div>

          {/* Notion Icon Button */}
          <div className="relative">
            <div
              className="flex items-center justify-center w-10 h-10 rounded-sm hover:bg-panel transition-colors text-[#3b82f6] dark:text-[#E8A33D]"
              title={isConnected ? "Notion: Connected" : "Notion: Disconnected"}
            >
              <FileText className="w-5 h-5" />
            </div>
            {isConnected && (
              <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-status-complete rounded-full border-2 border-base animate-pulse"></span>
            )}
          </div>
        </div>
      </div>

      {/* Sidebar Content (Fades out when collapsed) */}
      <div 
        className={`w-[260px] flex-1 flex flex-col px-4 pb-4 transition-opacity duration-200 ${
          isExpanded ? "opacity-100" : "opacity-0 absolute top-16 left-0 pointer-events-none"
        }`}
      >
        <Link href="/start" className="block w-full bg-accent text-base text-center py-2 text-[10px] font-bold uppercase tracking-widest hover:opacity-90 transition-opacity mb-8">
          New Session
        </Link>

        <div className="mb-8">
          <h3 className="text-[10px] uppercase tracking-widest text-text-muted font-bold mb-3">Integrations</h3>
          <div className="space-y-3">
            <div className="space-y-2 bg-panel border border-border-subtle p-3 rounded-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-text-main font-bold">Notion</span>
                {isConnected && <span className="w-2 h-2 bg-status-complete rounded-full animate-pulse"></span>}
              </div>
              <input 
                type="password" 
                placeholder="Integration Token" 
                value={notionToken}
                onChange={(e) => setNotionToken(e.target.value)}
                className="w-full bg-base border border-border-subtle px-2 py-1 text-text-main text-[10px] focus:outline-none focus:border-accent rounded-sm"
              />
              <input 
                type="text" 
                placeholder="Database ID" 
                value={notionDbId}
                onChange={(e) => setNotionDbId(e.target.value)}
                className="w-full bg-base border border-border-subtle px-2 py-1 text-text-main text-[10px] focus:outline-none focus:border-accent rounded-sm"
              />
              <button 
                onClick={handleSaveNotion}
                className="w-full bg-accent text-base py-1 text-[9px] font-bold uppercase tracking-widest hover:opacity-90 transition-opacity rounded-sm mt-1"
              >
                {isConnected ? "Update" : "Save"}
              </button>
            </div>

            <div className="space-y-2 bg-panel border border-border-subtle p-3 rounded-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] text-text-main font-bold">GitHub</span>
                {githubConnected && <span className="w-2 h-2 bg-status-complete rounded-full animate-pulse"></span>}
              </div>
              {githubConnected ? (
                <button 
                  onClick={handleDisconnectGithub}
                  className="w-full bg-base border border-border-subtle text-text-muted py-1 text-[9px] font-bold uppercase tracking-widest hover:bg-border-subtle transition-opacity rounded-sm"
                >
                  Disconnect
                </button>
              ) : (
                <button 
                  onClick={handleConnectGithub}
                  className="w-full bg-accent text-base py-1 text-[9px] font-bold uppercase tracking-widest hover:opacity-90 transition-opacity rounded-sm"
                >
                  Connect GitHub
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="flex-1">
          <h3 className="text-[10px] uppercase tracking-widest text-text-muted font-bold mb-3">Recent Sessions</h3>
          <div className="space-y-2">
            {recentSessions.length === 0 ? (
              <p className="text-text-muted text-[10px] italic">No history yet.</p>
            ) : (
              recentSessions.map((s: any) => (
                <Link href={`/session/${s.session_id}`} key={s.session_id} className="block bg-panel border border-border-subtle p-2 hover:border-accent transition-colors">
                  <div className="text-text-main text-[11px] font-bold truncate">{s.startup_name}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className={`w-1.5 h-1.5 rounded-full ${s.status === 'complete' ? 'bg-status-complete' : s.status === 'failed' ? 'bg-status-failed' : 'bg-accent animate-pulse'}`}></div>
                    <span className="text-text-muted text-[9px] uppercase tracking-widest">{s.status}</span>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
