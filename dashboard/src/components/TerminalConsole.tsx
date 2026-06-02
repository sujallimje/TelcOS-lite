import React, { useRef, useEffect } from "react";
import { Terminal, ShieldAlert } from "lucide-react";
import type { SimStep } from "../types";

interface TerminalConsoleProps {
  activeStep: SimStep;
  terminalLines: string[];
  isVetoed: boolean;
}

export const TerminalConsole: React.FC<TerminalConsoleProps> = ({ activeStep, terminalLines, isVetoed }) => {
  const endRef = useRef<HTMLDivElement>(null);
  
  const isActive = activeStep === "SSH_EXECUTION";
  const isAfter = activeStep === "TICKET_CREATION" || activeStep === "RESOLVED";

  useEffect(() => {
    if (endRef.current) {
      endRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [terminalLines]);

  return (
    <div className="glow-card p-5 h-[230px] flex flex-col bg-zinc-950/95 border-zinc-800">
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-3">
        <div className="flex items-center gap-2">
          <Terminal className="h-4.5 w-4.5 text-cyber-cyan" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Southbound Execution (SSH)
          </h2>
        </div>
        <span className="text-[10px] font-mono text-zinc-500">
          admin@10.0.89.2
        </span>
      </div>

      <div className="flex-1 overflow-y-auto pr-1 font-mono text-xs text-zinc-300 space-y-1 scrollbar-thin">
        {isVetoed ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-cyber-red/80 gap-2 font-mono">
            <ShieldAlert className="h-8 w-8 animate-pulse text-cyber-red" />
            <div className="text-xs uppercase font-extrabold tracking-wider">
              SSH Session Suspended
            </div>
            <div className="text-[10px] text-zinc-500 max-w-[220px]">
              Safety engine vetoed commands. Southbound execution bypassed to preserve network integrity.
            </div>
          </div>
        ) : !isActive && !isAfter ? (
          <div className="text-zinc-700 flex flex-col items-center justify-center h-full gap-1 select-none">
            <Terminal className="h-6 w-6 opacity-30" />
            <span>Session Idle. Awaiting execution state...</span>
          </div>
        ) : (
          <>
            {terminalLines.map((line, idx) => {
              let color = "text-zinc-300";
              if (line.includes("SUCCESS")) {
                color = "text-cyber-green font-bold";
              } else if (line.includes("Executing")) {
                color = "text-cyber-cyan";
              } else if (line.includes("Connecting") || line.includes("Closing")) {
                color = "text-zinc-500";
              } else if (line.includes("bash-5.1")) {
                color = "text-white";
              }

              return (
                <div key={idx} className={color}>
                  {line}
                </div>
              );
            })}
            
            {isActive && (
              <div className="inline-block h-3.5 w-1.5 bg-cyber-green animate-pulse" />
            )}
            
            <div ref={endRef} />
          </>
        )}
      </div>
    </div>
  );
};
