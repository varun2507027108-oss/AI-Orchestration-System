"use client";

import { motion } from "framer-motion";
import Link from "next/link";
import { Shield, Search, FileText, Database, Github, Megaphone } from "lucide-react";
import { CustomThemeToggler } from "@/components/theme-toggler";
import { InteractiveGridBackground } from "@/components/interactive-grid-background";

export default function LandingPage() {
  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="min-h-screen bg-base text-text-main font-mono selection:bg-accent selection:text-base">
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border-subtle bg-base/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="font-bold text-[13px] tracking-widest uppercase cursor-pointer" onClick={() => scrollTo("intent")}>
            BLUEPRINT
          </div>
          <div className="flex items-center gap-8 text-[11px] uppercase tracking-widest font-bold">
            <button onClick={() => scrollTo("intent")} className="hover:text-[#E8A33D] transition-colors">Intent</button>
            <button onClick={() => scrollTo("pipelines")} className="hover:text-[#E8A33D] transition-colors">Pipelines</button>
            <Link href="/start" className="text-[#E8A33D] hover:underline underline-offset-4 decoration-2">Start Pipeline</Link>
            <CustomThemeToggler />
          </div>
        </div>
      </nav>

      <main>
        <section id="intent" className="min-h-screen flex items-center pt-16 px-6 relative overflow-hidden">
          {/* Interactive Blueprint Grid Background */}
          <InteractiveGridBackground />

          {/* Subtle green glow */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#E8A33D]/5 rounded-full blur-[100px] pointer-events-none"></div>

          <div className="max-w-6xl mx-auto w-full z-10">
            <motion.div initial={{opacity: 0, y: 20}} animate={{opacity: 1, y: 0}} transition={{duration: 0.8}}>
              <h1 className="text-4xl md:text-6xl font-bold uppercase tracking-tight leading-[1.1] mb-6">
                The<br />Blueprint<br />
                <span className="text-[#E8A33D]">Engine</span>
              </h1>
              <p className="max-w-lg text-text-muted text-[13px] md:text-sm leading-relaxed mb-10 tracking-wide">
                Initialize an isolated workspace. Provide the core thesis. Submit your idea. Six specialized agents validate it, research the market, and produce the PRD, architecture spec, GitHub backlog, and launch copy you need to start building — the complete foundation, not a deployed app.
              </p>
              <div className="flex flex-col sm:flex-row items-center gap-4">
                <Link 
                  href="/start" 
                  className="w-full sm:w-auto bg-[#E8A33D] text-base px-8 py-4 text-[11px] font-bold uppercase tracking-[0.15em] hover:bg-[#E8A33D]/90 transition-all text-center border border-[#E8A33D]"
                >
                  Start a Pipeline
                </Link>
                <button 
                  onClick={() => scrollTo("pipelines")}
                  className="w-full sm:w-auto bg-panel border border-border-subtle text-text-main px-8 py-4 text-[11px] font-bold uppercase tracking-[0.15em] hover:bg-border-subtle transition-all text-center"
                >
                  Explore Agents
                </button>
              </div>
            </motion.div>
          </div>
        </section>

        <section id="pipelines" className="min-h-screen py-24 px-6 border-t border-border-subtle bg-panel relative">
          <div className="max-w-6xl mx-auto">
            <motion.div 
               initial={{opacity: 0}}
               whileInView={{opacity: 1}}
               viewport={{once: true}}
               transition={{duration: 0.6}}
            >
              <h2 className="text-2xl font-bold uppercase tracking-widest mb-2">The Engine</h2>
              <div className="text-[11px] text-text-muted uppercase tracking-widest mb-16">Coordinated Execution</div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {[
                  { name: "Startup Advisor", icon: Shield, desc: "Evaluates core thesis & market risks" },
                  { name: "Market Research", icon: Search, desc: "Analyzes competitors & opportunities" },
                  { name: "Product Manager", icon: FileText, desc: "Defines features & roadmaps" },
                  { name: "Architect", icon: Database, desc: "Designs database schemas & API routes" },
                  { name: "Engineering Manager", icon: Github, desc: "Plans sprint tasks & execution blocks" },
                  { name: "Marketing", icon: Megaphone, desc: "Drafts launch copy & campaigns" }
                ].map((agent, i) => (
                  <div key={i} className="border border-border-subtle bg-base p-8 hover:border-[#E8A33D]/30 transition-colors group relative overflow-hidden">
                    <div className="w-12 h-12 border border-border-subtle flex items-center justify-center mb-6 group-hover:border-[#E8A33D]/50 transition-colors">
                      <agent.icon className="w-6 h-6 text-[#E8A33D]" strokeWidth={1.5} />
                    </div>
                    <h3 className="text-[13px] font-bold uppercase tracking-widest mb-2 group-hover:text-[#E8A33D] transition-colors">{agent.name}</h3>
                    <p className="text-[11px] text-text-muted leading-relaxed">{agent.desc}</p>
                    
                    {/* Subtle corner glow on hover */}
                    <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-[#E8A33D]/10 rounded-full blur-[40px] opacity-0 group-hover:opacity-100 transition-opacity"></div>
                  </div>
                ))}
              </div>
            </motion.div>
          </div>
        </section>
      </main>
    </div>
  );
}
