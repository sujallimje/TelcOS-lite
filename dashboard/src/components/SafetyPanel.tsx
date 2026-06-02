import React from "react";
import { ShieldCheck, ShieldAlert, Check, X, Shield, AlertOctagon } from "lucide-react";
import type { SimStep } from "../types";

interface SafetyPanelProps {
  activeStep: SimStep;
  safetyData: {
    checks: { name: string; passed: boolean | null }[];
    verdict: "PENDING" | "SAFE" | "BLOCKED";
    status: "idle" | "evaluating" | "completed";
  };
}

export const SafetyPanel: React.FC<SafetyPanelProps> = ({ activeStep, safetyData }) => {
  const isPending = 
    activeStep === "NORMAL" || 
    activeStep === "FAULT_RECEIVED" || 
    activeStep === "PIPELINE_PROCESSING" || 
    activeStep === "RAG_RETRIEVAL" || 
    activeStep === "AI_STRATEGY";

  const isEvaluating = activeStep === "SAFETY_CHECK" && safetyData.status === "evaluating";
  const isCompleted = !isPending && !isEvaluating;

  const isVetoed = safetyData.verdict === "BLOCKED";

  return (
    <div className={`glow-card p-5 h-[230px] flex flex-col transition-all duration-300 ${
      isCompleted && isVetoed 
        ? "border-cyber-red/80 bg-cyber-red/5 shadow-glow-red animate-siren" 
        : isCompleted 
        ? "border-cyber-green/50 bg-cyber-green/5 shadow-glow-green" 
        : ""
    }`}>
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-3">
        <div className="flex items-center gap-2">
          {isCompleted && isVetoed ? (
            <ShieldAlert className="h-4.5 w-4.5 text-cyber-red animate-bounce" />
          ) : (
            <Shield className="h-4.5 w-4.5 text-cyber-green" />
          )}
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Deterministic Safety Gate
          </h2>
        </div>
        
        {isCompleted && (
          <span className={`text-[10px] font-mono font-black uppercase px-2 py-0.5 rounded border ${
            isVetoed 
              ? "bg-cyber-red/25 border-cyber-red text-cyber-red" 
              : "bg-cyber-green/25 border-cyber-green text-cyber-green"
          }`}>
            {isVetoed ? "VETO TRIGGERED" : "SAFE"}
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col justify-center">
        {isPending ? (
          <div className="text-center py-6 text-zinc-600 font-mono text-xs flex flex-col items-center justify-center gap-1.5">
            <Shield className="h-7 w-7 opacity-20" />
            <span>Awaiting proposed mitigation commands...</span>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Checklist */}
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              {safetyData.checks.map((check, idx) => {
                const passed = check.passed;
                
                let checkIcon = <span className="h-3 w-3 rounded-full bg-zinc-800 animate-pulse block" />;
                let textStyle = "text-zinc-500";

                if (passed === true) {
                  checkIcon = <Check className="h-4 w-4 text-cyber-green" />;
                  textStyle = "text-zinc-300";
                } else if (passed === false) {
                  checkIcon = <X className="h-4 w-4 text-cyber-red animate-bounce" />;
                  textStyle = "text-cyber-red font-bold";
                }

                return (
                  <div key={idx} className="flex items-center gap-2 border border-cyber-border/40 p-1.5 rounded bg-zinc-950/60">
                    <div className="flex-shrink-0">{checkIcon}</div>
                    <span className={`text-[9px] truncate uppercase leading-none ${textStyle}`}>{check.name}</span>
                  </div>
                );
              })}
            </div>

            {/* Verdict Display */}
            {isCompleted && (
              <div className="mt-3 flex items-center justify-between p-2 rounded-md bg-zinc-950/80 border border-cyber-border/40">
                <div className="flex items-center gap-2">
                  {isVetoed ? (
                    <AlertOctagon className="h-5 w-5 text-cyber-red" />
                  ) : (
                    <ShieldCheck className="h-5 w-5 text-cyber-green" />
                  )}
                  <div>
                    <div className="text-[8px] font-mono text-cyber-text-muted leading-none">VERDICT RESOLUTION</div>
                    <div className={`text-xs font-mono font-bold leading-none mt-1 ${isVetoed ? "text-cyber-red" : "text-cyber-green"}`}>
                      {isVetoed ? "SAFETY ENGINE BLOCKED EXECUTION" : "ALL SECURITY POLICIES COMPLIANT"}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
