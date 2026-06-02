import React, { useState, useCallback } from "react";
import { useDemoSimulation } from "./hooks/useDemoSimulation";
import { useWebSocket } from "./hooks/useWebSocket";
import { Header } from "./components/Header";
import { Navigation } from "./components/Navigation";
import { TowerGrid } from "./components/TowerGrid";
import { EventStream } from "./components/EventStream";
import { PipelineVisualizer } from "./components/PipelineVisualizer";
import { IncidentHistoryLog } from "./components/IncidentHistoryLog";
import { RagPanel } from "./components/RagPanel";
import { StrategyPanel } from "./components/StrategyPanel";
import { SafetyPanel } from "./components/SafetyPanel";
import { TerminalConsole } from "./components/TerminalConsole";
import { TicketPanel } from "./components/TicketPanel";
import { ResolutionCard } from "./components/ResolutionCard";
import { HistoryTable } from "./components/HistoryTable";
import { KpiMetrics } from "./components/KpiMetrics";
import { motion, AnimatePresence } from "framer-motion";

export const App: React.FC = () => {
  const {
    activeTab,
    setActiveTab,
    step,
    setStep,
    isPlaying,
    setIsPlaying,
    unsafeVetoEnabled,
    setUnsafeVetoEnabled,
    towers,
    eventLogs,
    currentIssueLogs,
    pastIncidents,
    kpis,
    slaTime,
    pipelineStages,
    ragData,
    strategyData,
    safetyData,
    terminalLines,
    ticketData,
    resolutionSummary,
    triggerNextStep,
    resetSimulation
  } = useDemoSimulation();

  const [isLiveMode, setIsLiveMode] = useState<boolean>(false);

  // Parse Live Backend WebSocket updates
  const handleWebSocketMessage = useCallback((data: any) => {
    if (!isLiveMode) return;

    // Transition frontend state based on backend updates
    if (data.raw_event) {
      setStep("FAULT_RECEIVED");
      // Populate logs and critical towers if relevant
    }
    if (data.retrieved_context) {
      setStep("RAG_RETRIEVAL");
    }
    if (data.proposed_commands) {
      setStep("AI_STRATEGY");
    }
    if (data.safety_evaluation) {
      setStep("SAFETY_CHECK");
    }
    if (data.execution_output) {
      setStep("SSH_EXECUTION");
    }
    if (data.tmf_ticket_id) {
      setStep("RESOLVED");
    }
  }, [isLiveMode, setStep]);

  const { status: wsStatus } = useWebSocket({
    url: "ws://localhost:8000/api/v1/demo/stream",
    onMessage: handleWebSocketMessage,
    enabled: isLiveMode
  });

  const isVetoed = safetyData.verdict === "BLOCKED";

  return (
    <div className="min-h-screen bg-cyber-bg text-cyber-text flex flex-col scanline-grid relative">
      {/* Decorative top grid lines */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyber-green/45 to-transparent z-10" />

      {/* Header */}
      <Header
        step={step}
        isPlaying={isPlaying}
        setIsPlaying={setIsPlaying}
        unsafeVetoEnabled={unsafeVetoEnabled}
        setUnsafeVetoEnabled={setUnsafeVetoEnabled}
        slaTime={slaTime}
        triggerNextStep={triggerNextStep}
        resetSimulation={resetSimulation}
        isLiveMode={isLiveMode}
        setIsLiveMode={setIsLiveMode}
        wsStatus={wsStatus}
      />

      {/* Navigation selector */}
      <Navigation activeTab={activeTab} setActiveTab={setActiveTab} />

      {/* Main Container */}
      <main className="flex-1 p-6 max-w-[1600px] w-full mx-auto space-y-6">
        <AnimatePresence mode="wait">
          {activeTab === "dashboard" ? (
            <motion.div
              key="dashboard-view"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="space-y-6"
            >
              {/* Row 1: Network Topology Map (Left) & Kafka Stream Log (Right) */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                <div className="lg:col-span-8">
                  <TowerGrid towers={towers} />
                </div>
                <div className="lg:col-span-4">
                  <EventStream logs={eventLogs} />
                </div>
              </div>

              {/* Row 2: Workflow Timeline Steps (Ingestion -> RAG -> Strategy -> Safety -> SSH Console / ServiceNow) */}
              <div>
                {/* Horizontal divider line for visual hierarchy */}
                <div className="flex items-center gap-3 mb-4">
                  <span className="h-[1px] bg-cyber-border/80 flex-1" />
                  <span className="text-[10px] font-mono uppercase tracking-widest text-cyber-text-muted">
                    Autonomous Operations Node Flow
                  </span>
                  <span className="h-[1px] bg-cyber-border/80 flex-1" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-6">
                  {/* Step 1: Pipeline */}
                  <PipelineVisualizer stages={pipelineStages} activeStep={step} />

                  {/* Step 2: RAG Retrieval */}
                  <RagPanel activeStep={step} ragData={ragData} />

                  {/* Step 3: AI Strategy */}
                  <StrategyPanel activeStep={step} strategyData={strategyData} />

                  {/* Step 4: Safety Check */}
                  <SafetyPanel activeStep={step} safetyData={safetyData} />

                  {/* Step 5: SSH Exec Terminal, Ticket, or Summary Card (Dynamic transition stack) */}
                  <div className="relative h-[230px]">
                    {step === "SSH_EXECUTION" && !isVetoed && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-10"
                      >
                        <TerminalConsole
                          activeStep={step}
                          terminalLines={terminalLines}
                          isVetoed={isVetoed}
                        />
                      </motion.div>
                    )}

                    {step === "TICKET_CREATION" && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-10"
                      >
                        <TicketPanel activeStep={step} ticketData={ticketData} />
                      </motion.div>
                    )}

                    {(step === "RESOLVED" || step === "NORMAL" || step === "FAULT_RECEIVED" || step === "PIPELINE_PROCESSING" || step === "RAG_RETRIEVAL" || step === "AI_STRATEGY" || (step === "SAFETY_CHECK" && isVetoed)) && (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.98 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0 }}
                        className="absolute inset-0 z-10"
                      >
                        <ResolutionCard summary={resolutionSummary} />
                      </motion.div>
                    )}
                  </div>
                </div>
              </div>

              {/* Row 3: Active Incident History Log (Visual trace of current steps) */}
              <div className="grid grid-cols-1 gap-6">
                <IncidentHistoryLog logs={currentIssueLogs} />
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="history-view"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              transition={{ duration: 0.3 }}
              className="space-y-6"
            >
              {/* KPI metrics at top of history view */}
              <KpiMetrics kpis={kpis} incidents={pastIncidents} />

              {/* Incidents Table audit log */}
              <HistoryTable incidents={pastIncidents} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      
      {/* Footer info */}
      <footer className="border-t border-cyber-border/40 py-3 text-center text-[10px] font-mono text-cyber-text-muted mt-auto bg-cyber-card/30">
        TelcOS Lite Operations Dashboard • Securing 4G/5G autonomous core remediations • SLA Target: &lt;= 30s
      </footer>
    </div>
  );
};
export default App;
