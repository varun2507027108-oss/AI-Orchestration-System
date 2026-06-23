"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { BACKEND_URL } from "@/lib/config";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { Activity, AlertTriangle, ArrowLeft } from "lucide-react";
import { CustomThemeToggler } from "@/components/theme-toggler";
import Sidebar from "@/components/Sidebar";

type PollingMap = {
  status: string;
  gate?: {
    resolved: boolean;
    result: {
      verdict: string;
      risk_score: number;
      reasoning: string;
      red_flags: string[];
    };
  };
};

function parseGithubRepo(input: string): string {
  if (!input) return "";
  let clean = input.trim();
  clean = clean.replace(/^(https?:\/\/)?(www\.)?github\.com\//i, "");
  clean = clean.replace(/\/$/, "");
  clean = clean.replace(/\.git$/, "");
  return clean;
}

export default function StartPage() {

  const router = useRouter();
  const [mode, setMode] = useState<"form" | "polling" | "gate" | "failed">("form");


  const [sessionId, setSessionId] = useState<string | null>(null);
  
  // Polling state
  const [pollData, setPollData] = useState<PollingMap | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isRevising, setIsRevising] = useState(false);
  const [revisedIdea, setRevisedIdea] = useState("");

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const formData = new FormData(e.currentTarget);
    const purpose = formData.get("purpose") as string;
    const building = formData.get("building") as string;
    const rawRepo = formData.get("github_repo") as string;
    const cleanRepo = parseGithubRepo(rawRepo);
    
    const payload = {
      startup_name: formData.get("startup_name") as string,
      idea: `Purpose: ${purpose}\n\nWhat we're building: ${building}`,
      github_repo: cleanRepo,
      github_token: localStorage.getItem("github_token") || null,
    };


    try {
      const res = await fetch(`${BACKEND_URL}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error("Failed to initialize session. System unreachable.");
      }

      const data = await res.json();
      setSessionId(data.session_id);

      // Save to local storage history
      try {
        const mySessions = JSON.parse(localStorage.getItem("my_sessions") || "[]");
        if (!mySessions.includes(data.session_id)) {
          mySessions.push(data.session_id);
          localStorage.setItem("my_sessions", JSON.stringify(mySessions));
        }
      } catch (e) {}

      setMode("polling");
    } catch (err: any) {
      setError(err.message);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (mode === "polling" || mode === "gate") {
      let interval: any;
      const poll = async () => {
        if (!sessionId) return;
        try {
          const res = await fetch(`${BACKEND_URL}/sessions/${sessionId}`);
          if (!res.ok) return;
          const data = await res.json();
          if (data.gate && !data.gate.result) {
            data.gate = { triggered: true, resolved: false, result: data.gate };
          }
          setPollData(data);

          if (data.status === "failed") {
            setMode("failed");
          } else if (data.status === "complete") {
            router.push(`/session/${sessionId}`);
          } else if (data.status === "awaiting_gate" && data.gate) {
            setMode("gate");
          } else {
             // ensure we're in polling mode if another status (e.g. running)
             setMode("polling");
          }
        } catch (err) {
          // Ignore network errors on polling, keep trying
        }
      };

      interval = setInterval(poll, 3000);
      poll(); // initial call
      return () => clearInterval(interval);
    }
  }, [mode, sessionId, router]);

  const handleGateAction = async (action: "continue" | "revise") => {
    if (!sessionId) return;
    
    // Continue
    try {
      setMode("polling");
      await fetch(`${BACKEND_URL}/sessions/${sessionId}/gate-decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: "continue" })
      });
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex min-h-screen bg-base text-text-main font-mono relative selection:bg-[#E8A33D] selection:text-base">
      <Sidebar />
      <div className="flex-1 min-w-0 md:pl-14">
        <nav className="fixed top-0 right-0 left-0 md:left-14 z-50 px-6 h-16 flex items-center justify-between border-b border-border-subtle bg-base/80 backdrop-blur-md">
        <Link href="/#intent" className="flex items-center gap-2 font-bold text-[13px] tracking-widest uppercase hover:text-[#E8A33D] transition-colors">
          <ArrowLeft className="w-4 h-4" />
          BLUEPRINT
        </Link>
        <CustomThemeToggler />
      </nav>

      <main className="pt-24 px-6 pb-24 flex justify-center min-h-screen relative overflow-hidden">
        {/* Glow accent */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[800px] bg-[#E8A33D]/5 rounded-full blur-[120px] pointer-events-none"></div>

        <div className="w-full max-w-xl z-10 relative">
          <AnimatePresence mode="wait">
            
            {mode === "form" && (
              <motion.div 
                key="form"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="bg-panel/80 backdrop-blur-lg border border-border-subtle p-8 md:p-12"
              >
                <div className="mb-10">
                  <h1 className="text-2xl font-bold uppercase tracking-widest mb-2">Initialize Workspace</h1>
                  <p className="text-xs text-text-muted uppercase tracking-widest">Connect your thesis to the execution engine.</p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-8">
                  <div className="group">
                    <label className="block text-[11px] font-bold uppercase tracking-widest text-[#E8A33D] mb-2">Company Name</label>
                    <input
                      name="startup_name"
                      required
                      className="w-full bg-base border border-border-subtle p-4 text-sm text-text-main focus:outline-none focus:border-[#E8A33D] transition-colors"
                      placeholder="e.g. Blueprint Labs"
                    />
                  </div>

                  <div className="group">
                    <label className="block text-[11px] font-bold uppercase tracking-widest text-[#E8A33D] mb-2">Purpose of Orchestration</label>
                    <textarea
                      name="purpose"
                      required
                      rows={3}
                      className="w-full bg-base border border-border-subtle p-4 text-sm text-text-main resize-none focus:outline-none focus:border-[#E8A33D] transition-colors leading-relaxed"
                      placeholder="Why does this exist? What problem does it solve?"
                    />
                  </div>

                  <div className="group">
                    <label className="block text-[11px] font-bold uppercase tracking-widest text-[#E8A33D] mb-2">What Are We Building?</label>
                    <textarea
                      name="building"
                      required
                      rows={4}
                      className="w-full bg-base border border-border-subtle p-4 text-sm text-text-main resize-none focus:outline-none focus:border-[#E8A33D] transition-colors leading-relaxed"
                      placeholder="Describe the software, features, and target users..."
                    />
                  </div>

                  <div className="group">
                    <label className="block text-[11px] font-bold uppercase tracking-widest text-text-muted mb-2">GitHub Repository (Optional)</label>
                    <div className="flex bg-base border border-border-subtle focus-within:border-[#E8A33D] transition-colors">
                      <input
                        name="github_repo"
                        className="w-full bg-transparent p-4 text-sm text-text-main focus:outline-none"
                        placeholder="e.g. owner/repo or full GitHub URL"
                      />
                    </div>
                  </div>


                  {error && (
                    <div className="p-4 border border-status-failed bg-status-failed/10 text-status-failed text-xs uppercase tracking-widest">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full bg-base border border-[#E8A33D] text-[#E8A33D] py-4 text-xs font-bold uppercase tracking-[0.15em] hover:bg-[#E8A33D] hover:text-base transition-colors relative"
                  >
                    {loading ? (
                      <span className="flex items-center justify-center gap-3">
                         <span className="animate-spin w-4 h-4 border-2 border-current border-t-transparent rounded-full"></span>
                         BOOTING...
                      </span>
                    ) : (
                      "Initialize Pipeline"
                    )}
                  </button>
                </form>
              </motion.div>
            )}

            {mode === "polling" && (
              <motion.div 
                key="polling"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="bg-panel/80 backdrop-blur-lg border border-[#E8A33D]/30 p-12 text-center h-[400px] flex flex-col items-center justify-center"
              >
                <div className="relative mb-8">
                  <div className="absolute inset-0 bg-[#E8A33D]/20 blur-xl rounded-full animate-pulse"></div>
                  <Activity className="w-12 h-12 text-[#E8A33D] relative z-10" />
                </div>
                <h2 className="text-xl font-bold uppercase tracking-widest mb-3">Agents Working</h2>
                <p className="text-xs text-text-muted uppercase tracking-widest whitespace-pre-wrap">
                  {pollData?.status 
                    ? `Current Status: ${pollData.status}` 
                    : "Establishing connection to orchestration layer..."}
                </p>
                <div className="mt-8 w-full max-w-xs h-1 bg-base border border-border-subtle overflow-hidden relative">
                   <motion.div 
                     className="absolute top-0 bottom-0 left-0 bg-[#E8A33D]" 
                     initial={{ width: "0%" }}
                     animate={{ width: "100%" }}
                     transition={{ duration: 2, repeat: Infinity }}
                   />
                </div>
              </motion.div>
            )}

            {mode === "gate" && pollData?.gate?.result && (
              <motion.div 
                key="gate"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-panel border border-[#E8A33D] p-8 md:p-12"
              >
                <div className="flex items-center gap-3 mb-6 pb-6 border-b border-border-subtle">
                  <AlertTriangle className="w-6 h-6 text-[#E8A33D]" />
                  <h2 className="text-lg font-bold uppercase tracking-widest text-[#E8A33D]">Gate Intervention Required</h2>
                </div>

                <div className="space-y-6">
                  <div>
                    <div className="text-[11px] uppercase tracking-widest text-[#E8A33D] font-bold mb-2">Verdict & Risk Score</div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm">{pollData.gate.result.verdict}</span>
                      <span className="bg-base border border-border-subtle px-3 py-1 text-xs font-bold">{(pollData.gate.result.risk_score * 100).toFixed(0)}% RISK</span>
                    </div>
                  </div>

                  <div>
                    <div className="text-[11px] uppercase tracking-widest text-text-muted font-bold mb-2">Reasoning</div>
                    <div className="text-sm leading-relaxed text-text-main bg-base p-4 border border-border-subtle">
                      {pollData.gate.result.reasoning}
                    </div>
                  </div>

                  <div>
                    <div className="text-[11px] uppercase tracking-widest text-status-failed font-bold mb-2">Identified Red Flags</div>
                    <ul className="space-y-2">
                      {pollData.gate.result.red_flags.map((flag, idx) => (
                        <li key={idx} className="text-xs flex items-start gap-2 bg-status-failed/5 p-3 border border-status-failed/20 text-status-failed">
                          <span className="shrink-0 mt-0.5">•</span>
                          <span>{flag}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  <div className="pt-6 border-t border-border-subtle">
                    {isRevising ? (
                      <div className="space-y-4">
                        <textarea
                          autoFocus
                          rows={4}
                          value={revisedIdea}
                          onChange={e => setRevisedIdea(e.target.value)}
                          className="w-full bg-base border border-border-subtle p-4 text-sm text-text-main resize-none focus:outline-none focus:border-[#E8A33D] transition-colors leading-relaxed"
                          placeholder="Revise your thesis..."
                        />
                        <div className="flex flex-col sm:flex-row gap-4">
                          <button 
                            onClick={async () => {
                              if (!sessionId) return;
                              try {
                                setMode("polling");
                                setIsRevising(false);
                                await fetch(`${BACKEND_URL}/sessions/${sessionId}/gate-decision`, {
                                  method: "POST",
                                  headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify({ decision: "revise", revised_idea: revisedIdea })
                                });
                              } catch (err) { console.error(err); }
                            }}
                            disabled={!revisedIdea.trim()}
                            className="flex-1 bg-[#E8A33D] text-base py-3 text-xs font-bold uppercase tracking-widest hover:bg-[#E8A33D]/90 transition-colors disabled:opacity-50"
                          >
                            Submit Revision
                          </button>
                          <button 
                            onClick={() => setIsRevising(false)}
                            className="flex-1 bg-base text-text-main border border-border-subtle py-3 text-xs font-bold uppercase tracking-widest hover:border-[#E8A33D] transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-col sm:flex-row gap-4">
                        <button 
                          onClick={() => handleGateAction("continue")}
                          className="flex-1 bg-[#E8A33D] text-base py-3 text-xs font-bold uppercase tracking-widest hover:bg-[#E8A33D]/90 transition-colors"
                        >
                          Acknowledge & Continue
                        </button>
                        <button 
                          onClick={() => setIsRevising(true)}
                          className="flex-1 bg-base border border-border-subtle py-3 text-xs font-bold uppercase tracking-widest hover:border-[#E8A33D] hover:text-[#E8A33D] transition-colors"
                        >
                          Revise Idea
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            )}

            {mode === "failed" && (
              <motion.div 
                key="failed"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="bg-panel border border-status-failed p-12 text-center"
              >
                <div className="text-status-failed mb-6 font-bold uppercase tracking-widest">Orchestration Failed</div>
                <p className="text-text-muted text-sm mb-8">The pipeline encountered a critical error during initialization.</p>
                <button 
                  onClick={() => setMode("form")}
                  className="bg-base border border-border-subtle px-8 py-3 text-xs font-bold uppercase tracking-widest hover:text-text-main transition-colors"
                >
                  Retry Initialization
                </button>
              </motion.div>
            )}

          </AnimatePresence>
        </div>
      </main>
      </div>
    </div>
  );
}
