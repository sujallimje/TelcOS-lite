"""
src/cognitive/nodes.py

TelcOS Lite – Level 3/4 Autonomous Operations Framework
Cognitive layer: LangGraph node implementations.

Nodes
-----
1. triage_node   – Normalise alarm metadata into a canonical schema.
2. rag_node      – Retrieve relevant runbook context from ChromaDB.
3. strategy_node – Produce remediation commands (demo or live via Ollama/Llama3).
4. safety_node   – Deterministic safety gate; never AI-delegated.
5. blocked_node  – Terminal sink for commands that fail the safety gate.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from chromadb import AsyncHttpClient as ChromaAsyncHttpClient
from langchain_core.documents import Document
from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical state schema (Pydantic V2)
# ---------------------------------------------------------------------------


class AlarmMetadata(BaseModel):
    """Normalised alarm envelope produced by triage_node."""

    alarm_id: str = Field(..., description="Unique alarm identifier.")
    source_device: str = Field(..., description="FQDN or management IP of the originating device.")
    alarm_type: str = Field(..., description="Alarm classification (e.g. 'link_down', 'cpu_high').")
    severity: str = Field(..., description="Normalised severity: CRITICAL | MAJOR | MINOR | WARNING | INFO.")
    timestamp_utc: str = Field(..., description="ISO-8601 UTC timestamp of alarm occurrence.")
    raw_payload: dict[str, Any] = Field(default_factory=dict, description="Original alarm payload for audit.")

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, v: str) -> str:
        mapping = {
            "crit": "CRITICAL",
            "critical": "CRITICAL",
            "maj": "MAJOR",
            "major": "MAJOR",
            "min": "MINOR",
            "minor": "MINOR",
            "warn": "WARNING",
            "warning": "WARNING",
            "info": "INFO",
            "informational": "INFO",
        }
        return mapping.get(v.lower(), v.upper())


class SafetyResult(BaseModel):
    """Deterministic safety evaluation result."""

    is_safe: bool
    reason: str


class GraphState(BaseModel):
    """
    Shared mutable state flowing through the LangGraph DAG.

    All nodes read from and write to this object.  Only fields
    explicitly documented here are considered stable API surface.
    """

    # Input fields (set before the graph starts)
    raw_alarm: dict[str, Any] = Field(..., description="Raw alarm payload from Kafka consumer.")
    demo_mode: bool = Field(default=False, description="When True, static playbooks are used instead of LLM.")

    # Populated by triage_node
    alarm: AlarmMetadata | None = Field(default=None)

    # Populated by rag_node
    rag_context: list[str] = Field(default_factory=list, description="Retrieved runbook snippets.")

    # Populated by strategy_node
    proposed_commands: list[str] = Field(default_factory=list, description="Ordered remediation commands.")

    # Populated by safety_node
    safety: SafetyResult | None = Field(default=None)

    # Runtime bookkeeping
    node_timings: dict[str, float] = Field(default_factory=dict, description="Per-node wall-clock seconds.")
    errors: list[str] = Field(default_factory=list, description="Non-fatal errors accumulated during execution.")

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Configuration (injected; defaults suitable for Docker Compose environment)
# ---------------------------------------------------------------------------


class CognitiveConfig(BaseModel):
    """Runtime configuration for cognitive nodes."""

    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    chroma_collection: str = "telcos_runbooks"
    rag_top_k: int = 5

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "llama3"
    ollama_timeout_s: float = 25.0  # keep headroom inside 30 s SLA

    # Blocked commands – deterministic list; never AI-delegated
    blocked_command_patterns: list[str] = Field(
        default_factory=lambda: [
            r"\breload\b",
            r"\bshutdown\b",
            r"\berase\b",
            r"\bformat\b",
        ]
    )
    power_threshold_pct: float = 20.0


_DEFAULT_CONFIG = CognitiveConfig()


# ---------------------------------------------------------------------------
# Static demo playbooks (demo_mode=True)
# ---------------------------------------------------------------------------

_DEMO_PLAYBOOKS: dict[str, list[str]] = {
    "link_down": [
        "show interface status",
        "show logging last 50",
        "clear counters GigabitEthernet0/0",
        "show ip ospf neighbor",
    ],
    "cpu_high": [
        "show processes cpu sorted",
        "show processes cpu history",
        "show platform resources",
    ],
    "memory_high": [
        "show processes memory sorted",
        "show platform resources",
    ],
    "bgp_session_down": [
        "show bgp summary",
        "show ip bgp neighbors",
        "clear ip bgp soft",
    ],
    "default": [
        "show version",
        "show logging last 100",
        "show platform health",
    ],
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed(start: float) -> float:
    return round(time.monotonic() - start, 4)


def _contains_blocked(command: str, patterns: list[str]) -> tuple[bool, str]:
    """
    Check *one* command string against all blocked patterns.

    Returns
    -------
    (True, matched_pattern)  if a blocked pattern is found.
    (False, "")              otherwise.
    """
    for pattern in patterns:
        if re.search(pattern, command, re.IGNORECASE):
            return True, pattern
    return False, ""


# ---------------------------------------------------------------------------
# Node 1 – triage_node
# ---------------------------------------------------------------------------


async def triage_node(state: GraphState, config: CognitiveConfig = _DEFAULT_CONFIG) -> GraphState:
    """
    Normalise the raw Kafka alarm payload into a canonical ``AlarmMetadata``
    schema.

    Responsibilities
    ----------------
    * Extract and coerce required fields (alarm_id, source_device, etc.).
    * Provide sensible defaults when optional fields are absent.
    * Preserve the original payload in ``raw_payload`` for audit purposes.
    * Append non-fatal warnings to ``state.errors`` without raising.

    Parameters
    ----------
    state:
        Current graph state.  Only ``state.raw_alarm`` is read.
    config:
        Cognitive configuration (unused in triage but accepted for consistency).

    Returns
    -------
    Updated ``GraphState`` with ``state.alarm`` populated.
    """
    t0 = time.monotonic()
    raw = state.raw_alarm

    logger.info(
        "triage_node: normalising alarm",
        extra={"alarm_id_raw": raw.get("alarm_id", "unknown")},
    )

    try:
        alarm_id: str = str(raw.get("alarm_id") or raw.get("id") or f"auto-{int(time.time())}")
        source_device: str = str(
            raw.get("source_device")
            or raw.get("device")
            or raw.get("host")
            or "unknown"
        )
        alarm_type: str = str(
            raw.get("alarm_type")
            or raw.get("type")
            or raw.get("event_type")
            or "unknown"
        ).lower().replace(" ", "_")

        severity_raw: str = str(
            raw.get("severity")
            or raw.get("priority")
            or "info"
        )

        # Timestamp normalisation – accept epoch int/float or ISO string
        ts_raw = raw.get("timestamp") or raw.get("event_time")
        if ts_raw is None:
            timestamp_utc = _utc_now_iso()
            state.errors.append("triage_node: missing timestamp; using server UTC time.")
        elif isinstance(ts_raw, (int, float)):
            timestamp_utc = datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat()
        else:
            timestamp_utc = str(ts_raw)

        alarm = AlarmMetadata(
            alarm_id=alarm_id,
            source_device=source_device,
            alarm_type=alarm_type,
            severity=severity_raw,
            timestamp_utc=timestamp_utc,
            raw_payload=raw,
        )
        state.alarm = alarm

        logger.info(
            "triage_node: alarm normalised",
            extra={
                "alarm_id": alarm.alarm_id,
                "alarm_type": alarm.alarm_type,
                "severity": alarm.severity,
                "source_device": alarm.source_device,
            },
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("triage_node: failed to normalise alarm", exc_info=exc)
        state.errors.append(f"triage_node: {exc}")

    finally:
        state.node_timings["triage_node"] = _elapsed(t0)

    return state


# ---------------------------------------------------------------------------
# Node 2 – rag_node
# ---------------------------------------------------------------------------


async def rag_node(state: GraphState, config: CognitiveConfig = _DEFAULT_CONFIG) -> GraphState:
    """
    Retrieve relevant runbook context from ChromaDB using the normalised alarm
    type and severity as query dimensions.

    Responsibilities
    ----------------
    * Build a semantic query string from ``state.alarm``.
    * Query the ChromaDB collection for the top-k nearest documents.
    * Populate ``state.rag_context`` with the retrieved text snippets.
    * Degrade gracefully when ChromaDB is unreachable.

    Parameters
    ----------
    state:
        Current graph state.  ``state.alarm`` must be populated.
    config:
        Cognitive configuration (ChromaDB endpoint and collection details).

    Returns
    -------
    Updated ``GraphState`` with ``state.rag_context`` populated.
    """
    t0 = time.monotonic()

    if state.alarm is None:
        logger.warning("rag_node: alarm metadata missing; skipping RAG retrieval.")
        state.errors.append("rag_node: alarm is None; skipping.")
        state.node_timings["rag_node"] = _elapsed(t0)
        return state

    alarm = state.alarm
    query = (
        f"alarm_type:{alarm.alarm_type} severity:{alarm.severity} "
        f"device:{alarm.source_device} remediation runbook"
    )

    logger.info(
        "rag_node: querying ChromaDB",
        extra={
            "collection": config.chroma_collection,
            "top_k": config.rag_top_k,
            "query_preview": query[:120],
        },
    )

    try:
        client = await ChromaAsyncHttpClient(
            host=config.chroma_host,
            port=config.chroma_port,
        )
        collection = await client.get_collection(name=config.chroma_collection)
        results = await collection.query(
            query_texts=[query],
            n_results=config.rag_top_k,
            include=["documents", "metadatas", "distances"],
        )

        # results["documents"] is a list[list[str]] (one inner list per query)
        docs: list[str] = results.get("documents", [[]])[0] or []
        state.rag_context = [d for d in docs if d]

        logger.info(
            "rag_node: retrieved documents",
            extra={"count": len(state.rag_context)},
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("rag_node: ChromaDB query failed; continuing without context.", exc_info=exc)
        state.errors.append(f"rag_node: {exc}")
        state.rag_context = []

    finally:
        state.node_timings["rag_node"] = _elapsed(t0)

    return state


# ---------------------------------------------------------------------------
# Node 3 – strategy_node
# ---------------------------------------------------------------------------


def _build_llm_prompt(alarm: AlarmMetadata, rag_context: list[str]) -> str:
    """
    Construct a structured prompt for Llama3 given the normalised alarm and
    retrieved runbook context.

    Returns
    -------
    A formatted prompt string.
    """
    context_block = "\n---\n".join(rag_context) if rag_context else "No runbook context available."
    return (
        "You are a senior NOC automation engineer for a Tier-1 CSP.\n"
        "Based ONLY on the alarm details and runbook context below, produce an ordered list "
        "of CLI remediation commands to execute on the affected network device.\n\n"
        "### Alarm\n"
        f"- ID        : {alarm.alarm_id}\n"
        f"- Device    : {alarm.source_device}\n"
        f"- Type      : {alarm.alarm_type}\n"
        f"- Severity  : {alarm.severity}\n"
        f"- Timestamp : {alarm.timestamp_utc}\n\n"
        "### Runbook Context\n"
        f"{context_block}\n\n"
        "### Instructions\n"
        "Return ONLY a JSON array of command strings.  No prose.  No markdown fences.\n"
        'Example: ["show version", "show logging last 50"]\n'
        "Commands must be read-only diagnostics or non-destructive corrective actions.\n"
        "NEVER include: reload, shutdown, erase, format."
    )


async def _call_ollama(prompt: str, config: CognitiveConfig) -> list[str]:
    """
    Invoke the Ollama REST API with Llama3 and parse the JSON command list.

    Parameters
    ----------
    prompt:
        Fully constructed prompt string.
    config:
        Cognitive configuration (Ollama URL, model, timeout).

    Returns
    -------
    Ordered list of remediation command strings.

    Raises
    ------
    httpx.HTTPError
        On transport or HTTP-level failure.
    ValueError
        When the model response cannot be parsed as a JSON list.
    """
    url = f"{config.ollama_base_url}/api/generate"
    payload = {
        "model": config.ollama_model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,   # near-deterministic for safety-critical ops
            "num_predict": 512,
        },
    }

    logger.debug("strategy_node: calling Ollama", extra={"model": config.ollama_model, "url": url})

    async with httpx.AsyncClient(timeout=config.ollama_timeout_s) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

    raw_text: str = body.get("response", "").strip()

    # Strip optional markdown fences defensively
    raw_text = re.sub(r"^```(?:json)?", "", raw_text, flags=re.MULTILINE).strip()
    raw_text = re.sub(r"```$", "", raw_text, flags=re.MULTILINE).strip()

    try:
        commands = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama response is not valid JSON: {raw_text!r}") from exc

    if not isinstance(commands, list):
        raise ValueError(f"Expected JSON array from Ollama, got: {type(commands)}")

    return [str(cmd) for cmd in commands if cmd]


async def strategy_node(state: GraphState, config: CognitiveConfig = _DEFAULT_CONFIG) -> GraphState:
    """
    Produce an ordered list of remediation commands.

    Behaviour
    ---------
    * **demo_mode=True** – Returns a static playbook keyed on ``alarm_type``.
      Falls back to the ``"default"`` playbook when the type is unrecognised.
    * **demo_mode=False** – Calls Llama3 through the Ollama REST API with a
      structured prompt composed from ``state.alarm`` and ``state.rag_context``.
      On LLM failure, the node degrades to the demo playbook and records the
      error in ``state.errors``.

    Parameters
    ----------
    state:
        Current graph state.  ``state.alarm`` must be populated.
    config:
        Cognitive configuration.

    Returns
    -------
    Updated ``GraphState`` with ``state.proposed_commands`` populated.
    """
    t0 = time.monotonic()

    if state.alarm is None:
        logger.warning("strategy_node: alarm metadata missing; cannot produce strategy.")
        state.errors.append("strategy_node: alarm is None; skipping.")
        state.node_timings["strategy_node"] = _elapsed(t0)
        return state

    alarm = state.alarm

    if state.demo_mode:
        # ------------------------------------------------------------------ #
        # Demo mode – static playbooks only                                   #
        # ------------------------------------------------------------------ #
        commands = _DEMO_PLAYBOOKS.get(alarm.alarm_type, _DEMO_PLAYBOOKS["default"])
        logger.info(
            "strategy_node: demo_mode=True; returning static playbook",
            extra={"alarm_type": alarm.alarm_type, "command_count": len(commands)},
        )
        state.proposed_commands = list(commands)

    else:
        # ------------------------------------------------------------------ #
        # Live mode – Llama3 via Ollama                                       #
        # ------------------------------------------------------------------ #
        prompt = _build_llm_prompt(alarm, state.rag_context)
        try:
            commands = await _call_ollama(prompt, config)
            logger.info(
                "strategy_node: LLM strategy generated",
                extra={"command_count": len(commands)},
            )
            state.proposed_commands = commands

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "strategy_node: Ollama call failed; falling back to demo playbook.",
                exc_info=exc,
            )
            state.errors.append(f"strategy_node (LLM fallback): {exc}")
            fallback = _DEMO_PLAYBOOKS.get(alarm.alarm_type, _DEMO_PLAYBOOKS["default"])
            state.proposed_commands = list(fallback)

    state.node_timings["strategy_node"] = _elapsed(t0)
    return state


# ---------------------------------------------------------------------------
# Node 4 – safety_node
# ---------------------------------------------------------------------------


async def safety_node(state: GraphState, config: CognitiveConfig = _DEFAULT_CONFIG) -> GraphState:
    """
    Deterministic safety gate – **never** delegated to any AI component.

    Rules evaluated (all must pass)
    --------------------------------
    1. No proposed command matches a blocked pattern
       (``reload``, ``shutdown``, ``erase``, ``format``).
    2. If a ``power_pct`` field is present in the raw alarm payload, it must be
       >= ``config.power_threshold_pct`` (default 20 %).

    The result is stored in ``state.safety`` as a ``SafetyResult``.  Downstream
    routing uses ``state.safety.is_safe`` to branch to either the executor node
    or ``blocked_node``.

    Parameters
    ----------
    state:
        Current graph state.
    config:
        Cognitive configuration (blocked patterns and power threshold).

    Returns
    -------
    Updated ``GraphState`` with ``state.safety`` populated.
    """
    t0 = time.monotonic()

    logger.info(
        "safety_node: evaluating proposed commands",
        extra={"command_count": len(state.proposed_commands)},
    )

    # ---------------------------------------------------------------------- #
    # Rule 1 – blocked command patterns                                       #
    # ---------------------------------------------------------------------- #
    for cmd in state.proposed_commands:
        matched, pattern = _contains_blocked(cmd, config.blocked_command_patterns)
        if matched:
            reason = (
                f"Command '{cmd}' matches blocked pattern '{pattern}'. "
                "Execution denied by deterministic safety gate."
            )
            logger.warning("safety_node: blocked command detected", extra={"command": cmd, "pattern": pattern})
            state.safety = SafetyResult(is_safe=False, reason=reason)
            state.node_timings["safety_node"] = _elapsed(t0)
            return state

    # ---------------------------------------------------------------------- #
    # Rule 2 – power threshold                                                #
    # ---------------------------------------------------------------------- #
    raw = state.raw_alarm
    power_pct_raw = raw.get("power_pct") or raw.get("power_percent") or raw.get("pwr_pct")
    if power_pct_raw is not None:
        try:
            power_pct = float(power_pct_raw)
        except (TypeError, ValueError):
            power_pct = None

        if power_pct is not None and power_pct < config.power_threshold_pct:
            reason = (
                f"Device power level {power_pct:.1f}% is below the minimum safe threshold "
                f"of {config.power_threshold_pct:.1f}%. Execution denied to prevent unsafe state."
            )
            logger.warning(
                "safety_node: power threshold violation",
                extra={"power_pct": power_pct, "threshold": config.power_threshold_pct},
            )
            state.safety = SafetyResult(is_safe=False, reason=reason)
            state.node_timings["safety_node"] = _elapsed(t0)
            return state

    # ---------------------------------------------------------------------- #
    # All rules passed                                                        #
    # ---------------------------------------------------------------------- #
    state.safety = SafetyResult(
        is_safe=True,
        reason="All deterministic safety checks passed.",
    )
    logger.info("safety_node: all checks passed; commands approved for execution.")
    state.node_timings["safety_node"] = _elapsed(t0)
    return state


# ---------------------------------------------------------------------------
# Node 5 – blocked_node
# ---------------------------------------------------------------------------


async def blocked_node(state: GraphState, config: CognitiveConfig = _DEFAULT_CONFIG) -> GraphState:
    """
    Terminal sink for command sets that did not pass the safety gate.

    Responsibilities
    ----------------
    * Emit a structured audit-log entry with full context for SIEM ingestion.
    * Clear ``state.proposed_commands`` to prevent accidental downstream use.
    * Record timing.

    This node does **not** raise; it is a safe terminal state.

    Parameters
    ----------
    state:
        Current graph state.  ``state.safety`` should be populated with the
        blocking reason.
    config:
        Cognitive configuration (unused; accepted for interface consistency).

    Returns
    -------
    Updated ``GraphState`` with proposed commands cleared.
    """
    t0 = time.monotonic()

    safety = state.safety
    reason = safety.reason if safety else "Safety result unavailable."
    alarm_id = state.alarm.alarm_id if state.alarm else "unknown"

    logger.error(
        "blocked_node: execution blocked by safety gate",
        extra={
            "alarm_id": alarm_id,
            "source_device": state.alarm.source_device if state.alarm else "unknown",
            "blocked_reason": reason,
            "proposed_commands": state.proposed_commands,
            "audit_timestamp_utc": _utc_now_iso(),
        },
    )

    # Sanitise state so no downstream node can accidentally execute the commands
    state.proposed_commands = []
    state.node_timings["blocked_node"] = _elapsed(t0)
    return state