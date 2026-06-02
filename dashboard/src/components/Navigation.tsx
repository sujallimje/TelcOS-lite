import React from "react";
import { LayoutDashboard, History } from "lucide-react";

interface NavigationProps {
  activeTab: "dashboard" | "history";
  setActiveTab: (tab: "dashboard" | "history") => void;
}

export const Navigation: React.FC<NavigationProps> = ({ activeTab, setActiveTab }) => {
  return (
    <div className="flex border-b border-cyber-border/40 bg-cyber-bg px-6">
      <button
        onClick={() => setActiveTab("dashboard")}
        className={`flex items-center gap-2 px-5 py-3.5 text-xs font-mono tracking-wider uppercase border-b-2 transition-all ${
          activeTab === "dashboard"
            ? "border-cyber-green text-cyber-green bg-cyber-green/5"
            : "border-transparent text-cyber-text-muted hover:text-white"
        }`}
      >
        <LayoutDashboard className="h-4 w-4" />
        Operations Dashboard
      </button>

      <button
        onClick={() => setActiveTab("history")}
        className={`flex items-center gap-2 px-5 py-3.5 text-xs font-mono tracking-wider uppercase border-b-2 transition-all ${
          activeTab === "history"
            ? "border-cyber-cyan text-cyber-cyan bg-cyber-cyan/5"
            : "border-transparent text-cyber-text-muted hover:text-white"
        }`}
      >
        <History className="h-4 w-4" />
        Resolution History
      </button>
    </div>
  );
};
