import React from "react";
import type { PipelineStage, SimStep } from "../types";
import { CheckCircle, Loader2, Activity } from "lucide-react";
import { motion } from "framer-motion";

interface PipelineVisualizerProps {
  stages: PipelineStage[];
  activeStep: SimStep;
}

export const PipelineVisualizer: React.FC<PipelineVisualizerProps> = ({ stages, activeStep }) => {
  const isPipelineActive = activeStep !== "NORMAL" && activeStep !== "FAULT_RECEIVED";

  return (
    <div className="glow-card p-5 relative overflow-hidden flex flex-col h-[280px]">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-cyber-green animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Backend Pipeline Engine
          </h2>
        </div>
        <span className="text-[10px] font-mono text-cyber-text-muted">
          Execution Trace
        </span>
      </div>

      <div className="flex-1 flex flex-col justify-between relative py-1">
        {/* Background connector line */}
        <div className="absolute left-[15px] top-6 bottom-6 w-0.5 bg-zinc-800 -z-10" />
        
        {isPipelineActive && (
          <motion.div 
            initial={{ height: 0 }}
            animate={{ height: "100%" }}
            transition={{ duration: 2 }}
            className="absolute left-[15px] top-6 bottom-6 w-0.5 bg-gradient-to-b from-cyber-green via-cyber-blue to-cyber-cyan -z-10"
          />
        )}

        {stages.map((stage, idx) => {
          // Adjust status depending on the step
          let currentStatus = stage.status;
          let showTime = stage.durationMs;

          if (isPipelineActive) {
            if (activeStep === "PIPELINE_PROCESSING") {
              // Standard pacing managed inside hook, otherwise fallback
            } else {
              // For later stages, everything in pipeline completed
              currentStatus = "completed";
              if (stage.id === "kafka") showTime = 150;
              if (stage.id === "consumer") showTime = 120;
              if (stage.id === "timestamp") showTime = 10;
              if (stage.id === "graph") showTime = 45;
            }
          } else {
            currentStatus = "idle";
          }

          const isCompleted = currentStatus === "completed";
          const isRunning = currentStatus === "running" || (activeStep === "PIPELINE_PROCESSING" && !isCompleted);

          return (
            <div key={stage.id} className="flex items-center justify-between pl-1">
              <div className="flex items-center gap-4">
                {/* Node Status Dot */}
                <div className="relative">
                  <div
                    className={`h-7 w-7 rounded-full flex items-center justify-center border transition-all duration-300 ${
                      isCompleted
                        ? "bg-cyber-green/10 border-cyber-green text-cyber-green shadow-glow-green"
                        : isRunning
                        ? "bg-cyber-blue/10 border-cyber-blue text-cyber-blue animate-pulse"
                        : "bg-zinc-950 border-zinc-800 text-zinc-600"
                    }`}
                  >
                    {isCompleted ? (
                      <CheckCircle className="h-4 w-4" />
                    ) : isRunning ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <span className="text-[10px] font-mono font-bold">{idx + 1}</span>
                    )}
                  </div>
                </div>

                {/* Stage Info */}
                <div>
                  <h3
                    className={`text-xs font-mono font-bold tracking-wide transition-colors ${
                      isCompleted
                        ? "text-white"
                        : isRunning
                        ? "text-cyber-blue"
                        : "text-zinc-500"
                    }`}
                  >
                    {stage.name}
                  </h3>
                  <p className="text-[9px] text-cyber-text-muted font-mono leading-none mt-1">
                    {stage.id === "kafka" && "Topic Ingestion & Queue Verification"}
                    {stage.id === "consumer" && "Telemetry Event Deserializer"}
                    {stage.id === "timestamp" && "Enrichment & Temporal Indexing"}
                    {stage.id === "graph" && "LangGraph Topology Engine Trigger"}
                  </p>
                </div>
              </div>

              {/* Execution time output */}
              <div className="text-right font-mono text-[10px] pr-2">
                {isCompleted && showTime ? (
                  <span className="text-cyber-green bg-cyber-green/5 px-2 py-0.5 border border-cyber-green/10 rounded">
                    {showTime}ms
                  </span>
                ) : isRunning ? (
                  <span className="text-cyber-blue animate-pulse uppercase text-[9px] font-bold">
                    Running
                  </span>
                ) : (
                  <span className="text-zinc-700">--</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
