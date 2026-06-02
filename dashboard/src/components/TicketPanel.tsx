import React from "react";
import { FileText, Send, CheckCircle2, ShieldAlert } from "lucide-react";
import type { SimStep } from "../types";

interface TicketPanelProps {
  activeStep: SimStep;
  ticketData: {
    id: string;
    asset: string;
    alarm: string;
    resolution: string;
    status: "idle" | "posting" | "delivered" | "blocked";
  };
}

export const TicketPanel: React.FC<TicketPanelProps> = ({ activeStep, ticketData }) => {
  const isPending = 
    activeStep === "NORMAL" || 
    activeStep === "FAULT_RECEIVED" || 
    activeStep === "PIPELINE_PROCESSING" || 
    activeStep === "RAG_RETRIEVAL" || 
    activeStep === "AI_STRATEGY" || 
    activeStep === "SAFETY_CHECK" ||
    (activeStep === "SSH_EXECUTION" && ticketData.status === "idle");

  const isDelivered = ticketData.status === "delivered";
  const isBlocked = ticketData.status === "blocked" || (activeStep === "RESOLVED" && ticketData.resolution.includes("Safety veto"));

  return (
    <div className="glow-card p-5 h-[230px] flex flex-col">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4.5 w-4.5 text-cyber-blue" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            TMF621 Trouble Ticket
          </h2>
        </div>
        {!isPending && (
          <span className={`text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded border ${
            isDelivered 
              ? "bg-cyber-green/10 border-cyber-green/30 text-cyber-green" 
              : isBlocked 
              ? "bg-cyber-red/10 border-cyber-red/30 text-cyber-red"
              : "bg-cyber-blue/10 border-cyber-blue/30 text-cyber-blue animate-pulse"
          }`}>
            {isDelivered ? "TMF-621 Generated" : isBlocked ? "BLOCKED" : "POSTing..."}
          </span>
        )}
      </div>

      <div className="flex-1 flex flex-col justify-center">
        {isPending ? (
          <div className="text-center py-6 text-zinc-600 font-mono text-xs flex flex-col items-center justify-center gap-1.5">
            <FileText className="h-7 w-7 opacity-20" />
            <span>Awaiting incident resolution for ticket registration...</span>
          </div>
        ) : (
          <div className="space-y-2 font-mono text-[11px]">
            <div className="grid grid-cols-3 border-b border-zinc-900 pb-1">
              <span className="text-cyber-text-muted">TICKET ID:</span>
              <span className="col-span-2 text-white font-bold">{ticketData.id}</span>
            </div>
            
            <div className="grid grid-cols-3 border-b border-zinc-900 pb-1">
              <span className="text-cyber-text-muted">ASSET:</span>
              <span className="col-span-2 text-white">{ticketData.asset}</span>
            </div>

            <div className="grid grid-cols-3 border-b border-zinc-900 pb-1">
              <span className="text-cyber-text-muted">ALARM:</span>
              <span className="col-span-2 text-cyber-red font-semibold">{ticketData.alarm}</span>
            </div>

            <div className="grid grid-cols-3 border-b border-zinc-900 pb-1">
              <span className="text-cyber-text-muted">RESOLUTION:</span>
              <span className="col-span-2 text-white truncate max-w-[200px]" title={ticketData.resolution}>
                {ticketData.resolution}
              </span>
            </div>

            {/* ServiceNow Sync Status */}
            <div className="pt-2 flex items-center justify-between">
              <span className="text-[10px] text-cyber-text-muted">SERVICENOW STATUS:</span>
              <div className="flex items-center gap-1.5">
                {isDelivered ? (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-cyber-green" />
                    <span className="text-cyber-green font-bold uppercase text-[10px]">
                      Delivered (HTTP 201)
                    </span>
                  </>
                ) : isBlocked ? (
                  <>
                    <ShieldAlert className="h-4 w-4 text-cyber-red" />
                    <span className="text-cyber-red font-bold uppercase text-[10px]">
                      BLOCKED / CLOSED
                    </span>
                  </>
                ) : (
                  <>
                    <Send className="h-3.5 w-3.5 text-cyber-blue animate-bounce" />
                    <span className="text-cyber-blue animate-pulse uppercase text-[10px]">
                      POSTing to ServiceNow...
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
