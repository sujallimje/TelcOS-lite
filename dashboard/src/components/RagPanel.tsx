import React from "react";
import { Search, FileText, Loader2 } from "lucide-react";
import type { SimStep } from "../types";

interface RagPanelProps {
  activeStep: SimStep;
  ragData: {
    manualMatch: string;
    chunks: string[];
    similarityScore: number;
    status: "idle" | "loading" | "retrieved";
  };
}

export const RagPanel: React.FC<RagPanelProps> = ({ activeStep, ragData }) => {
  const isPending = activeStep === "NORMAL" || activeStep === "FAULT_RECEIVED" || activeStep === "PIPELINE_PROCESSING";
  const isLoading = activeStep === "RAG_RETRIEVAL" && ragData.status === "loading";
  const isLoaded = !isPending && !isLoading;

  return (
    <div className="glow-card p-5 h-[230px] flex flex-col">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-3">
        <div className="flex items-center gap-2">
          <Search className="h-4.5 w-4.5 text-cyber-blue animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            RAG Context Retrieval
          </h2>
        </div>
        
        {isLoaded && (
          <span className="text-[10px] font-mono bg-cyber-green/10 text-cyber-green px-2 py-0.5 border border-cyber-green/20 rounded font-bold">
            Sim Similarity: {(ragData.similarityScore * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col justify-center">
        {isPending ? (
          <div className="text-center py-6 text-zinc-600 font-mono text-xs flex flex-col items-center justify-center gap-1.5">
            <FileText className="h-7 w-7 opacity-20" />
            <span>Waiting for vector DB query...</span>
          </div>
        ) : isLoading ? (
          <div className="text-center py-6 text-cyber-blue font-mono text-xs flex flex-col items-center justify-center gap-2">
            <Loader2 className="h-7 w-7 animate-spin" />
            <span>Searching vector store index (ChromaDB)...</span>
          </div>
        ) : (
          <div className="space-y-3">
            {/* Document title */}
            <div className="bg-zinc-950 border border-cyber-border/40 p-2.5 rounded-lg flex items-center gap-2">
              <FileText className="h-4.5 w-4.5 text-cyber-blue flex-shrink-0" />
              <div>
                <div className="text-[9px] font-mono text-cyber-text-muted leading-none">MATCHED MANUAL</div>
                <div className="text-xs font-mono font-bold text-white mt-1 leading-none">
                  {ragData.manualMatch}
                </div>
              </div>
            </div>

            {/* Chunks */}
            <div className="space-y-1.5">
              <div className="text-[9px] font-mono text-cyber-text-muted">RETRIEVED KNOWLEDGE CHUNKS:</div>
              <div className="space-y-1">
                {ragData.chunks.map((chunk, idx) => (
                  <div key={idx} className="flex items-start gap-1.5 text-[11px] font-mono text-zinc-300">
                    <span className="text-cyber-blue select-none font-bold mt-0.5">▪</span>
                    <span className="leading-tight">{chunk}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
