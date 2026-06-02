import React from "react";
import type { EventLog } from "../types";
import { ListFilter, ShieldAlert } from "lucide-react";
import { motion } from "framer-motion";

interface IncidentHistoryLogProps {
  logs: EventLog[];
}

export const IncidentHistoryLog: React.FC<IncidentHistoryLogProps> = ({ logs }) => {
  return (
    <div className="glow-card p-5 h-[230px] flex flex-col">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-3">
        <div className="flex items-center gap-2">
          <ListFilter className="h-4 w-4 text-cyber-amber animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Active Incident Trace Log
          </h2>
        </div>
        <span className="text-[10px] font-mono text-cyber-amber bg-cyber-amber/10 px-2 py-0.5 border border-cyber-amber/20 rounded">
          Active Logs: {logs.length}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2 pr-2 font-mono text-[11px]">
        {logs.length === 0 ? (
          <div className="text-zinc-600 flex flex-col items-center justify-center h-full gap-1">
            <ShieldAlert className="h-6 w-6 opacity-30" />
            <span>No active incident remediation running.</span>
          </div>
        ) : (
          logs.map((log, index) => {
            let typeColor = "border-zinc-800 text-zinc-300";
            if (log.type === "error") {
              typeColor = "border-cyber-red/35 bg-cyber-red/5 text-cyber-red font-semibold";
            } else if (log.type === "success") {
              typeColor = "border-cyber-green/35 bg-cyber-green/5 text-cyber-green";
            } else if (log.type === "warning") {
              typeColor = "border-cyber-amber/35 bg-cyber-amber/5 text-cyber-amber";
            }

            return (
              <motion.div
                key={log.id}
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: index * 0.05 }}
                className={`p-2.5 rounded-lg border flex flex-col gap-1 ${typeColor}`}
              >
                <div className="flex justify-between items-center text-[10px]">
                  <span className="text-cyber-text-muted opacity-80 uppercase font-extrabold tracking-wide">
                    {log.source}
                  </span>
                  <span className="text-zinc-500 opacity-80">
                    {log.timestamp}
                  </span>
                </div>
                <div className="text-white text-xs leading-relaxed mt-0.5">
                  {log.message}
                </div>
              </motion.div>
            );
          })
        )}
      </div>
    </div>
  );
};
