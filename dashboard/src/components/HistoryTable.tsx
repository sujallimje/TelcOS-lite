import React from "react";
import type { IncidentRecord } from "../types";
import { ShieldCheck, ShieldAlert, FileText, Clock } from "lucide-react";

interface HistoryTableProps {
  incidents: IncidentRecord[];
}

export const HistoryTable: React.FC<HistoryTableProps> = ({ incidents }) => {
  return (
    <div className="glow-card p-5 flex flex-col h-[400px]">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3.5 mb-4">
        <div className="flex items-center gap-2">
          <FileText className="h-4.5 w-4.5 text-cyber-cyan" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Remediation Incident Catalog
          </h2>
        </div>
        <span className="text-[10px] font-mono text-cyber-text-muted">
          audit log
        </span>
      </div>

      <div className="flex-1 overflow-auto pr-1">
        <table className="w-full text-left font-mono text-xs border-collapse">
          <thead>
            <tr className="border-b border-zinc-800 text-cyber-text-muted uppercase text-[10px] tracking-wider bg-zinc-950/40">
              <th className="py-2.5 px-3">Timestamp</th>
              <th className="py-2.5 px-3">Ticket ID</th>
              <th className="py-2.5 px-3">Asset</th>
              <th className="py-2.5 px-3">Alarm Name</th>
              <th className="py-2.5 px-3">Remediation Action</th>
              <th className="py-2.5 px-3 text-center">Safety Verdict</th>
              <th className="py-2.5 px-3 text-right">Execution</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-900">
            {incidents.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-10 text-center text-zinc-600">
                  No historical incidents cataloged yet.
                </td>
              </tr>
            ) : (
              incidents.map((inc) => {
                const isBlocked = inc.verdict === "BLOCKED";
                
                return (
                  <tr key={inc.id} className="hover:bg-zinc-900/40 transition">
                    <td className="py-3 px-3 text-[10px] text-zinc-500 whitespace-nowrap">
                      {new Date(inc.timestamp).toLocaleString()}
                    </td>
                    
                    <td className="py-3 px-3 text-white font-bold whitespace-nowrap">
                      {inc.ticketId}
                    </td>

                    <td className="py-3 px-3 text-cyber-cyan font-bold whitespace-nowrap">
                      {inc.asset}
                    </td>

                    <td className="py-3 px-3 text-cyber-red font-semibold whitespace-nowrap">
                      {inc.alarm}
                    </td>

                    <td className="py-3 px-3 text-zinc-300 max-w-[200px] truncate" title={inc.actionTaken}>
                      {inc.actionTaken}
                    </td>

                    <td className="py-3 px-3 text-center">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full border text-[10px] font-bold ${
                        isBlocked
                          ? "bg-cyber-red/10 border-cyber-red/20 text-cyber-red"
                          : "bg-cyber-green/10 border-cyber-green/20 text-cyber-green"
                      }`}>
                        {isBlocked ? (
                          <>
                            <ShieldAlert className="h-3 w-3" />
                            BLOCKED
                          </>
                        ) : (
                          <>
                            <ShieldCheck className="h-3 w-3" />
                            SAFE
                          </>
                        )}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-right text-zinc-300 font-bold whitespace-nowrap">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3 w-3 opacity-60" />
                        {inc.executionTime.toFixed(1)}s
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
