"use client";

import { use, useEffect, useState, ChangeEvent } from "react";
import { BACKEND_URL } from "@/lib/config";
import { motion, AnimatePresence } from "framer-motion";

import { CustomThemeToggler } from "@/components/theme-toggler";
import Sidebar from "@/components/Sidebar";
import dynamic from 'next/dynamic';

const ReactFlowERD = dynamic(() => import("@/components/ReactFlowERD"), {
  ssr: false,
  loading: () => <div className="text-text-muted text-[11px] font-mono p-4 animate-pulse">Loading diagram engine...</div>
});

const AGENT_COLORS: Record<string, string> = {
  'startup_advisor': 'bg-[#E8A33D]',
  'market_research': 'bg-[#A78BFA]',
  'product_manager': 'bg-[#60A5FA]',
  'architect': 'bg-[#34D399]',
  'engineering_manager': 'bg-[#F472B6]',
  'marketing': 'bg-[#F87171]'
};

const THINKING_TEXT: Record<string, string> = {
  'startup_advisor': 'Evaluating market risks...',
  'market_research': 'Scanning competitor landscape...',
  'product_manager': 'Defining feature scope...',
  'architect': 'Designing database schema...',
  'engineering_manager': 'Structuring sprint backlog...',
  'marketing': 'Drafting launch assets...'
};

// -------- Subcomponents -------- //

function PipelineNode({ id, name, status, delay = 0 }: { id: string, name: string, status?: string, delay?: number }) {
  const isComplete = status === 'complete';
  const isRunning = status === 'running';
  const isFailed = status === 'failed';

  let borderColor = 'border-border-subtle';
  let badgeColor = '';
  let badgeBg = '';

  if (isComplete) {
    borderColor = 'border-status-complete';
    badgeColor = 'text-status-complete';
    badgeBg = 'bg-status-complete/10';
  } else if (isRunning) {
    borderColor = 'border-accent';
    badgeColor = 'text-accent';
    badgeBg = 'bg-accent/10';
  } else if (isFailed) {
    borderColor = 'border-status-failed';
    badgeColor = 'text-status-failed';
    badgeBg = 'bg-status-failed/10';
  } else {
    badgeColor = 'text-status-pending';
    badgeBg = 'bg-status-pending/5';
  }

  const agentColor = AGENT_COLORS[id] || 'bg-status-pending';

  return (
    <div className="flex flex-col items-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, delay }}
        className={`border ${borderColor} bg-panel px-4 py-3.5 flex items-center gap-3 w-48 shadow-none transition-all duration-300 z-10 relative`}
      >
        <div className={`w-2 h-2 rounded-none ${agentColor} shrink-0 ${isRunning ? 'animate-pulse' : ''}`}></div>
        <span className={`text-[10px] uppercase tracking-widest truncate ${isComplete || isRunning ? 'text-text-main' : 'text-text-muted'}`} title={name}>{name}</span>
        <span className={`ml-auto text-[8px] font-bold px-1.5 py-0.5 rounded-full ${badgeColor} ${badgeBg} ${isRunning ? 'animate-pulse font-bold' : ''}`}>
          {isRunning ? (THINKING_TEXT[id] || 'THINKING') : status ? status.toUpperCase() : 'WAIT'}
        </span>
      </motion.div>
      <AnimatePresence>
        {isRunning && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 0.7, height: 'auto', y: 4 }}
            exit={{ opacity: 0, height: 0 }}
            className="text-[10px] text-accent uppercase tracking-widest font-bold mt-1 text-center"
          >
            <motion.span
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
            >
              {THINKING_TEXT[id] || 'AI is analyzing...'}
            </motion.span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ConnectorLine({ active, gateActive }: { active: boolean, gateActive?: boolean }) {
  let lineClass = active ? 'bg-status-complete' : 'bg-border-subtle';
  if (gateActive) {
    lineClass = 'bg-status-complete animate-pulse shadow-[0_0_8px_#3FB950]';
  }
  return (
    <>
      {/* Vertical line on mobile */}
      <div className={`h-6 w-px md:hidden relative ${lineClass}`} />
      {/* Horizontal line on desktop */}
      <div className={`hidden md:block w-8 h-px relative ${lineClass}`} />
    </>
  );
}

function PipelineView({ stages }: { stages: Record<string, any> }) {
  if (!stages) return null;

  const sA = stages.startup_advisor?.status;
  const mR = stages.market_research?.status;
  const pM = stages.product_manager?.status;
  const ar = stages.architect?.status;
  const em = stages.engineering_manager?.status;
  const mk = stages.marketing?.status;

  return (
    <div className="bg-base border border-border-subtle p-8 shadow-none text-text-main font-mono">
      <div className="flex items-center justify-between mb-8 pb-4 border-b border-border-subtle">
        <h3 className="text-lg text-text-main uppercase tracking-widest">Execution Trace</h3>
        <span className="text-[10px] text-text-muted uppercase tracking-widest font-bold">Workflow DAG</span>
      </div>

      <div className="w-full max-w-full mx-auto overflow-x-auto pb-4 hide-scrollbar">
        <div className="flex flex-col md:flex-row items-center justify-start xl:justify-center w-full md:w-max mx-auto px-4 md:px-8">
          {/* Left part: Advisor -> Market Res -> Product Manager */}
          <div className="flex flex-col md:flex-row items-center">
            <PipelineNode id="startup_advisor" name="Advisor" status={sA} delay={0} />
            <ConnectorLine active={sA === 'complete'} gateActive={sA === 'awaiting_gate'} />
            <PipelineNode id="market_research" name="Market Res" status={mR} delay={0.1} />
            <ConnectorLine active={mR === 'complete'} />
            <PipelineNode id="product_manager" name="Product Mgr" status={pM} delay={0.2} />
          </div>

          {/* Fork Section */}
          <div className="flex flex-col md:flex-row items-center relative w-full md:w-auto">
            {/* On mobile: vertical line between Product Manager and the branches */}
            <div className={`h-6 w-px md:hidden ${pM === 'complete' ? 'bg-status-complete' : 'bg-border-subtle'}`} />

            {/* On desktop: horizontal connector from Product Manager to the bracket */}
            <div className={`hidden md:block w-8 h-px ${pM === 'complete' ? 'bg-status-complete' : 'bg-border-subtle'}`} />

            {/* The two parallel branches */}
            <div className="relative pl-0 md:pl-8 flex flex-col gap-6 md:gap-8 w-full md:w-auto">
              {/* Desktop branch bracket */}
              <div
                className={`hidden md:block absolute left-0 top-[26px] bottom-[26px] w-8 border-l border-t border-b ${pM === 'complete' ? 'border-status-complete' : 'border-border-subtle'
                  }`}
              />

              {/* Row 1: Architect -> Eng Manager */}
              <div className="flex flex-col md:flex-row items-center">
                {/* On mobile: vertical line connection */}
                <div className={`h-6 w-px md:hidden ${pM === 'complete' ? 'bg-status-complete' : 'bg-border-subtle'}`} />
                <PipelineNode id="architect" name="Architect" status={ar} delay={0.3} />
                <ConnectorLine active={ar === 'complete'} />
                <PipelineNode id="engineering_manager" name="Eng Manager" status={em} delay={0.4} />
              </div>

              {/* Row 2: Marketing */}
              <div className="flex flex-col md:flex-row items-center">
                {/* On mobile: vertical line connection */}
                <div className={`h-6 w-px md:hidden ${pM === 'complete' ? 'bg-status-complete' : 'bg-border-subtle'}`} />
                <PipelineNode id="marketing" name="Marketing" status={mk} delay={0.3} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GateCard({ id, gate }: { id: string, gate: any }) {
  const [revisedIdea, setRevisedIdea] = useState("");
  const [mode, setMode] = useState<"view" | "revise">("view");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (decision: "continue" | "revise") => {
    setLoading(true);
    try {
      await fetch(`${BACKEND_URL}/sessions/${id}/gate-decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decision === 'continue' ? { decision } : { decision, revised_idea: revisedIdea }),
      });
    } catch (e) {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-panel border-2 border-accent p-6 rounded-none relative overflow-hidden"
    >
      {/* Pulser effect background */}
      <div className="absolute top-0 right-0 w-full h-full bg-accent/5 animate-pulse pointer-events-none"></div>
      <div className="relative z-10">
        <div className="flex items-center gap-3 mb-6 border-b border-border-subtle pb-4">
          <div className="w-2 h-2 rounded-full bg-accent animate-ping"></div>
          <h2 className="text-accent text-sm uppercase tracking-widest font-bold">Human-in-the-Loop Review Required</h2>
        </div>

        <div className="space-y-4 mb-8">
          <div className="flex justify-between items-baseline border-b border-border-subtle pb-2">
            <span className="text-[11px] text-text-muted uppercase tracking-widest font-bold">Verdict</span>
            <span className="text-[12px] text-text-main font-bold">{gate.result?.verdict}</span>
          </div>
          <div className="flex justify-between items-baseline border-b border-border-subtle pb-2">
            <span className="text-[11px] text-text-muted uppercase tracking-widest font-bold">Risk Score</span>
            <span className="text-[13px] text-accent font-bold">{gate.result?.risk_score}</span>
          </div>
          <div className="text-[13px] leading-relaxed text-text-main pt-2">
            {gate.result?.reasoning}
          </div>
          <div className="bg-base border border-border-subtle p-4 mt-4">
            <span className="block text-[11px] text-status-failed uppercase tracking-widest mb-3 font-bold">Red Flags Triggered:</span>
            <ul className="text-xs text-text-main space-y-3">
              {gate.result?.red_flags?.map((r: string, i: number) => (
                <li key={i} className="flex gap-3">
                  <span className="text-status-failed text-[10px] mt-0.5">■</span> {r}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {mode === 'view' ? (
          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={() => handleSubmit('continue')}
              disabled={loading}
              className="flex-1 bg-accent text-base uppercase tracking-widest py-3 text-[10px] font-bold hover:opacity-90 transition-opacity"
            >
              Force Execute
            </button>
            <button
              onClick={() => setMode('revise')}
              disabled={loading}
              className="flex-1 bg-panel border border-border-subtle text-text-main uppercase tracking-widest py-3 text-[10px] hover:bg-base hover:border-text-muted transition-colors font-bold"
            >
              Revise Parameters
            </button>
          </div>
        ) : (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="space-y-4">
            <textarea
              className="w-full bg-base border border-border-subtle p-4 text-[12px] text-text-main focus:outline-none focus:border-accent transition-colors rounded-none"
              rows={4}
              placeholder="Refine your thesis..."
              value={revisedIdea}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setRevisedIdea(e.target.value)}
            />
            <div className="flex gap-3">
              <button
                onClick={() => handleSubmit('revise')}
                disabled={loading || !revisedIdea.trim()}
                className="flex-[2] bg-accent text-base font-bold uppercase tracking-widest py-3 text-[10px] hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                Submit Revision
              </button>
              <button
                onClick={() => setMode('view')}
                disabled={loading}
                className="flex-1 border border-border-subtle bg-panel text-text-main font-bold uppercase tracking-widest text-[10px] hover:bg-base transition-colors"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}

function DataBlock({ label, value, isLongText, list }: { label: string, value?: string, isLongText?: boolean, list?: string[] }) {
  const isListValid = list && Array.isArray(list) && list.length > 0;
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">{label}</span>
      <div className={`border border-border-subtle bg-panel p-4 text-text-main text-sm leading-relaxed ${isLongText ? 'whitespace-pre-wrap' : ''}`}>
        {value && <>{value}</>}
        {isListValid && (
          <ul className="space-y-2">
            {list.map((item, i) => (
              <li key={i} className="flex gap-3">
                <span className="text-text-muted shrink-0 text-[10px] mt-0.5 border border-border-subtle px-1 leading-[1.2rem]">{String(i + 1).padStart(2, '0')}</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        )}
        {!value && !isListValid && <span className="text-status-pending italic">No data</span>}
      </div>
    </div>
  )
}

function ArtifactDisplay({ stage, data }: { stage: string; data: any }) {
  if (!data) return <div className="p-8 text-text-muted text-sm italic">Artifact unavailable.</div>;

  const content = () => {
    switch (stage) {
      case 'startup_advisor':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-6">
              <DataBlock label="Verdict" value={data.verdict} />
              <DataBlock label="Risk Score" value={data.risk_score?.toFixed(2)} />
            </div>
            <DataBlock label="Reasoning" value={data.reasoning} isLongText />
            {data.red_flags?.length > 0 && (
              <DataBlock label="Red Flags Triggered" list={data.red_flags} />
            )}
          </div>
        );
      case 'market_research':
        return (
          <div className="space-y-6">
            <DataBlock label="TAM Estimate" value={data.tam_estimate} />
            <DataBlock label="Key Trends" list={data.trends} />
            <div className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Competitor Force Matrix</span>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {data.competitors?.map((c: any, i: number) => (
                  <div key={i} className="border border-border-subtle bg-panel p-4">
                    <div className="text-text-main text-[13px] uppercase font-bold mb-1">{c.name}</div>
                    <div className="text-[12px] text-text-muted mb-3 leading-relaxed">{c.description}</div>
                    {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="text-[10px] text-accent hover:underline uppercase tracking-widest line-clamp-1">{c.url} ↗</a>}
                  </div>
                ))}
              </div>
            </div>
            <DataBlock label="Verified Sources" list={data.sources} />
          </div>
        );
      case 'product_manager':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {data.goals && Array.isArray(data.goals) && data.goals.length > 0 ? (
                <DataBlock label="Goals" list={data.goals} />
              ) : (
                <DataBlock label="Goals" value={typeof data.goals === 'string' ? data.goals : "No data"} />
              )}
              {data.success_metrics && Array.isArray(data.success_metrics) && data.success_metrics.length > 0 ? (
                <DataBlock label="Success Metrics" list={data.success_metrics} />
              ) : (
                <DataBlock label="Success Metrics" value={typeof data.success_metrics === 'string' ? data.success_metrics : "No data"} />
              )}
            </div>
            <DataBlock label="Problem Statement" value={data.problem_statement} isLongText />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <DataBlock label="User Stories" list={data.user_stories} />

              <div className="flex flex-col gap-2">
                <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Core Features</span>
                <div className="border border-border-subtle bg-panel p-4 space-y-4">
                  {data.features?.map((f: any, i: number) => (
                    <div key={i} className="flex flex-col gap-1 pb-4 border-b border-border-subtle last:border-0 last:pb-0">
                      <div className="flex justify-between items-start gap-4">
                        <span className="text-text-main text-[13px]">{f.name}</span>
                        <span className="text-[9px] bg-base border border-border-subtle px-1.5 py-0.5 text-text-muted uppercase font-bold shrink-0">{f.priority}</span>
                      </div>
                      <span className="text-text-muted text-[11px] leading-relaxed">{f.description}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Roadmap Phases</span>
              <div className="border border-border-subtle bg-panel p-4 space-y-6">
                {data.roadmap_phases?.map((p: any, i: number) => (
                  <div key={i} className="flex flex-col gap-3">
                    <div className="text-text-main text-[11px] font-bold uppercase tracking-widest border-b border-border-subtle pb-2">{p.name}</div>
                    <ul className="space-y-2 text-[12px] text-text-muted">
                      {p.items?.map((item: string, idx: number) => <li key={idx} className="flex gap-2"><span className="text-border-subtle">-</span> {item}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      case 'architect':
        return (
          <div className="space-y-6">
            <DataBlock label="System Design Notes" value={data.system_design_notes} isLongText />

            <div className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Schema SQL Definition</span>
              <pre className="border border-border-subtle bg-panel p-4 text-[12px] text-text-main overflow-x-auto whitespace-pre">
                {data.db_schema_sql}
              </pre>
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Entity Relationship Diagram</span>
              <ReactFlowERD chart={data.db_schema_mermaid} />
            </div>

            <div className="flex flex-col gap-2">
              <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">API Routes Binding</span>
              <div className="border border-border-subtle bg-panel overflow-hidden">
                <table className="w-full text-left text-sm border-collapse min-w-full">
                  <thead>
                    <tr className="border-b border-border-subtle uppercase text-[9px] text-text-muted bg-base/50">
                      <th className="py-2.5 px-4 font-normal whitespace-nowrap">Method</th>
                      <th className="py-2.5 px-4 font-normal whitespace-nowrap">Path</th>
                      <th className="py-2.5 px-4 font-normal">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.api_endpoints?.map((ep: any, i: number) => (
                      <tr key={i} className="border-b border-border-subtle last:border-0 hover:bg-base/30 transition-colors">
                        <td className="py-3 px-4 text-[11px] text-accent font-bold whitespace-nowrap">{ep.method}</td>
                        <td className="py-3 px-4 text-[11px] text-text-main">{ep.path}</td>
                        <td className="py-3 px-4 text-text-muted text-[11px]">{ep.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        );
      case 'engineering_manager':
        return (
          <div className="flex flex-col gap-6">
            {data.sprints?.map((sprint: any, i: number) => (
              <div key={i} className="border border-border-subtle bg-panel p-4">
                <div className="text-[11px] uppercase tracking-widest font-bold text-text-main border-b border-border-subtle pb-2 mb-4">{sprint.name}</div>
                <div className="space-y-4">
                  {sprint.issue_titles?.map((title: string, idx: number) => {
                    const issue = data.issues?.find((iss: any) => iss.title === title);
                    if (!issue) return null;
                    return (
                      <div key={idx} className="pb-4 border-b border-border-subtle last:border-0 last:pb-0">
                        <div className="flex justify-between items-start mb-2 gap-2">
                          <div className="text-text-main text-[13px] font-bold">{issue.title}</div>
                          {issue.story_points && (
                            <span className="text-[9px] bg-purple-500/20 text-purple-400 border border-purple-500/30 px-1.5 py-0.5 uppercase tracking-widest font-bold shrink-0">
                              {issue.story_points} PT
                            </span>
                          )}
                        </div>
                        <div className="text-text-muted text-[12px] mb-3 leading-relaxed">{issue.body}</div>
                        <div className="flex flex-wrap gap-2">
                          {issue.labels?.map((l: string, lidx: number) => (
                            <span key={lidx} className="text-[9px] bg-base border border-border-subtle text-text-muted px-1.5 py-0.5 uppercase tracking-widest font-bold">
                              {l}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {data.definition_of_done && data.definition_of_done.length > 0 && (
                <DataBlock label="Definition of Done" list={data.definition_of_done} />
              )}
              {data.tech_debt_risks && data.tech_debt_risks.length > 0 && (
                <DataBlock label="Tech Debt Risks" list={data.tech_debt_risks} />
              )}
            </div>
            
            {data.team_size_recommended && (
              <DataBlock label="Recommended Team Size" value={data.team_size_recommended} />
            )}
          </div>
        );
      case 'marketing':
        return (
          <div className="space-y-6">
            <DataBlock label="Landing Page Copy" value={data.landing_copy} isLongText />
            <DataBlock label="LinkedIn Social Post" value={data.linkedin_post} isLongText />
            
            {data.pricing_tiers && data.pricing_tiers.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Pricing Strategy</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {data.pricing_tiers.map((tier: any, i: number) => (
                    <div key={i} className="border border-border-subtle bg-panel p-4">
                      <div className="flex justify-between items-center mb-3 border-b border-border-subtle pb-2">
                        <span className="text-text-main text-[13px] font-bold uppercase">{tier.model}</span>
                        <span className="text-accent text-[12px] font-bold">{tier.price}</span>
                      </div>
                      <ul className="space-y-2 text-[12px] text-text-muted">
                        {tier.features?.map((f: string, fidx: number) => (
                          <li key={fidx} className="flex gap-2"><span className="text-border-subtle">-</span> {f}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.email_sequence && data.email_sequence.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Email Drip Campaign</span>
                <div className="border-l-2 border-accent/30 pl-4 space-y-6">
                  {data.email_sequence.map((step: any, i: number) => (
                    <div key={i} className="relative">
                      <div className="absolute -left-[21px] top-1 w-2 h-2 rounded-full bg-accent"></div>
                      <div className="flex justify-between items-baseline mb-1">
                        <span className="text-text-main text-[12px] font-bold">{step.subject}</span>
                        <span className="text-[9px] text-text-muted uppercase tracking-widest">{step.send_day}</span>
                      </div>
                      <div className="text-[10px] text-accent uppercase tracking-widest mb-2 font-bold">Goal: {step.goal}</div>
                      <p className="text-text-muted text-[12px] leading-relaxed whitespace-pre-wrap">{step.body}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.ninety_day_plan && data.ninety_day_plan.length > 0 && (
              <DataBlock label="90-Day Launch Plan" list={data.ninety_day_plan} />
            )}

            {data.launch_channels && data.launch_channels.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className="text-[11px] uppercase tracking-widest text-text-muted font-bold">Launch Channels</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {data.launch_channels.map((ch: any, i: number) => (
                    <div key={i} className="border border-border-subtle bg-panel p-4">
                      <div className="text-text-main text-[13px] font-bold uppercase mb-1">{ch.channel}</div>
                      <div className="text-[12px] text-text-muted mb-2 leading-relaxed">{ch.tactic}</div>
                      <div className="text-[10px] text-accent uppercase tracking-widest font-bold">Reach: {ch.expected_reach}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      default:
        return null;
    }
  }

  return (
    <motion.div
      key={stage}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
    >
      {content()}
    </motion.div>
  )
}

const STAGES = [
  'startup_advisor',
  'market_research',
  'product_manager',
  'architect',
  'engineering_manager',
  'marketing'
];

const STAGE_LABELS: Record<string, string> = {
  'startup_advisor': 'Startup Advisor',
  'market_research': 'Market Research',
  'product_manager': 'Product Manager',
  'architect': 'Architect',
  'engineering_manager': 'Eng Manager',
  'marketing': 'Marketing'
};

function RemoteArtifactViewer({ sessionId, stage, stageStatus, artifactData }: { sessionId: string, stage: string, stageStatus?: string, artifactData?: any }) {
  const [data, setData] = useState<any>(artifactData || null);

  useEffect(() => {
    // If we already have the data from the main poll, use it.
    if (artifactData) {
      setData(artifactData);
      return;
    }

    // If stage isn't complete, don't try to fetch yet.
    if (stageStatus !== 'complete') {
      return;
    }

    let isMounted = true;
    const fetchArtifact = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/sessions/${sessionId}/artifacts/${stage}`);
        if (res.ok) {
          const json = await res.json();
          if (isMounted) setData(json);
        }
      } catch (e) { }
    };
    fetchArtifact();
    return () => { isMounted = false; };
  }, [sessionId, stage, stageStatus, artifactData]);

  if (stageStatus !== 'complete' && !data) {
    return <div className="text-text-muted font-mono text-[11px] uppercase tracking-widest italic flex items-center justify-center h-48 border border-dashed border-border-subtle bg-base">Awaiting operational output...</div>;
  }
  if (!data) return <div className="text-accent font-mono text-[11px] uppercase tracking-widest flex items-center justify-center h-48 animate-pulse border border-border-subtle bg-panel">Downloading artifact data...</div>;

  return <ArtifactDisplay stage={stage} data={data} />;
}

function TabsViewer({ sessionId, activeStatuses, artifacts }: { sessionId: string, activeStatuses: Record<string, string>, artifacts: Record<string, any> }) {
  const [activeTab, setActiveTab] = useState(STAGES[0]);
  const [manualMode, setManualMode] = useState(false);

  // Auto-advance logic
  useEffect(() => {
    if (manualMode) return;

    // Find currently running stage
    const runningStage = STAGES.find(s => activeStatuses[s] === 'running');
    if (runningStage) {
      setActiveTab(runningStage);
    } else {
      // If none running, find latest complete
      const latestComplete = STAGES.filter(s => activeStatuses[s] === 'complete').pop();
      if (latestComplete) setActiveTab(latestComplete);
    }
  }, [activeStatuses, manualMode]);

  const handleTabClick = (s: string) => {
    setManualMode(true);
    setActiveTab(s);
  };

  return (
    <div className="border border-border-subtle bg-base flex flex-col shadow-none mt-8">
      <div className="flex overflow-x-auto border-b border-border-subtle hide-scrollbar bg-panel">
        {STAGES.map(s => {
          const isActive = activeTab === s;
          const status = activeStatuses[s];
          const isComplete = status === 'complete';
          const isRunning = status === 'running';
          const isFailed = status === 'failed';

          let badgeColor = 'text-status-pending';
          let badgeBg = 'bg-status-pending/5';
          if (isComplete) {
            badgeColor = 'text-status-complete';
            badgeBg = 'bg-status-complete/10';
          } else if (isRunning) {
            badgeColor = 'text-accent';
            badgeBg = 'bg-accent/10';
          } else if (isFailed) {
            badgeColor = 'text-status-failed';
            badgeBg = 'bg-status-failed/10';
          }

          return (
            <button
              key={s}
              onClick={() => handleTabClick(s)}
              className={`shrink-0 px-5 py-4 font-mono text-[10px] font-bold uppercase tracking-[0.1em] transition-colors relative flex items-center gap-3 ${isActive ? 'text-text-main bg-base' : 'text-text-muted hover:bg-base/50 hover:text-text-main'
                }`}
            >
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 ${AGENT_COLORS[s]} opacity-80`}></div>
                {STAGE_LABELS[s]}
              </div>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${badgeColor} ${badgeBg}`}>
                {status ? status.toUpperCase() : 'WAIT'}
              </span>
              {isActive && (
                <motion.div layoutId="activeTabIndicator" className="absolute bottom-0 left-0 right-0 h-[2px] bg-accent" />
              )}
            </button>
          )
        })}
      </div>
      <div className="p-6 md:p-8 min-h-[400px]">
        <AnimatePresence mode="wait">
          <RemoteArtifactViewer
            key={activeTab}
            sessionId={sessionId}
            stage={activeTab}
            stageStatus={activeStatuses[activeTab]}
            artifactData={artifacts[activeTab]}
          />
        </AnimatePresence>
      </div>
    </div>
  )
}

function DecisionLogPanel({ sessionId, isComplete }: { sessionId: string, isComplete: boolean }) {
  const [entries, setEntries] = useState<any[]>([]);

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    const fetchLog = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/sessions/${sessionId}/decision-log`);
        if (res.ok) {
          const json = await res.json();
          setEntries(Array.isArray(json) ? json : (json.entries || []));
        }
      } catch (e) { }

      if (!isComplete) {
        timeout = setTimeout(fetchLog, 4000);
      }
    };
    fetchLog();
    return () => clearTimeout(timeout);
  }, [sessionId, isComplete]);

  return (
    <div className="bg-base border border-border-subtle shadow-none flex flex-col h-full max-h-[400px]">
      <div className="bg-panel border-b border-border-subtle p-4 flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-widest text-text-main font-bold">System Log</span>
        {!isComplete && <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse shadow-[0_0_8px_rgba(232,163,61,0.5)]"></span>}
      </div>
      <div className="overflow-y-auto p-4 space-y-3 flex-1 font-mono">
        {entries.length === 0 ? (
          <div className="text-text-muted text-xs italic py-4">Awaiting operational records...</div>
        ) : (
          entries.map((e, i) => (
            <motion.div
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              key={i}
              className="flex flex-col gap-1 border-b border-border-subtle/30 pb-2.5 last:border-0 last:pb-0 text-xs"
            >
              <div className="flex items-center gap-3">
                <span className="text-text-muted text-[11px]">[{new Date(e.created_at).toLocaleTimeString()}]</span>
                <span className={`${AGENT_COLORS[e.stage_name] ? AGENT_COLORS[e.stage_name].replace('bg-', 'text-') : 'text-accent'} text-[11px] uppercase tracking-widest font-bold`}>{e.stage_name}</span>
              </div>
              <span className="text-text-main text-[13px] leading-relaxed">{e.reasoning}</span>
            </motion.div>
          ))
        )}
      </div>
    </div>
  )
}

function ExportActions({ sessionId }: { sessionId: string }) {
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [loadingNotion, setLoadingNotion] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [notionUrl, setNotionUrl] = useState<string | null>(null);

  const handleExport = async (target: "pdf" | "notion") => {
    const isPdf = target === 'pdf';
    if (isPdf) {
      setLoadingPdf(true);
    } else {
      const token = localStorage.getItem("notion_token");
      const dbId = localStorage.getItem("notion_database_id");
      if (!token || !dbId) {
        alert("Please connect your Notion account in the sidebar before exporting.");
        return;
      }
      setLoadingNotion(true);
    }

    try {
      const body: any = { target };
      if (target === 'notion') {
        body.notion_token = localStorage.getItem("notion_token");
        body.notion_database_id = localStorage.getItem("notion_database_id");
      }

      const res = await fetch(`${BACKEND_URL}/sessions/${sessionId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        const data = await res.json();
        if (isPdf) {
          const url = data.download_url.startsWith('http') ? data.download_url : `${BACKEND_URL}${data.download_url}`;
          setPdfUrl(url);
        } else {
          setNotionUrl(data.notion_url);
        }
      }
    } catch (e) { }
    finally {
      isPdf ? setLoadingPdf(false) : setLoadingNotion(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col sm:flex-row gap-3 w-full pt-6 md:pt-8 border-t border-border-subtle mt-8"
    >
      <div className="flex-1 flex gap-0 border border-border-subtle overflow-hidden">
        <button
          onClick={() => handleExport('pdf')}
          disabled={loadingPdf}
          className="flex-1 bg-panel text-text-main font-mono text-[10px] font-bold uppercase tracking-widest py-4 px-4 hover:bg-base transition-colors"
        >
          {loadingPdf ? 'GENERATING...' : pdfUrl ? 'EXPORTED ✓' : 'EXPORT DATA TO PDF'}
        </button>
        {pdfUrl && <a href={pdfUrl} target="_blank" rel="noreferrer" className="flex items-center justify-center px-6 bg-accent text-base hover:bg-opacity-90 font-mono text-[10px] font-bold transition-opacity">VIEW</a>}
      </div>

      <div className="flex-1 flex gap-0 border border-border-subtle overflow-hidden">
        <button
          onClick={() => handleExport('notion')}
          disabled={loadingNotion}
          className="flex-1 bg-panel text-text-main font-mono text-[10px] font-bold uppercase tracking-widest py-4 px-4 hover:bg-base transition-colors"
        >
          {loadingNotion ? 'PUSHING...' : notionUrl ? 'SYNCED ✓' : 'PUSH TO NOTION HUB'}
        </button>
        {notionUrl && <a href={notionUrl} target="_blank" rel="noreferrer" className="flex items-center justify-center px-6 bg-accent text-base hover:bg-opacity-90 font-mono text-[10px] font-bold transition-opacity">VIEW</a>}
      </div>
    </motion.div>
  )
}

// -------- Main Page -------- //

export default function SessionDashboard({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);

  const [sidebarOpen, setSidebarOpen] = useState(true);

  useEffect(() => {
    if (!id) return;
    try {
      const mySessions = JSON.parse(localStorage.getItem("my_sessions") || "[]");
      if (!mySessions.includes(id)) {
        mySessions.push(id);
        localStorage.setItem("my_sessions", JSON.stringify(mySessions));
      }
    } catch (e) {}
  }, [id]);

  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    let isMounted = true;
    let currentStatus = "running";

    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/sessions/${id}`);
        if (!res.ok) throw new Error("Connection failed");
        const json = await res.json();
        if (json.gate && !json.gate.result) {
          json.gate = { triggered: true, resolved: false, result: json.gate };
        }

        if (!isMounted) return;
        setData((prevData: any) => {
          if (json.status === "running" && prevData?.status === "awaiting_gate") {
            return { ...json, gate: prevData.gate };
          }
          return json;
        });
        setError(null);
        setIsRetrying(false);
        currentStatus = json.status;
      } catch (err: any) {
        if (!isMounted) return;
        setIsRetrying(true);
      }

      if (isMounted && currentStatus !== "complete" && currentStatus !== "failed") {
        timeoutId = setTimeout(poll, 1500);
      }
    };

    poll();

    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
    };
  }, [id]);

  if (error && !data) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-status-failed font-mono text-[12px] tracking-widest px-6 text-center">
        Error establishing connection: {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-[1500px] mx-auto p-6 md:p-10 space-y-8 min-h-screen font-mono">
        <div className="h-24 bg-panel border border-border-subtle animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="h-96 bg-panel border border-border-subtle animate-pulse" />
          <div className="h-96 bg-panel border border-border-subtle animate-pulse md:col-span-2" />
        </div>
      </div>
    );
  }

  const activeStatuses = Object.fromEntries(Object.entries(data.stages || {}).map(([k, v]: any) => [k, v.status]));
  const completedCount = STAGES.filter(s => activeStatuses[s] === 'complete').length;
  const progressPercent = (completedCount / STAGES.length) * 100;
  const isAnyStageRunning = STAGES.some(s => activeStatuses[s] === 'running');

  const isBlurred = data.gate?.triggered && !data.gate.resolved;
  const blurClasses = isBlurred ? "blur-sm opacity-40 pointer-events-none transition-all duration-300" : "transition-all duration-300";

  return (
    <div className="flex min-h-screen font-mono bg-base text-text-main">
      <Sidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />
      <div className={`flex-1 min-w-0 transition-all duration-300 ${sidebarOpen ? 'ml-72' : 'ml-0'}`}>
        <div className="max-w-[1500px] mx-auto p-6 md:p-10 space-y-8">
      {/* Global Progress Bar */}
      <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-border-subtle overflow-hidden">
        <motion.div
          className="h-full bg-accent shadow-[0_0_8px_rgba(232,163,61,0.5)]"
          initial={{ width: 0 }}
          animate={{
            width: `${progressPercent}%`,
            ...(isAnyStageRunning ? { opacity: [0.6, 1, 0.6] } : { opacity: 1 })
          }}
          transition={{
            width: { duration: 0.5, ease: "easeOut" },
            ...(isAnyStageRunning ? { opacity: { repeat: Infinity, duration: 1.5, ease: "easeInOut" } } : { duration: 0.2 })
          }}
        />
      </div>

      {isRetrying && (
        <div className="fixed top-0 left-0 right-0 bg-status-failed text-base text-[10px] uppercase font-bold py-2 px-4 tracking-widest z-50 text-center shadow-lg border-b border-status-failed">
          Connection Interrupted. Attempting to restore telemetry...
        </div>
      )}

      {/* Header Panel */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="flex flex-col md:flex-row justify-between items-start md:items-end border-b border-border-subtle pb-6 gap-6 pt-16"
      >
        <div className="max-w-2xl">
          <h1 className="text-3xl lg:text-4xl text-text-main font-bold tracking-tight mb-2 uppercase">{data.startup_name}</h1>
          <p className="text-text-muted text-[13px] leading-relaxed">{data.idea}</p>
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <div className="flex items-center gap-4">
            <CustomThemeToggler />
          </div>
          <div className="text-[11px] text-text-muted uppercase tracking-widest font-bold mt-2">Session ID</div>
          <div className="text-[11px] text-text-main bg-panel border-border-subtle border px-3 py-1">{data.session_id}</div>
          <div className={`mt-2 px-4 py-1.5 text-[9px] font-bold uppercase tracking-widest border ${data.status === 'complete' ? 'border-status-complete text-status-complete bg-status-complete/10' :
            data.status === 'failed' ? 'border-status-failed text-status-failed bg-status-failed/10' :
              'border-accent text-accent bg-accent/5 animate-pulse shadow-[0_0_10px_rgba(232,163,61,0.15)]'
            }`}>
            {data.status === 'awaiting_gate' ? 'PAUSED. PENDING REVIEW' : data.status}
          </div>
        </div>
      </motion.div>

      <div className="flex flex-col gap-8 items-stretch pt-4">
        {/* Review Gate Section */}
        <AnimatePresence>
          {isBlurred && (
            <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}>
              <GateCard id={id} gate={data.gate} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Top Section = Flow Diagram */}
        <div className={blurClasses}>
          <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <PipelineView stages={data.stages || {}} />
          </motion.div>
        </div>

        {/* Middle Section = Content Inspector / Agents Output */}
        <div className={blurClasses}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <TabsViewer sessionId={id} activeStatuses={activeStatuses} artifacts={data.artifacts || {}} />

            <AnimatePresence>
              {(data.status === 'complete' || data.status === 'failed') && (
                <ExportActions sessionId={id} />
              )}
            </AnimatePresence>
          </motion.div>
        </div>

        {/* Bottom Section = System Log */}
        <div className={blurClasses}>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
            <DecisionLogPanel sessionId={id} isComplete={data.status === 'complete' || data.status === 'failed'} />
          </motion.div>
        </div>
      </div>
      </div>
      </div>
    </div>
  )
}