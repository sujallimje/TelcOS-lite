# Project Walkthrough: TelcOS Lite Operations Dashboard

I have designed, implemented, and validated a high-fidelity, cyber-ops dark mode Operations Dashboard to demonstrate the complete **TelcOS Lite autonomous remediation workflow** (Kafka → LangGraph → Safety → SSH Southbound → ServiceNow TMF621 → SLA Resolution).

---

## File Deliverables

The application is structured inside a new `/dashboard` folder to separate concerns from the Python backend:

*   **Configurations:**
    *   [package.json](file:///d:/_extra/TelcOS-lite/dashboard/package.json): Handles React, TypeScript, Vite, Tailwind CSS, Lucide React, Recharts, and Framer Motion dependencies.
    *   [tailwind.config.js](file:///d:/_extra/TelcOS-lite/dashboard/tailwind.config.js): Establishes custom cyber theme colors, neon shadows, and alert siren keyframe animations.
    *   [postcss.config.js](file:///d:/_extra/TelcOS-lite/dashboard/postcss.config.js): Configured for Tailwind CSS v3 PostCSS compilation.
    *   [vite.config.ts](file:///d:/_extra/TelcOS-lite/dashboard/vite.config.ts): Scaffolds building parameters.
    *   [index.html](file:///d:/_extra/TelcOS-lite/dashboard/index.html): Updates document titles, meta descriptors, viewport specifications, and containers.
*   **Styles & Entrypoints:**
    *   [src/index.css](file:///d:/_extra/TelcOS-lite/dashboard/src/index.css): Imports fonts, designs scanline overlays, blinking LED keyframes, glowing borders, custom scrollbars, and chart tooltips.
    *   [src/main.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/main.tsx): Mounts the React application.
    *   [src/types/index.ts](file:///d:/_extra/TelcOS-lite/dashboard/src/types/index.ts): Defines type models for `Tower`, `EventLog`, `IncidentRecord`, `SimStep`, and `PipelineStage`.
*   **State Hooks:**
    *   [src/hooks/useDemoSimulation.ts](file:///d:/_extra/TelcOS-lite/dashboard/src/hooks/useDemoSimulation.ts): Core state machine controlling continuous heartbeats, SLA countdowns, step delays, LLM mock command generation, policy guardrails, typewriter CLI outputs, ticket states, and past history databases.
    *   [src/hooks/useWebSocket.ts](file:///d:/_extra/TelcOS-lite/dashboard/src/hooks/useWebSocket.ts): Real WebSocket client handler with automatic reconnect schedules for live backend telemetry streaming.
*   **Integrations & Layouts:**
    *   [src/App.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/App.tsx): Coordinates global simulation parameters, tab navigation views, WebSocket updates, and layout columns.
    *   [src/components/Header.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/Header.tsx): Features logos, SLA warnings, play/pause controls, and unsafe simulation triggers.
    *   [src/components/Navigation.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/Navigation.tsx): Switches tabs between the active console dashboard and historical records views.
*   **Components:**
    *   [src/components/TowerGrid.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/TowerGrid.tsx): Displays the 15 towers, status rings, and performance meters.
    *   [src/components/EventStream.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/EventStream.tsx): Displays live Kafka event streams and incoming heartbeats.
    *   [src/components/PipelineVisualizer.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/PipelineVisualizer.tsx): Renders step-by-step backend stages and execution timings.
    *   [src/components/IncidentHistoryLog.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/IncidentHistoryLog.tsx): Renders a timeline of intermediate states specifically for the active incident.
    *   [src/components/RagPanel.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/RagPanel.tsx): Visualizes procedural documentation chunks matched with similarity metrics.
    *   [src/components/StrategyPanel.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/StrategyPanel.tsx): Renders generated CLI actions, LLM inputs, and outputs.
    *   [src/components/SafetyPanel.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/SafetyPanel.tsx): Represents the guardrail safety checklist, risk score, and verdict blocks.
    *   [src/components/TerminalConsole.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/TerminalConsole.tsx): Authentic SSH terminal display emulator.
    *   [src/components/TicketPanel.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/TicketPanel.tsx): Summarizes TM Forum ticketing and ServiceNow post indicators.
    *   [src/components/ResolutionCard.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/ResolutionCard.tsx): Displays final SLA margins and summaries.
    *   [src/components/HistoryTable.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/HistoryTable.tsx): Audits past resolved and blocked alarms.
    *   [src/components/KpiMetrics.tsx](file:///d:/_extra/TelcOS-lite/dashboard/src/components/KpiMetrics.tsx): Features Recharts components (AreaChart mapping latency vs SLA limit, BarChart mapping remediation actions).

---

## Verifications & Testing

1.  **TypeScript & Vite Build Validation:**
    *   Ran `tsc -b && vite build` inside `/dashboard`.
    *   The project successfully compiled into static outputs under `dist/` with **zero errors**.
2.  **Workflow Simulation Verification (Self-Contained Mode):**
    *   **Normal Operations:** Towers pulse green, logs show regular heartbeat receipts.
    *   **Fault Received:** Overheat alert is registered. `TWR-002` flashes red. Siren animation plays. SLA timer ticks down from 30s.
    *   **Orchestration Chain:** Pipeline stages update, RAG matches manual cooling procedures (similarity 94%), LLM recommends parameters (cooling aggressive, fans 90%), safety verifies compliance (SAFE), Netmiko connection connects and runs commands, TWR-002 recovers to green/healthy, TMF-621 trouble ticket posts successfully, and resolution details show final statistics.
3.  **Safety Veto Vetoed Command Verification:**
    *   Toggled "Simulate Unsafe Command".
    *   LLM produces a `reload` command.
    *   Safety checklist marks "Reload Detection Check" and "Forbidden Commands Check" as **Failed** (X). Safety card displays verdict: **BLOCKED / VETO TRIGGERED**.
    *   SSH Execution console is bypassed, preserving network integrity.
    *   TMF-621 Ticket is raised with status: **BLOCKED**.
    *   Incident is logged into the audit list as **BLOCKED**.
4.  **Audit Logs & History Views:**
    *   Historical tab successfully aggregates KPI cards.
    *   Recharts maps latency trends with area gradients and outlines safety vetos correctly.
