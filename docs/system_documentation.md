# TelcOS Lite System Documentation
## Level 3/4 Autonomous Operations Framework for Communication Service Providers (CSPs)

---

## 1. Executive Summary & SLA Invariants
TelcOS Lite is a modular, production-ready framework designed to automate network-fault telemetry ingestion, AI-augmented cognitive troubleshooting, deterministic safety gating, southbound SSH remediation, and TMF621 ServiceNow trouble-ticket ticketing.

The framework operates under a **hard SLA budget of 30 seconds per incident**. Every phase—from ingestion to ticketing—is designed for minimal latency, non-blocking asynchronous execution, and predictable timeouts to guarantee compliance with this critical limit.

---

## 2. System Architecture Overview

The system follows **Clean Architecture** and **SOLID** design principles. It decouples the telemetry ingestion, cognitive orchestration, SSH execution, and ServiceNow integration into separate modules:

```mermaid
graph TD
    %% Styling
    classDef startEnd fill:#111,stroke:#00F3FF,stroke-width:2px,color:#00F3FF;
    classDef layer fill:#1E293B,stroke:#38BDF8,stroke-width:2px,color:#E2E8F0;
    classDef check fill:#2D1B4E,stroke:#C084FC,stroke-width:2px,color:#E9D5FF;
    classDef target fill:#1B2C24,stroke:#34D399,stroke-width:2px,color:#D1FAE5;
    classDef blocked fill:#3F1A1A,stroke:#F87171,stroke-width:2px,color:#FEE2E2;

    START([Inbound Kafka Event]) :::startEnd
    
    subgraph Ingestion["Ingestion Layer"]
        models[models.py: Pydantic Validation]
        consumer[kafka_consumer.py: Async consumer]
    end
    style Ingestion fill:#0F172A,stroke:#1E293B,color:#94A3B8
    
    subgraph Cognitive["Cognitive Layer (LangGraph DAG)"]
        triage[TRIAGE: Metadata Normalization]
        rag[RAG: ChromaDB Context Retrieval]
        strategy[STRATEGY: LLM / Playbook Planning]
        safety{SAFETY: Deterministic Veto}
    end
    style Cognitive fill:#0F172A,stroke:#1E293B,color:#94A3B8

    subgraph Execution["Execution Layer"]
        ssh[ssh_automation.py: Netmiko SSH]
    end
    style Execution fill:#0F172A,stroke:#1E293B,color:#94A3B8

    subgraph Federation["Federation Layer"]
        mapper[mapper.py: TMF621 Mapper]
        client[client.py: ServiceNow Client]
    end
    style Federation fill:#0F172A,stroke:#1E293B,color:#94A3B8

    blocked_node[BLOCKED: Audit Log / Purge State]

    START --> consumer
    consumer --> models
    models --> triage
    triage --> rag
    rag --> strategy
    strategy --> safety
    
    safety -- Approved (Verdict: Safe) --> ssh
    safety -- Vetoed (Verdict: Unsafe) --> blocked_node
    
    ssh --> mapper
    mapper --> client
    client --> END([End of Pipeline]) :::startEnd
    blocked_node --> END
    
    class triage,rag,strategy,models,consumer,mapper,client,ssh layer;
    class safety check;
    class blocked_node blocked;
```

---

## 3. Ingestion Layer (`src/ingestion/`)

The Ingestion Layer acts as the gatekeeper for all network-fault telemetry events entering the system.

### 3.1 Pydantic Domain Models ([models.py](file:///d:/_extra/TelcOS-lite/src/ingestion/models.py))
The `TelemetryEvent` class represents a frozen, immutable domain model parsing incoming alarms. It enforces:
* **Timezone-Aware UTC Normalization**: Naive datetimes are strictly rejected at parse time. All timestamps are forced into UTC to prevent offset comparison errors.
* **IP Address Checking**: Uses Python's standard `ipaddress` library to validate both IPv4 and IPv6 format structures.
* **Automatic SLA Expiration**: The field `sla_expiration` is a derived attribute computed dynamically as `telemetry_timestamp + 30 seconds`. The framework raises validation errors if an external client tries to pass this value manually.

### 3.2 Async Kafka Consumer ([kafka_consumer.py](file:///d:/_extra/TelcOS-lite/src/ingestion/kafka_consumer.py))
An asynchronous telemetry consumer built on top of `aiokafka`.
* **Transient Failure Isolation**: Message processing is wrapped in a retry cycle utilizing exponential backoff with full jitter:
  $$\text{Backoff} = \text{random}(0, \min(\text{ceiling}, \text{base} \times 2^{\text{attempt}}))$$
* **Dead-Letter Queue (DLQ)**: If a telemetry payload fails parsing or validation after 5 attempts, it is routed to a dedicated `telemetry.network.faults.dlq` topic. The DLQ message incorporates base64/safe-text formatting of the corrupted payload, failure stack trace, and ingestion metrics.
* **At-Least-Once Delivery**: Offsets are committed to Kafka only after successful processing or successful DLQ routing.

---

## 4. Cognitive Layer (`src/cognitive/`)

This layer represents the core decision-making loop, utilizing a LangGraph StateGraph topology.

### 4.1 Shared State Schema ([state.py](file:///d:/_extra/TelcOS-lite/src/cognitive/state.py))
The `GraphState` TypedDict is the canonical data-carrier that flows between all nodes. It maintains:
* `raw_event`: The ingress Kafka metadata envelope.
* `retrieved_context`: Chunks of runbooks matching the current alarm type.
* `proposed_commands`: Ordered remediation commands.
* `safety_evaluation`: The deterministic verdict (`safe` or `unsafe`), risk scores, and violated policies.
* `execution_output`: Device responses and execution latency tracking.
* `tmf_ticket_id`: Generated ServiceNow Trouble-Ticket ID.

### 4.2 Graph Topology & Routing ([graph.py](file:///d:/_extra/TelcOS-lite/src/cognitive/graph.py))
The LangGraph DAG defines linear state transitions from `START -> TRIAGE -> STRATEGY -> SAFETY`. 

At the `SAFETY` gate, a **pure deterministic conditional router** (`_route_after_safety`) analyzes the state.
* If `verdict == "safe"`, the execution branches to `EXECUTE -> TMF621 -> END`.
* If `verdict == "unsafe"` (or is missing/malformed), the execution branches to `BLOCKED -> END` (**fail-closed posture**).

### 4.3 RAG Ingestion & VectorStore ([vectorstore.py](file:///d:/_extra/TelcOS-lite/src/cognitive/vectorstore.py))
The RAG pipeline provides context to the decision engine.
* **Persistent DB**: Utilizes ChromaDB to store runbook procedures.
* **Local Embeddings**: Wraps HuggingFace's `sentence-transformers/all-MiniLM-L6-v2` locally on CPU. This eliminates external network requests and ensures predictable latency.
* **Idempotency**: Documents loaded via `load_documents.py` are chunked using a `RecursiveCharacterTextSplitter` and indexed using source path hashes to ensure re-runs overwrite old context safely.

### 4.4 Planning & Strategy ([nodes.py](file:///d:/_extra/TelcOS-lite/src/cognitive/nodes.py))
Generates remediation strategies:
* **LLM Engine**: Queries Llama3 via Ollama. It compiles a prompt using the normalized alarm and the RAG-matched runbooks. The temperature is locked at `0.1` to maintain near-deterministic output, and a JSON schema is requested.
* **Demo Mode Fallback**: If `demo_mode=True` or the Ollama client fails (timeouts, transport errors), the node falls back to static pre-defined playbooks (e.g. `clear counters` or `show processes cpu`) to protect SLA timing.

---

## 5. Deterministic Safety Layer

Operating autonomous networks demands absolute predictability. AI models are probabilistic and prone to hallucination; therefore, the **Safety Node is strictly deterministic and never delegated to an AI model**.

### 5.1 Verification Rules
The safety gate enforces two critical verification passes:
1. **Forbidden Commands Check**: Proposed commands are cross-referenced using regular expressions at word boundaries against a blocklist:
   * Blocked patterns: `\breload\b`, `\bshutdown\b`, `\berase\b`, `\bformat\b`.
2. **Power Level Safety Gate**: The alarm event's metadata is analyzed. If the device power level falls below **20%**, the strategy is vetoed to avoid draining battery reserves or crashing weak hardware during diagnostic procedures.

### 5.2 Failure Path (Blocked Node)
If any check fails:
* The verdict is set to `unsafe`.
* The `proposed_commands` array is **immediately purged** inside the GraphState to prevent downstream nodes from accessing the instructions.
* A high-severity security audit log is written, recording the exact policy violated, the original payload, and the vetoed command list.

---

## 6. Execution Layer (`src/execution/`)

### 6.1 SSH Automation ([ssh_automation.py](file:///d:/_extra/TelcOS-lite/src/execution/ssh_automation.py))
Commands that clear the safety gate are dispatched to the targeted device using Netmiko.
* **Single Session Reuse**: Multiple commands are sent through a single, open SSH session to minimize handshake overhead.
* **Bounded Latency**: Configured with strict timeouts (15s for connection, 20s per command read) to fit the 30-second SLA.
* **Exception Safety**: The execution function wraps all SSH/Paramiko transport exceptions, recording connection timeouts, authentication failures, and read errors directly into the `ExecutionResult` object instead of crashing the thread.
* **Clean Teardown**: SSH sessions are guaranteed to disconnect in a `finally` block.

---

## 7. Federation Layer (`src/federation/`)

### 7.1 Trouble Ticket Mapper ([mapper.py](file:///d:/_extra/TelcOS-lite/src/federation/mapper.py))
Maps the execution results into a trouble-ticket JSON payload conforming to the **TM Forum TMF621 Trouble Ticket specification**:
* Maps incident IDs, alarm severities (mapped to standard enums: `CRITICAL`, `MAJOR`, `MINOR`, etc.), and execution outputs into ticket notes.
* Translates resolution statuses to lifecycle states (`acknowledged`, `inProgress`, `resolved`, `pending`).

### 7.2 Federation Client ([client.py](file:///d:/_extra/TelcOS-lite/src/federation/client.py))
Dispatches tickets to downstream systems (mock ServiceNow API).
* **Retry Loop**: Employs an exponential back-off retry policy (1 initial attempt + 2 retries) sleeping for `0.5s` then `1.0s`.
* **Fail-Fast Boundary**: Retries only occur on 5xx status codes or network socket errors. Client errors (4xx codes) are failed immediately.
* **Lifecycle Controls**: Uses HTTPX's `AsyncClient` within an asynchronous context manager to ensure connection pool teardown.

---

## 8. Test & Verification Suite

The test framework uses `pytest` and handles complex asynchronous flows without local virtual machine dependencies.

### 8.1 Mocking Strategy ([conftest.py](file:///d:/_extra/TelcOS-lite/tests/conftest.py))
To avoid compilation requirements for libraries like `chromadb` (which requires local C++ compilers for `hnswlib`), `conftest.py` injects global stubs into `sys.modules`:
* Stubs out `netmiko`, `paramiko`, `chromadb`, and `aiokafka`.
* Dynamically patches Python's `GraphState` TypedDict structure at test runtime to inject `_node_state` tracking annotations, allowing complete LangGraph compile validation.

### 8.2 Test Modules
* **[test_models.py](file:///d:/_extra/TelcOS-lite/tests/test_models.py)**: Asserts UTC conversion, 30s SLA offsets, and IP validation.
* **[test_safety.py](file:///d:/_extra/TelcOS-lite/tests/test_safety.py)**: Validates command regex blocking, power thresholds, and missing values.
* **[test_graph.py](file:///d:/_extra/TelcOS-lite/tests/test_graph.py)**: Runs mock compiled StateGraphs to trace safe paths (to TMF621) and unsafe paths (to BLOCKED).
* **[test_tmf621.py](file:///d:/_extra/TelcOS-lite/tests/test_tmf621.py)**: Tests TM Forum schema generation, retry back-offs, and immediate client failures.

---

## 9. Operations Dashboard (`/dashboard`)

The frontend dashboard serves as a high-fidelity React interface mapping the backend's telemetry workflow.

```
/dashboard
├── src/
│   ├── types/index.ts         # Type models (Tower, EventLog, IncidentRecord)
│   ├── hooks/                 
│   │   ├── useDemoSimulation.ts # Local state machine (typewriter, SLA count)
│   │   └── useWebSocket.ts    # Live FastAPI streaming WS handler
│   ├── components/
│   │   ├── TowerGrid.tsx       # Live status grids for 15 towers
│   │   ├── PipelineVisualizer.tsx # Multi-step execution flowchart
│   │   ├── SafetyPanel.tsx     # Deterministic safety gate evaluation logs
│   │   ├── TerminalConsole.tsx  # Interactive typewriter SSH terminal emulator
│   │   ├── KpiMetrics.tsx      # Recharts graphs tracking SLA response times
│   │   └── HistoryTable.tsx    # Incident auditing console
│   ├── App.tsx                # Layout and view state routing
│   └── index.css              # Cyber-theme styling and LED keyframes
```

### 9.1 Theme System
The UI utilizes Tailwind CSS styled in a cyber-operations dark mode:
* **Glow/LED Effects**: Pulsing red/green glow filters (`animate-pulse`) simulating active cell tower faults.
* **SSH Console**: Typewriter-driven text rendering mimicking command execution over Netmiko.
* **Visual Flow**: The `PipelineVisualizer` highlights nodes dynamically as they execute in the backend.

---

## 10. Execution Guide

### Local Development Setup
1. **Infrastructure Provisioning**:
   ```bash
   docker compose up -d zookeeper kafka chromadb mock_ssh_device
   ```
2. **Backing Ingestion Bootstrapping**:
   ```bash
   python -m src.cognitive.load_documents --path data/runbooks.md
   ```
3. **Application Execution**:
   ```bash
   python -m src.main
   ```
4. **Dashboard Setup**:
   ```bash
   cd dashboard
   npm install
   npm run dev
   ```
5. **Testing Execution**:
   ```bash
   pytest -v tests/
   ```
