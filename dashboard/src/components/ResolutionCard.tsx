import React from "react";
import { CheckCircle2, ShieldAlert, Clock, Sparkles } from "lucide-react";

interface ResolutionCardProps {
  summary: {
    alarm: string;
    asset: string;
    rootCause: string;
    actionTaken: string;
    executionTime: number;
    slaRemaining: number;
    result: string;
  } | null;
}

export const ResolutionCard: React.FC<ResolutionCardProps> = ({ summary }) => {
  if (!summary) {
    return (
      <div className="glow-card p-5 h-[230px] flex flex-col justify-center items-center text-zinc-600 font-mono text-xs">
        <Sparkles className="h-7 w-7 opacity-20 mb-1.5" />
        <span>Awaiting remediation cycle completion...</span>
      </div>
    );
  }

  const isVetoed = summary.result.includes("VETO");

  return (
    <div className={`glow-card p-5 h-[230px] flex flex-col justify-between transition-all duration-300 ${
      isVetoed 
        ? "border-cyber-red/80 bg-cyber-red/5 shadow-glow-red" 
        : "border-cyber-green/50 bg-cyber-green/5 shadow-glow-green"
    }`}>
      <div className="flex items-center justify-between border-b border-cyber-border pb-3">
        <div className="flex items-center gap-2">
          {isVetoed ? (
            <ShieldAlert className="h-4.5 w-4.5 text-cyber-red animate-bounce" />
          ) : (
            <CheckCircle2 className="h-4.5 w-4.5 text-cyber-green animate-pulse" />
          )}
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Remediation Resolution
          </h2>
        </div>
        <span className={`text-[10px] font-mono font-black uppercase px-2 py-0.5 rounded border ${
          isVetoed 
            ? "bg-cyber-red/10 border-cyber-red/30 text-cyber-red" 
            : "bg-cyber-green/10 border-cyber-green/30 text-cyber-green"
        }`}>
          {isVetoed ? "VETOED" : "SUCCESS"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-[11px] py-2">
        <div className="flex flex-col">
          <span className="text-cyber-text-muted text-[9px] uppercase">ALARM CODE</span>
          <span className="text-white font-bold truncate">{summary.alarm}</span>
        </div>

        <div className="flex flex-col">
          <span className="text-cyber-text-muted text-[9px] uppercase">AFFECTED ASSET</span>
          <span className="text-white font-bold">{summary.asset}</span>
        </div>

        <div className="flex flex-col col-span-2">
          <span className="text-cyber-text-muted text-[9px] uppercase">ROOT CAUSE ANALYSIS</span>
          <span className="text-zinc-300 font-semibold">{summary.rootCause}</span>
        </div>

        <div className="flex flex-col col-span-2">
          <span className="text-cyber-text-muted text-[9px] uppercase">ACTION REMEDIATION</span>
          <span className="text-zinc-300 font-semibold truncate" title={summary.actionTaken}>
            {summary.actionTaken}
          </span>
        </div>
      </div>

      {/* Latency and SLA stats */}
      <div className="flex items-center justify-between bg-zinc-950/80 border border-cyber-border/40 p-2.5 rounded-lg">
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-zinc-300">
          <Clock className="h-3.5 w-3.5 text-cyber-blue" />
          <span>EXEC TIME: <strong className="text-white">{summary.executionTime}s</strong></span>
        </div>

        <div className="font-mono text-[10px] text-zinc-300">
          SLA REMAINING:{" "}
          <strong className={summary.slaRemaining > 15 ? "text-cyber-green" : "text-cyber-amber"}>
            {summary.slaRemaining.toFixed(1)}s
          </strong>
        </div>
      </div>
    </div>
  );
};
