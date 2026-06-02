import React from "react";
import { Play, Pause, RotateCcw, AlertTriangle, ShieldAlert, Cpu, Activity, ArrowRight } from "lucide-react";
import type { SimStep } from "../types";

interface HeaderProps {
  step: SimStep;
  isPlaying: boolean;
  setIsPlaying: (playing: boolean) => void;
  unsafeVetoEnabled: boolean;
  setUnsafeVetoEnabled: (enabled: boolean) => void;
  slaTime: number;
  triggerNextStep: () => void;
  resetSimulation: () => void;
  isLiveMode: boolean;
  setIsLiveMode: (live: boolean) => void;
  wsStatus: "connecting" | "open" | "closed" | "error";
}

export const Header: React.FC<HeaderProps> = ({
  step,
  isPlaying,
  setIsPlaying,
  unsafeVetoEnabled,
  setUnsafeVetoEnabled,
  slaTime,
  triggerNextStep,
  resetSimulation,
  isLiveMode,
  setIsLiveMode,
  wsStatus,
}) => {
  const isEmergency = step !== "NORMAL" && step !== "RESOLVED";

  return (
    <header className="border-b border-cyber-border bg-cyber-card/90 px-6 py-4 backdrop-blur-md sticky top-0 z-50">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        {/* Title / Branding */}
        <div className="flex items-center gap-3">
          <div className="bg-cyber-green/10 text-cyber-green p-2.5 rounded-lg border border-cyber-green/20 animate-led-blink">
            <Cpu className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-black font-sans uppercase tracking-wider text-white">
                TelcOS <span className="text-cyber-green">Lite</span>
              </h1>
              <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 font-mono text-cyber-text-muted">
                v1.0.4-Remedy
              </span>
            </div>
            <p className="text-xs text-cyber-text-muted font-mono tracking-widest uppercase">
              Autonomous Orchestration & Remediation
            </p>
          </div>
        </div>

        {/* SLA Status Card */}
        {isEmergency && (
          <div className="flex items-center gap-3 px-4 py-2 bg-cyber-red/10 border border-cyber-red/30 rounded-lg animate-siren">
            <AlertTriangle className="h-5 w-5 text-cyber-red animate-bounce" />
            <div className="font-mono text-sm">
              <div className="text-[10px] text-cyber-red uppercase font-bold tracking-wider leading-none">
                Active Critical SLA Target
              </div>
              <div className="text-white font-extrabold text-lg leading-none mt-1">
                {slaTime}s Remaining
              </div>
            </div>
          </div>
        )}

        {/* Simulation / Controls Panel */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Live vs Mock Switch */}
          <div className="flex items-center bg-zinc-950 border border-cyber-border rounded-lg p-1">
            <button
              onClick={() => {
                setIsLiveMode(false);
                setIsPlaying(true);
              }}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-all ${
                !isLiveMode
                  ? "bg-zinc-800 text-cyber-green border border-cyber-green/30"
                  : "text-cyber-text-muted hover:text-white"
              }`}
            >
              Demo Simulation
            </button>
            <button
              onClick={() => {
                setIsLiveMode(true);
                setIsPlaying(false);
              }}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-all flex items-center gap-1.5 ${
                isLiveMode
                  ? "bg-zinc-800 text-cyber-cyan border border-cyber-cyan/30"
                  : "text-cyber-text-muted hover:text-white"
              }`}
            >
              <Activity className="h-3 w-3" />
              Live Backend
            </button>
          </div>

          {/* Connection Status Dot */}
          {isLiveMode && (
            <div className="flex items-center gap-2 bg-zinc-900 border border-cyber-border px-3 py-1.5 rounded-lg text-xs font-mono">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  wsStatus === "open"
                    ? "bg-cyber-green shadow-[0_0_8px_#10b981]"
                    : wsStatus === "connecting"
                    ? "bg-cyber-amber animate-pulse"
                    : "bg-cyber-red shadow-[0_0_8px_#ef4444]"
                }`}
              />
              <span className="text-cyber-text-muted uppercase">
                {wsStatus === "open"
                  ? "WebSocket Live"
                  : wsStatus === "connecting"
                  ? "Connecting..."
                  : "Disconnected"}
              </span>
            </div>
          )}

          {/* Player controls (only for Simulation mode) */}
          {!isLiveMode && (
            <div className="flex items-center bg-zinc-900 border border-cyber-border rounded-lg p-0.5">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className={`p-1.5 rounded hover:bg-zinc-800 transition ${
                  isPlaying ? "text-cyber-amber" : "text-cyber-green"
                }`}
                title={isPlaying ? "Pause Automated Flow" : "Auto Play Flow"}
              >
                {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </button>
              
              <button
                onClick={triggerNextStep}
                disabled={isPlaying && step !== "NORMAL" && step !== "RESOLVED"}
                className="p-1.5 rounded hover:bg-zinc-800 transition text-white disabled:opacity-30 disabled:hover:bg-transparent"
                title="Trigger Next Step Manually"
              >
                <ArrowRight className="h-4 w-4" />
              </button>

              <button
                onClick={resetSimulation}
                className="p-1.5 rounded hover:bg-zinc-800 transition text-cyber-text-muted hover:text-white"
                title="Reset Simulation State"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            </div>
          )}

          {/* Veto Toggle */}
          <div className="flex items-center gap-2 bg-zinc-900 border border-cyber-border px-3 py-1.5 rounded-lg">
            <span className="text-xs font-mono text-cyber-text-muted uppercase flex items-center gap-1.5">
              <ShieldAlert className="h-3.5 w-3.5 text-cyber-amber" />
              Simulate Unsafe
            </span>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={unsafeVetoEnabled}
                onChange={(e) => setUnsafeVetoEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-9 h-5 bg-zinc-800 rounded-full peer peer-focus:ring-0 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-zinc-400 after:border-zinc-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-cyber-red peer-checked:after:bg-white"></div>
            </label>
          </div>
        </div>
      </div>
    </header>
  );
};
