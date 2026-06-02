export interface Tower {
  id: string;
  status: "healthy" | "critical" | "recovering";
  lastPing: string;
  cpu: number;
  temperature: number;
  networkHealth: number;
  ip: string;
}

export interface EventLog {
  id: string;
  timestamp: string;
  source: "Kafka" | "LangGraph" | "Safety" | "SSH Console" | "ServiceNow" | "System";
  message: string;
  type: "info" | "warning" | "error" | "success";
}

export interface IncidentRecord {
  id: string;
  timestamp: string;
  alarm: string;
  asset: string;
  ip: string;
  rootCause: string;
  actionTaken: string;
  commands: string[];
  verdict: "SAFE" | "BLOCKED";
  executionTime: number; // in seconds
  slaRemaining: number; // in seconds
  ticketId: string;
  status: "Delivered" | "BLOCKED";
}

export type SimStep = 
  | "NORMAL" 
  | "FAULT_RECEIVED" 
  | "PIPELINE_PROCESSING" 
  | "RAG_RETRIEVAL" 
  | "AI_STRATEGY" 
  | "SAFETY_CHECK" 
  | "SSH_EXECUTION" 
  | "TICKET_CREATION" 
  | "RESOLVED";

export interface PipelineStage {
  id: string;
  name: string;
  status: "idle" | "running" | "completed" | "failed";
  durationMs?: number;
}
