import React from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from "recharts";
import { Activity, ShieldCheck, ShieldAlert, Clock, BarChart3 } from "lucide-react";
import type { IncidentRecord } from "../types";

interface KpiMetricsProps {
  kpis: {
    eventsProcessed: number;
    successfulRemediations: number;
    blockedActions: number;
    avgResolutionTime: number;
  };
  incidents: IncidentRecord[];
}

export const KpiMetrics: React.FC<KpiMetricsProps> = ({ kpis, incidents }) => {
  // Map incidents for charting (reverse chronology to normal timeline)
  const chartData = [...incidents]
    .reverse()
    .map((inc) => ({
      name: `Ticket #${inc.ticketId.split("-").pop()}`,
      executionTime: inc.executionTime,
      slaLimit: 30,
      slaRemaining: inc.slaRemaining,
      verdict: inc.verdict,
    }));

  // Safe vs Blocked aggregation data
  const volumeData = [
    {
      name: "Remediations",
      Successful: kpis.successfulRemediations,
      Blocked: kpis.blockedActions,
    }
  ];

  return (
    <div className="space-y-6">
      {/* KPI Cards Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1 */}
        <div className="glow-card p-4 flex items-center justify-between">
          <div>
            <span className="text-[10px] font-mono text-cyber-text-muted uppercase tracking-wider block">
              Events Processed
            </span>
            <span className="text-2xl font-sans font-black text-white mt-1 block">
              {kpis.eventsProcessed}
            </span>
          </div>
          <div className="bg-cyber-blue/10 border border-cyber-blue/20 text-cyber-blue p-2 rounded-lg">
            <Activity className="h-5 w-5 animate-pulse" />
          </div>
        </div>

        {/* KPI 2 */}
        <div className="glow-card p-4 flex items-center justify-between">
          <div>
            <span className="text-[10px] font-mono text-cyber-text-muted uppercase tracking-wider block">
              Successful Remediations
            </span>
            <span className="text-2xl font-sans font-black text-cyber-green mt-1 block">
              {kpis.successfulRemediations}
            </span>
          </div>
          <div className="bg-cyber-green/10 border border-cyber-green/20 text-cyber-green p-2 rounded-lg">
            <ShieldCheck className="h-5 w-5" />
          </div>
        </div>

        {/* KPI 3 */}
        <div className="glow-card p-4 flex items-center justify-between">
          <div>
            <span className="text-[10px] font-mono text-cyber-text-muted uppercase tracking-wider block">
              Blocked Actions
            </span>
            <span className="text-2xl font-sans font-black text-cyber-red mt-1 block">
              {kpis.blockedActions}
            </span>
          </div>
          <div className="bg-cyber-red/10 border border-cyber-red/20 text-cyber-red p-2 rounded-lg">
            <ShieldAlert className="h-5 w-5" />
          </div>
        </div>

        {/* KPI 4 */}
        <div className="glow-card p-4 flex items-center justify-between">
          <div>
            <span className="text-[10px] font-mono text-cyber-text-muted uppercase tracking-wider block">
              Avg Resolution Time
            </span>
            <span className="text-2xl font-sans font-black text-cyber-cyan mt-1 block">
              {kpis.avgResolutionTime}s
            </span>
          </div>
          <div className="bg-cyber-cyan/10 border border-cyber-cyan/20 text-cyber-cyan p-2 rounded-lg">
            <Clock className="h-5 w-5" />
          </div>
        </div>
      </div>

      {/* Recharts Panels Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Latency History Chart (2/3 width) */}
        <div className="glow-card p-5 lg:col-span-2 flex flex-col h-[320px]">
          <div className="flex items-center gap-2 border-b border-cyber-border pb-3 mb-4">
            <BarChart3 className="h-4.5 w-4.5 text-cyber-green" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-white">
              Remediation Latency vs. 30s SLA Limit
            </h3>
          </div>

          <div className="flex-1 w-full text-xs">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorLatency" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4}/>
                    <stop offset="95%" stopColor="#06b6d4" stopOpacity={0.0}/>
                  </linearGradient>
                  <linearGradient id="colorSla" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a50" />
                <XAxis dataKey="name" stroke="#71717a" strokeWidth={1} style={{ fontSize: "10px", fontFamily: "monospace" }} />
                <YAxis stroke="#71717a" strokeWidth={1} style={{ fontSize: "10px", fontFamily: "monospace" }} />
                <Tooltip contentStyle={{ backgroundColor: "#121214", borderColor: "#27272a" }} />
                <Legend wrapperStyle={{ fontSize: "10px", fontFamily: "monospace", paddingTop: "5px" }} />
                <Area name="Remediation Latency (s)" type="monotone" dataKey="executionTime" stroke="#06b6d4" fillOpacity={1} fill="url(#colorLatency)" strokeWidth={2} />
                <Area name="SLA Deadline (s)" type="monotone" dataKey="slaLimit" stroke="#ef4444" fillOpacity={1} fill="url(#colorSla)" strokeWidth={1.5} strokeDasharray="5 5" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Volume Safe vs Blocked Chart (1/3 width) */}
        <div className="glow-card p-5 flex flex-col h-[320px]">
          <div className="flex items-center gap-2 border-b border-cyber-border pb-3 mb-4">
            <ShieldCheck className="h-4.5 w-4.5 text-cyber-cyan" />
            <h3 className="text-xs font-bold uppercase tracking-wider text-white">
              Remediation Action Audit
            </h3>
          </div>

          <div className="flex-1 w-full text-xs">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={volumeData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a50" />
                <XAxis dataKey="name" stroke="#71717a" style={{ fontSize: "10px", fontFamily: "monospace" }} />
                <YAxis stroke="#71717a" style={{ fontSize: "10px", fontFamily: "monospace" }} />
                <Tooltip contentStyle={{ backgroundColor: "#121214", borderColor: "#27272a" }} />
                <Legend wrapperStyle={{ fontSize: "10px", fontFamily: "monospace", paddingTop: "5px" }} />
                <Bar name="Successful Safe Actions" dataKey="Successful" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar name="Safety Veto / Blocks" dataKey="Blocked" fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
