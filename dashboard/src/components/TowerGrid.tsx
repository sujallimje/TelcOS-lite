import React from "react";
import type { Tower as TowerType } from "../types";
import { Wifi, Thermometer, Cpu, Radio } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface TowerGridProps {
  towers: TowerType[];
}

export const TowerGrid: React.FC<TowerGridProps> = ({ towers }) => {
  return (
    <div className="glow-card p-5 relative overflow-hidden">
      {/* Grid background overlay for cyber aesthetics */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1f293710_1px,transparent_1px),linear-gradient(to_bottom,#1f293710_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] pointer-events-none" />

      <div className="flex items-center justify-between border-b border-cyber-border pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Radio className="h-4.5 w-4.5 text-cyber-green animate-pulse" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-white">
            Active Network Topology
          </h2>
        </div>
        <span className="text-[10px] font-mono bg-cyber-green/10 text-cyber-green px-2 py-0.5 rounded border border-cyber-green/20">
          15 Nodes Monitored
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-3">
        <AnimatePresence>
          {towers.map((tower) => {
            const isCritical = tower.status === "critical";
            const isRecovering = tower.status === "recovering";
            
            let statusColor = "border-cyber-green/30 bg-cyber-green/5 text-cyber-green shadow-glow-green";
            if (isCritical) {
              statusColor = "border-cyber-red/80 bg-cyber-red/10 text-cyber-red shadow-glow-red animate-pulse-fast";
            } else if (isRecovering) {
              statusColor = "border-cyber-amber/60 bg-cyber-amber/5 text-cyber-amber shadow-glow-blue";
            }

            return (
              <motion.div
                key={tower.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3 }}
                className={`glow-card flex flex-col p-3 rounded-lg border relative transition-all duration-300 ${statusColor}`}
              >
                {/* Ping Pulse Animation */}
                {!isCritical && (
                  <span className="absolute top-2 right-2 flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyber-green opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-cyber-green"></span>
                  </span>
                )}
                {isCritical && (
                  <span className="absolute top-2 right-2 flex h-3.5 w-3.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyber-red opacity-80"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-cyber-red"></span>
                  </span>
                )}

                {/* Card Contents */}
                <div className="flex items-center gap-1.5 mb-2">
                  <Wifi className="h-4 w-4" />
                  <span className="font-mono text-xs font-bold text-white">
                    {tower.id}
                  </span>
                </div>

                <div className="space-y-1.5 text-[10px] font-mono mt-auto">
                  <div className="flex justify-between">
                    <span className="text-cyber-text-muted">STATUS:</span>
                    <span className={`font-bold ${isCritical ? "text-cyber-red" : isRecovering ? "text-cyber-amber" : "text-cyber-green"}`}>
                      {tower.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="flex justify-between items-center">
                    <span className="text-cyber-text-muted flex items-center gap-0.5"><Cpu className="h-3 w-3" /> CPU:</span>
                    <span className="text-white">{tower.cpu}%</span>
                  </div>

                  <div className="flex justify-between items-center">
                    <span className="text-cyber-text-muted flex items-center gap-0.5"><Thermometer className="h-3 w-3" /> TEMP:</span>
                    <span className={`font-bold ${tower.temperature > 80 ? "text-cyber-red" : "text-white"}`}>
                      {tower.temperature}°C
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-cyber-text-muted">HEALTH:</span>
                    <span className="text-white">{tower.networkHealth}%</span>
                  </div>
                </div>

                {/* Small indicator bar */}
                <div className="w-full bg-zinc-800 h-1.5 rounded-full mt-2.5 overflow-hidden">
                  <div
                    className={`h-full transition-all duration-500 ${
                      isCritical
                        ? "bg-cyber-red"
                        : isRecovering
                        ? "bg-cyber-amber animate-pulse"
                        : "bg-cyber-green"
                    }`}
                    style={{ width: `${tower.networkHealth}%` }}
                  />
                </div>

                {/* Device IP */}
                <div className="text-[8px] font-mono text-cyber-text-muted text-right mt-1.5 opacity-50">
                  {tower.ip}
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
};
