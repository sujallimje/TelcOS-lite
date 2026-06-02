import { useState, useEffect, useCallback, useRef } from "react";
import type { Tower, EventLog, IncidentRecord, SimStep, PipelineStage } from "../types";

const INITIAL_TOWERS: Tower[] = Array.from({ length: 15 }, (_, i) => {
  const id = `TWR-${String(i + 1).padStart(3, "0")}`;
  return {
    id,
    status: "healthy",
    lastPing: new Date().toLocaleTimeString(),
    cpu: Math.floor(Math.random() * 25) + 15,
    temperature: Math.floor(Math.random() * 15) + 35,
    networkHealth: 100 - Math.floor(Math.random() * 3),
    ip: `10.0.89.${i + 1}`,
  };
});

const INITIAL_KPIS = {
  eventsProcessed: 142,
  successfulRemediations: 88,
  blockedActions: 12,
  avgResolutionTime: 4.8, // in seconds
};

export const useDemoSimulation = () => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "history">("dashboard");
  const [step, setStep] = useState<SimStep>("NORMAL");
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [unsafeVetoEnabled, setUnsafeVetoEnabled] = useState<boolean>(false);
  const [towers, setTowers] = useState<Tower[]>(INITIAL_TOWERS);
  const [eventLogs, setEventLogs] = useState<EventLog[]>([]);
  const [currentIssueLogs, setCurrentIssueLogs] = useState<EventLog[]>([]);
  const [pastIncidents, setPastIncidents] = useState<IncidentRecord[]>([
    {
      id: "TMF-621-INC-882041",
      timestamp: new Date(Date.now() - 3600000 * 4).toISOString(),
      alarm: "BBU_OVERHEATING_CRITICAL",
      asset: "TWR-005",
      ip: "10.0.89.5",
      rootCause: "Thermal Threshold Breach",
      actionTaken: "Cooling Profile Increased",
      commands: ["set cooling-profile aggressive", "set fan-speed 90"],
      verdict: "SAFE",
      executionTime: 4.1,
      slaRemaining: 25.9,
      ticketId: "TMF-621-INC-882041",
      status: "Delivered",
    },
    {
      id: "TMF-621-INC-882190",
      timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
      alarm: "CONFIG_INTEGRITY_FAIL",
      asset: "TWR-012",
      ip: "10.0.89.12",
      rootCause: "Unauthorized Reload Detected",
      actionTaken: "Execution Blocked - Safety Veto",
      commands: ["reload"],
      verdict: "BLOCKED",
      executionTime: 1.2,
      slaRemaining: 28.8,
      ticketId: "TMF-621-INC-882190",
      status: "BLOCKED",
    }
  ]);
  const [kpis, setKpis] = useState(INITIAL_KPIS);
  const [slaTime, setSlaTime] = useState<number>(30);
  
  // Pipeline Data
  const [pipelineStages, setPipelineStages] = useState<PipelineStage[]>([
    { id: "kafka", name: "Kafka Ingestion", status: "idle" },
    { id: "consumer", name: "FastAPI Consumer", status: "idle" },
    { id: "timestamp", name: "Timestamp Enrichment", status: "idle" },
    { id: "graph", name: "LangGraph Dispatch", status: "idle" }
  ]);

  // Step specific detail states
  const [ragData, setRagData] = useState<{
    manualMatch: string;
    chunks: string[];
    similarityScore: number;
    status: "idle" | "loading" | "retrieved";
  }>({
    manualMatch: "",
    chunks: [],
    similarityScore: 0,
    status: "idle"
  });

  const [strategyData, setStrategyData] = useState<{
    commands: string[];
    confidence: number;
    inputs: string;
    outputs: string;
    status: "idle" | "generated";
  }>({
    commands: [],
    confidence: 0,
    inputs: "",
    outputs: "",
    status: "idle"
  });

  const [safetyData, setSafetyData] = useState<{
    checks: { name: string; passed: boolean | null }[];
    verdict: "PENDING" | "SAFE" | "BLOCKED";
    status: "idle" | "evaluating" | "completed";
  }>({
    checks: [
      { name: "Forbidden Commands", passed: null },
      { name: "Shutdown Detection", passed: null },
      { name: "Reload Detection", passed: null },
      { name: "Power Threshold Check (>20%)", passed: null }
    ],
    verdict: "PENDING",
    status: "idle"
  });

  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const [ticketData, setTicketData] = useState<{
    id: string;
    asset: string;
    alarm: string;
    resolution: string;
    status: "idle" | "posting" | "delivered" | "blocked";
  }>({
    id: "",
    asset: "",
    alarm: "",
    resolution: "",
    status: "idle"
  });

  const [resolutionSummary, setResolutionSummary] = useState<{
    alarm: string;
    asset: string;
    rootCause: string;
    actionTaken: string;
    executionTime: number;
    slaRemaining: number;
    result: string;
  } | null>(null);

  // References to preserve state timing
  const isPlayingRef = useRef(isPlaying);
  isPlayingRef.current = isPlaying;
  const stepRef = useRef(step);
  stepRef.current = step;
  const unsafeRef = useRef(unsafeVetoEnabled);
  unsafeRef.current = unsafeVetoEnabled;

  // Add event log helper
  const addLog = useCallback((message: string, source: EventLog["source"], type: EventLog["type"] = "info", isIncidentSpecific: boolean = false) => {
    const newLog: EventLog = {
      id: `log-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp: new Date().toLocaleTimeString(),
      source,
      message,
      type
    };
    setEventLogs(prev => [newLog, ...prev.slice(0, 99)]);
    if (isIncidentSpecific) {
      setCurrentIssueLogs(prev => [...prev, newLog]);
    }
  }, []);

  // Continuous background pings during NORMAL operation
  useEffect(() => {
    const pingInterval = setInterval(() => {
      if (stepRef.current === "NORMAL") {
        setTowers(prev => prev.map(t => {
          // Add minor normal variance
          const variance = Math.random() > 0.5 ? 1 : -1;
          const cpuVar = Math.max(10, Math.min(80, t.cpu + variance * Math.floor(Math.random() * 3)));
          const tempVar = Math.max(30, Math.min(65, t.temperature + variance * Math.floor(Math.random() * 2)));
          
          return {
            ...t,
            lastPing: new Date().toLocaleTimeString(),
            cpu: cpuVar,
            temperature: tempVar
          };
        }));

        // Log one random tower's heartbeat OK every few seconds
        const randomTowerIdx = Math.floor(Math.random() * 15);
        const twr = INITIAL_TOWERS[randomTowerIdx];
        addLog(`${twr.id} → Heartbeat OK`, "System", "info");
      }
    }, 2500);

    return () => clearInterval(pingInterval);
  }, [addLog]);

  useEffect(() => {
    let timer: any;
    if (step !== "NORMAL" && step !== "RESOLVED") {
      timer = setInterval(() => {
        setSlaTime(prev => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => clearInterval(timer);
  }, [step]);

  // Main State Machine Transition Core Logic
  const triggerNextStep = useCallback(() => {
    const currentStep = stepRef.current;
    const veto = unsafeRef.current;

    switch (currentStep) {
      case "NORMAL": {
        // Step 2: Fault Event Arrives
        setStep("FAULT_RECEIVED");
        setSlaTime(30);
        setCurrentIssueLogs([]); // Reset active issue logs
        
        addLog("Kafka Ingress: BBU_OVERHEATING_CRITICAL alarm received", "Kafka", "error", true);
        addLog("Asset details: TWR-002, Management IP: 10.0.89.2", "Kafka", "info", true);

        // Turn TWR-002 to CRITICAL state
        setTowers(prev => prev.map(t => {
          if (t.id === "TWR-002") {
            return {
              ...t,
              status: "critical",
              temperature: 92, // Overheating trigger
              cpu: 78,
              networkHealth: 45
            };
          }
          return t;
        }));
        
        // Reset and prime workflow components
        setPipelineStages([
          { id: "kafka", name: "Kafka Ingestion", status: "idle" },
          { id: "consumer", name: "FastAPI Consumer", status: "idle" },
          { id: "timestamp", name: "Timestamp Enrichment", status: "idle" },
          { id: "graph", name: "LangGraph Dispatch", status: "idle" }
        ]);
        setRagData({ manualMatch: "", chunks: [], similarityScore: 0, status: "idle" });
        setStrategyData({ commands: [], confidence: 0, inputs: "", outputs: "", status: "idle" });
        setSafetyData({
          checks: [
            { name: "Forbidden Commands", passed: null },
            { name: "Shutdown Detection", passed: null },
            { name: "Reload Detection", passed: null },
            { name: "Power Threshold Check (>20%)", passed: null }
          ],
          verdict: "PENDING",
          status: "idle"
        });
        setTerminalLines([]);
        setTicketData({ id: "", asset: "", alarm: "", resolution: "", status: "idle" });
        setResolutionSummary(null);
        break;
      }
      case "FAULT_RECEIVED": {
        // Step 3: Backend Processing Pipeline
        setStep("PIPELINE_PROCESSING");
        addLog("Initiating autonomous workflow pipeline", "System", "info", true);
        
        // Simulate step durations
        setTimeout(() => {
          setPipelineStages(prev => prev.map(s => s.id === "kafka" ? { ...s, status: "completed", durationMs: 150 } : s));
          addLog("Kafka Ingestion completed (150ms)", "LangGraph", "success", true);
        }, 600);

        setTimeout(() => {
          setPipelineStages(prev => prev.map(s => s.id === "consumer" ? { ...s, status: "completed", durationMs: 120 } : s));
          addLog("FastAPI consumer parsed payload (120ms)", "LangGraph", "success", true);
        }, 1200);

        setTimeout(() => {
          setPipelineStages(prev => prev.map(s => s.id === "timestamp" ? { ...s, status: "completed", durationMs: 10 } : s));
          addLog("Timestamp enrichment successful (10ms)", "LangGraph", "success", true);
        }, 1800);

        setTimeout(() => {
          setPipelineStages(prev => prev.map(s => s.id === "graph" ? { ...s, status: "completed", durationMs: 45 } : s));
          addLog("LangGraph dispatch executed (45ms)", "LangGraph", "success", true);
        }, 2400);

        break;
      }
      case "PIPELINE_PROCESSING": {
        // Step 4: RAG Retrieval
        setStep("RAG_RETRIEVAL");
        setRagData(prev => ({ ...prev, status: "loading" }));
        addLog("Querying vector store for cooling operations manual...", "LangGraph", "info", true);
        
        setTimeout(() => {
          setRagData({
            status: "retrieved",
            manualMatch: "BBU Cooling Procedure v2.4",
            similarityScore: 0.94,
            chunks: [
              "Check fan status and thermal indicators",
              "Increase cooling profile to aggressive configuration",
              "Verify thermal threshold drops below target limits"
            ]
          });
          addLog("RAG Success: Document 'BBU Cooling Procedure v2.4' matched (Similarity: 94%)", "LangGraph", "success", true);
        }, 1000);
        break;
      }
      case "RAG_RETRIEVAL": {
        // Step 5: AI Strategy Generation
        setStep("AI_STRATEGY");
        addLog("Dispatching parameters to LLM strategy node", "LangGraph", "info", true);
        
        const commands = veto ? ["reload"] : ["set cooling-profile aggressive", "set fan-speed 90"];
        
        setStrategyData({
          status: "generated",
          commands,
          confidence: veto ? 0.82 : 0.98,
          inputs: "Alarm: BBU_OVERHEATING_CRITICAL, Node: TWR-002, Proc: BBU Cooling Procedure v2.4",
          outputs: commands.join("\n")
        });
        
        addLog(`AI Strategy generated ${commands.length} execution command(s)`, "LangGraph", "success", true);
        break;
      }
      case "AI_STRATEGY": {
        // Step 6: Safety Guardrail
        setStep("SAFETY_CHECK");
        setSafetyData(prev => ({ ...prev, status: "evaluating" }));
        addLog("Evaluating generated commands against network safety policies", "Safety", "warning", true);

        // Transition through checks step-by-step
        setTimeout(() => {
          setSafetyData(prev => {
            const checks = [...prev.checks];
            checks[0] = { name: "Forbidden Commands Check", passed: veto ? false : true };
            return { ...prev, checks };
          });
          if (veto) {
            addLog("Safety Check Error: Command 'reload' matches forbidden list", "Safety", "error", true);
          } else {
            addLog("Safety Check OK: No forbidden commands detected", "Safety", "success", true);
          }
        }, 600);

        setTimeout(() => {
          setSafetyData(prev => {
            const checks = [...prev.checks];
            checks[1] = { name: "Shutdown Detection Check", passed: true };
            return { ...prev, checks };
          });
          addLog("Safety Check OK: No shutdown operations detected", "Safety", "success", true);
        }, 1200);

        setTimeout(() => {
          setSafetyData(prev => {
            const checks = [...prev.checks];
            checks[2] = { name: "Reload Detection Check", passed: veto ? false : true };
            return { ...prev, checks };
          });
          if (veto) {
            addLog("Safety Check Failed: System reload requested", "Safety", "error", true);
          } else {
            addLog("Safety Check OK: No reloading scheduled", "Safety", "success", true);
          }
        }, 1800);

        setTimeout(() => {
          setSafetyData(prev => {
            const checks = [...prev.checks];
            checks[3] = { name: "Power Threshold Check (>20%)", passed: true };
            return { ...prev, checks };
          });
          addLog("Safety Check OK: Power metrics acceptable (50%)", "Safety", "success", true);
          
          setSafetyData(prev => ({
            ...prev,
            status: "completed",
            verdict: veto ? "BLOCKED" : "SAFE"
          }));
          
          if (veto) {
            addLog("SAFETY POLICY VIOLATED - VETO TRIGGERED", "Safety", "error", true);
          } else {
            addLog("SAFETY EVALUATION COMPLETE: COMMANDS VERIFIED SAFE", "Safety", "success", true);
          }
        }, 2400);

        break;
      }
      case "SAFETY_CHECK": {
        if (veto) {
          // If veto is triggered, we skip SSH execution completely and go directly to ticket generation
          setStep("TICKET_CREATION");
          setTicketData({
            id: `TMF-621-INC-${Math.floor(100000 + Math.random() * 900000)}`,
            asset: "TWR-002",
            alarm: "BBU_OVERHEATING_CRITICAL",
            resolution: "Safety veto triggered: Reload command blocked.",
            status: "posting"
          });
          addLog("Creating ticket with status BLOCKED...", "ServiceNow", "warning", true);
        } else {
          // Step 7: SSH Execution
          setStep("SSH_EXECUTION");
          addLog("Initiating southbound Netmiko connection to 10.0.89.2:2222", "SSH Console", "info", true);
          
          const lines = [
            "Connecting to 10.0.89.2...",
            "SSH connection established.",
            "Authentication successful (user: admin).",
            "bash-5.1# set cooling-profile aggressive",
            "SUCCESS: cooling profile updated to aggressive",
            "bash-5.1# set fan-speed 90",
            "SUCCESS: fan duty set to 90%",
            "bash-5.1# exit",
            "Closing SSH session. Disconnected."
          ];

          // Type out console lines with interval
          lines.forEach((line, index) => {
            setTimeout(() => {
              setTerminalLines(prev => [...prev, line]);
              if (line.includes("SUCCESS")) {
                addLog(`Console Output: ${line}`, "SSH Console", "success", true);
              } else {
                addLog(`SSH: ${line}`, "SSH Console", "info", true);
              }

              // Animate TWR-002 transitions
              if (line.includes("cooling-profile")) {
                setTowers(prev => prev.map(t => t.id === "TWR-002" ? { ...t, status: "recovering", temperature: 72, networkHealth: 80 } : t));
                addLog("Tower TWR-002 status: RECOVERING", "System", "warning", true);
              }
              if (line.includes("fan-speed")) {
                setTowers(prev => prev.map(t => t.id === "TWR-002" ? { ...t, status: "healthy", temperature: 52, networkHealth: 98 } : t));
                addLog("Tower TWR-002 status: HEALTHY", "System", "success", true);
              }
            }, index * 300);
          });
        }
        break;
      }
      case "SSH_EXECUTION": {
        // Step 8: TMF621 ServiceNow Ticket
        setStep("TICKET_CREATION");
        setTicketData({
          id: `TMF-621-INC-${Math.floor(100000 + Math.random() * 900000)}`,
          asset: "TWR-002",
          alarm: "BBU_OVERHEATING_CRITICAL",
          resolution: "BBU cooling profile set to aggressive and fan speed adjusted to 90%. Temperature restored to 52C.",
          status: "posting"
        });
        addLog("Generating TMF-621 Trouble Ticket JSON payload", "ServiceNow", "info", true);
        
        setTimeout(() => {
          setTicketData(prev => ({ ...prev, status: "delivered" }));
          addLog("POST -> ServiceNow successful (Delivered)", "ServiceNow", "success", true);
        }, 1500);
        break;
      }
      case "TICKET_CREATION": {
        // Step 9: Final Resolution Dashboard
        setStep("RESOLVED");
        
        const finalExecutionTime = veto ? 1.2 : 4.2;
        const finalSlaRemaining = 30.0 - finalExecutionTime;
        
        setResolutionSummary({
          alarm: "BBU_OVERHEATING_CRITICAL",
          asset: "TWR-002",
          rootCause: veto ? "Unsafe command requested (reload)" : "Thermal Threshold Breach",
          actionTaken: veto ? "Execution Blocked - Safety Veto Applied" : "Cooling Profile Increased via SSH CLI",
          executionTime: finalExecutionTime,
          slaRemaining: finalSlaRemaining,
          result: veto ? "SAFETY VETO TRIGGERED" : "AUTONOMOUS REMEDIATION SUCCESSFUL"
        });

        // Add incident to pastIncidents list
        const ticketId = ticketData.id;
        const newRecord: IncidentRecord = {
          id: ticketId,
          timestamp: new Date().toISOString(),
          alarm: "BBU_OVERHEATING_CRITICAL",
          asset: "TWR-002",
          ip: "10.0.89.2",
          rootCause: veto ? "Unsafe command (reload)" : "Thermal Threshold Breach",
          actionTaken: veto ? "Blocked by safety guardrail" : "Cooling profile set to aggressive, fans at 90%",
          commands: veto ? ["reload"] : ["set cooling-profile aggressive", "set fan-speed 90"],
          verdict: veto ? "BLOCKED" : "SAFE",
          executionTime: finalExecutionTime,
          slaRemaining: finalSlaRemaining,
          ticketId,
          status: veto ? "BLOCKED" : "Delivered"
        };
        
        setPastIncidents(prev => [newRecord, ...prev]);

        // Update KPIs
        setKpis(prev => ({
          eventsProcessed: prev.eventsProcessed + 1,
          successfulRemediations: veto ? prev.successfulRemediations : prev.successfulRemediations + 1,
          blockedActions: veto ? prev.blockedActions + 1 : prev.blockedActions,
          avgResolutionTime: Number(((prev.avgResolutionTime * prev.eventsProcessed + finalExecutionTime) / (prev.eventsProcessed + 1)).toFixed(1))
        }));

        if (veto) {
          addLog("Remediation terminated. Event safety veto recorded.", "System", "error", true);
        } else {
          addLog("Remediation completed successfully. Node status stabilized.", "System", "success", true);
        }
        break;
      }
      case "RESOLVED": {
        // Cycle back to Normal Operations
        setStep("NORMAL");
        addLog("Returning to normal monitoring mode", "System", "info");
        // Reset TWR-002 metrics back to normal if they were still red/critical
        setTowers(prev => prev.map(t => {
          if (t.id === "TWR-002") {
            return {
              ...t,
              status: "healthy",
              temperature: 42,
              cpu: 32,
              networkHealth: 100
            };
          }
          return t;
        }));
        break;
      }
      default:
        break;
    }
  }, [addLog, ticketData.id, ticketData.status]);

  // Automated 3-second simulation step delay loop
  useEffect(() => {
    let loopTimer: any;
    if (isPlaying && step !== "NORMAL" && step !== "RESOLVED") {
      // Set timer to transition
      const duration = step === "SAFETY_CHECK" ? 3000 : 3500; // Allow extra time for checks animations
      loopTimer = setTimeout(() => {
        triggerNextStep();
      }, duration);
    }
    return () => clearTimeout(loopTimer);
  }, [isPlaying, step, triggerNextStep]);

  // Trigger manual simulation start
  const runSimulation = () => {
    if (step === "NORMAL") {
      triggerNextStep();
    }
  };

  const resetSimulation = () => {
    setStep("NORMAL");
    setTowers(INITIAL_TOWERS);
    setSlaTime(30);
    setTerminalLines([]);
    setRagData({ manualMatch: "", chunks: [], similarityScore: 0, status: "idle" });
    setStrategyData({ commands: [], confidence: 0, inputs: "", outputs: "", status: "idle" });
    setSafetyData({
      checks: [
        { name: "Forbidden Commands", passed: null },
        { name: "Shutdown Detection", passed: null },
        { name: "Reload Detection", passed: null },
        { name: "Power Threshold Check (>20%)", passed: null }
      ],
      verdict: "PENDING",
      status: "idle"
    });
    setTicketData({ id: "", asset: "", alarm: "", resolution: "", status: "idle" });
    setResolutionSummary(null);
    setCurrentIssueLogs([]);
    addLog("Demo dashboard manual reset triggered", "System", "info");
  };

  return {
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
    runSimulation,
    resetSimulation
  };
};
