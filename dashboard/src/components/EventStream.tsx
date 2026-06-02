import React, { useRef, useEffect } from "react";
import type { EventLog } from "../types";
import { Terminal, Database } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface EventStreamProps {
  logs: EventLog[];
}

export const EventStream: React.FC<EventStreamProps> = ({ logs }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Keep scroll at top since logs are unshifted, or auto scroll.
    // If log is sorted reverse chronological (new logs at top), scroll is unnecessary.
  }, [logs]);

  return (
    <div className="glow-card p-5 h-[230px] flex flex-col">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-3">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-cyber-blue" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Ingress Event Stream (Kafka)
          </h2>
        </div>
        <span className="text-[10px] font-mono text-cyber-text-muted">
          Auto-polling
        </span>
      </div>

      <div 
        ref={containerRef}
        className="flex-1 overflow-y-auto space-y-1.5 pr-2 font-mono text-[11px]"
      >
        <AnimatePresence initial={false}>
          {logs.length === 0 ? (
            <div className="text-cyber-text-muted flex items-center justify-center h-full gap-2">
              <Terminal className="h-4.5 w-4.5 opacity-40 animate-pulse" />
              <span>Monitoring Kafka topics for telemetry...</span>
            </div>
          ) : (
            logs.map((log) => {
              let textClass = "text-cyber-text-muted";
              let badgeBg = "bg-zinc-800 border-zinc-700";

              if (log.type === "error") {
                textClass = "text-cyber-red font-bold";
                badgeBg = "bg-cyber-red/10 border-cyber-red/30 text-cyber-red";
              } else if (log.type === "success") {
                textClass = "text-cyber-green";
                badgeBg = "bg-cyber-green/10 border-cyber-green/30 text-cyber-green";
              } else if (log.type === "warning") {
                textClass = "text-cyber-amber";
                badgeBg = "bg-cyber-amber/10 border-cyber-amber/30 text-cyber-amber";
              }

              return (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex items-start gap-2.5 py-1 border-b border-zinc-900/50"
                >
                  <span className="text-[10px] text-cyber-text-muted opacity-60 flex-shrink-0 select-none">
                    [{log.timestamp}]
                  </span>
                  
                  <span className={`text-[9px] px-1.5 py-0.2 rounded border font-bold uppercase flex-shrink-0 ${badgeBg}`}>
                    {log.source}
                  </span>

                  <span className={`flex-1 break-all ${textClass}`}>
                    {log.message}
                  </span>
                </motion.div>
              );
            })
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};
