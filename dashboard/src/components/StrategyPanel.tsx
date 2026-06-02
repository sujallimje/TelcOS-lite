import React from "react";
import { Cpu, Terminal, Compass } from "lucide-react";
import type { SimStep } from "../types";

interface StrategyPanelProps {
  activeStep: SimStep;
  strategyData: {
    commands: string[];
    confidence: number;
    inputs: string;
    outputs: string;
    status: "idle" | "generated";
  };
}

export const StrategyPanel: React.FC<StrategyPanelProps> = ({ activeStep, strategyData }) => {
  const isPending = 
    activeStep === "NORMAL" || 
    activeStep === "FAULT_RECEIVED" || 
    activeStep === "PIPELINE_PROCESSING" || 
    activeStep === "RAG_RETRIEVAL";
  
  const isLoaded = !isPending;

  return (
    <div className="glow-card p-5 h-[230px] flex flex-col">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-3">
        <div className="flex items-center gap-2">
          <Compass className="h-4.5 w-4.5 text-cyber-green animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            AI Strategy Generation
          </h2>
        </div>
        {isLoaded && (
          <span className="text-[10px] font-mono bg-cyber-green/10 text-cyber-green px-2 py-0.5 border border-cyber-green/20 rounded font-bold">
            LLM Conf: {(strategyData.confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col justify-center">
        {isPending ? (
          <div className="text-center py-6 text-zinc-600 font-mono text-xs flex flex-col items-center justify-center gap-1.5">
            <Cpu className="h-7 w-7 opacity-20" />
            <span>Awaiting RAG output for strategy construction...</span>
          </div>
        ) : (
          <div className="space-y-2.5">
            {/* Inputs summary */}
            <div className="text-[10px] font-mono text-cyber-text-muted">
              <span className="text-cyber-green font-bold mr-1">INPUTS:</span> 
              {strategyData.inputs}
            </div>

            {/* Commands list */}
            <div className="space-y-1.5">
              <span className="text-[9px] font-mono text-cyber-text-muted block">GENERATED SOUTHBOUND COMMANDS:</span>
              <div className="bg-zinc-950 border border-cyber-border/40 p-2.5 rounded-lg font-mono">
                {strategyData.commands.map((cmd, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-xs">
                    <Terminal className="h-3 w-3 text-cyber-green flex-shrink-0" />
                    <span className="text-white font-semibold">{cmd}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Operational Output Status */}
            <div className="flex items-center justify-between text-[10px] font-mono pt-1">
              <span className="text-cyber-text-muted">DECISION ENGINE STATE:</span>
              <span className="text-cyber-green font-extrabold uppercase animate-pulse">
                Strategy Generated
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
