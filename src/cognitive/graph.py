"""
src/cognitive/graph.py
----------------------
Assembles and compiles the TelcOS Lite LangGraph topology.

Topology
--------

    START
      └─► TRIAGE          (RAG retrieval + event classification)
            └─► STRATEGY  (LLM-driven remediation planning)
                  └─► SAFETY  (deterministic policy evaluation)
                        ├─[safe]──► EXECUTE   (Netmiko device execution)
                        │               └─► TMF621  (trouble-ticket creation)
                        │                       └─► END
                        └─[unsafe]─► BLOCKED  (audit log + suppression)
                                        └─► END

Routing invariant
-----------------
The SAFETY → {EXECUTE | BLOCKED} conditional edge is the *only* place
where the graph branches.  It reads ``state["safety_evaluation"]["verdict"]``
which is always either the literal string ``"safe"`` or ``"unsafe"``.
The routing function is a pure deterministic Python function – no LLM
inference is involved at this decision point (Rule 15).

Node stubs
----------
Node callables are imported from their respective modules.  This file
only wires the topology; node implementations live elsewhere (Rule 11).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from src.cognitive.state import GraphState
from src.cognitive.nodes import (
    GraphState as NodeGraphState,
    triage_node,
    rag_node,
    strategy_node,
    safety_node,
    blocked_node,
)
from src.execution.ssh_automation import execute_commands
from src.federation.mapper import GraphState as MapperGraphState, TMF621Mapper
from src.federation.client import TMF621Client

# --------------------------------------------------------------------------- #
# Structured logger                                                            #
# --------------------------------------------------------------------------- #

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Node name constants – used as single source of truth for edge declarations  #
# --------------------------------------------------------------------------- #

NODE_TRIAGE: Literal["TRIAGE"] = "TRIAGE"
NODE_STRATEGY: Literal["STRATEGY"] = "STRATEGY"
NODE_SAFETY: Literal["SAFETY"] = "SAFETY"
NODE_EXECUTE: Literal["EXECUTE"] = "EXECUTE"
NODE_TMF621: Literal["TMF621"] = "TMF621"
NODE_BLOCKED: Literal["BLOCKED"] = "BLOCKED"

# Routing output literals consumed by add_conditional_edges
_ROUTE_SAFE: Literal["safe"] = "safe"
_ROUTE_UNSAFE: Literal["unsafe"] = "unsafe"

# --------------------------------------------------------------------------- #
# Node Implementations / Wrappers                                              #
# --------------------------------------------------------------------------- #

async def wrapped_triage(state: GraphState) -> GraphState:
    raw_event = state.get("raw_event") or {}
    raw_alarm = raw_event.get("payload") or {}
    demo_mode = raw_event.get("payload", {}).get("demo_mode", False)
    
    node_state = NodeGraphState(
        raw_alarm=raw_alarm,
        demo_mode=demo_mode
    )
    
    node_state = await triage_node(node_state)
    node_state = await rag_node(node_state)
    
    runbooks = [{"text": doc} for doc in node_state.rag_context]
    
    return {
        **state,
        "retrieved_context": {
            "runbooks": runbooks,
            "topology": {},
            "historical_incidents": [],
            "retrieval_latency_ms": node_state.node_timings.get("rag_node", 0.0) * 1000.0,
        },
        "_node_state": node_state,
    }


async def wrapped_strategy(state: GraphState) -> GraphState:
    node_state = state.get("_node_state")
    if node_state is None:
        raw_event = state.get("raw_event") or {}
        raw_alarm = raw_event.get("payload") or {}
        node_state = NodeGraphState(raw_alarm=raw_alarm)
        
    node_state = await strategy_node(node_state)
    
    return {
        **state,
        "proposed_commands": {
            "commands": node_state.proposed_commands,
            "target_devices": [node_state.alarm.source_device] if node_state.alarm else [],
            "rollback_commands": [],
            "rationale": "Generated via strategy node",
        },
        "_node_state": node_state,
    }


async def wrapped_safety(state: GraphState) -> GraphState:
    node_state = state.get("_node_state")
    if node_state is None:
        raw_event = state.get("raw_event") or {}
        raw_alarm = raw_event.get("payload") or {}
        node_state = NodeGraphState(raw_alarm=raw_alarm)
        
    node_state = await safety_node(node_state)
    
    is_safe = node_state.safety.is_safe if node_state.safety else False
    verdict = "safe" if is_safe else "unsafe"
    reason = node_state.safety.reason if node_state.safety else "Unknown safety reason"
    
    return {
        **state,
        "safety_evaluation": {
            "verdict": verdict,
            "violated_policies": [] if is_safe else [reason],
            "risk_score": 0 if is_safe else 100,
            "evaluated_at": datetime.now(tz=timezone.utc).isoformat(),
            "evaluator_version": "1.0.0",
        },
        "_node_state": node_state,
    }


async def wrapped_blocked(state: GraphState) -> GraphState:
    node_state = state.get("_node_state")
    if node_state is not None:
        node_state = await blocked_node(node_state)
    return state


async def wrapped_execute(state: GraphState) -> GraphState:
    node_state = state.get("_node_state")
    if node_state is None:
        return state
        
    commands = node_state.proposed_commands
    
    from src.main import settings
    
    host = settings.ssh_device_host
    port = settings.ssh_device_port
    
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: execute_commands(
            host=host,
            commands=commands,
            port=port,
            device_type="cisco_ios",
        )
    )
    
    success = result.success
    device_responses = {host: "\n".join([f"{r.command}: {r.output}" for r in result.results])}
    
    execution_output = {
        "device_responses": device_responses,
        "success": success,
        "failed_devices": [] if success else [host],
        "execution_latency_ms": result.total_duration * 1000.0,
        "rollback_triggered": False,
    }
    
    return {
        **state,
        "execution_output": execution_output,
        "_node_state": node_state,
    }


async def wrapped_tmf621(state: GraphState) -> GraphState:
    node_state = state.get("_node_state")
    if node_state is None or node_state.alarm is None:
        return state
        
    exec_output = state.get("execution_output") or {}
    success = exec_output.get("success", False)
    resolution_status = "RESOLVED" if success else "FAILED"
    
    device_responses = exec_output.get("device_responses") or {}
    notes_list = []
    for host, output in device_responses.items():
        notes_list.append(f"Device: {host}\nOutput:\n{output}")
    notes = "\n".join(notes_list) if notes_list else "No execution output."
    
    mapper_state = MapperGraphState(
        incident_id=node_state.alarm.alarm_id,
        alarm_type=node_state.alarm.alarm_type.upper(),
        alarm_severity=node_state.alarm.severity,
        alarm_description=f"Auto-remediation for alarm {node_state.alarm.alarm_type}",
        asset_name=node_state.alarm.source_device,
        device_ip=node_state.raw_alarm.get("ip", "127.0.0.1"),
        resolution_status=resolution_status,
        resolution_notes=notes,
    )
    
    mapper = TMF621Mapper()
    payload = mapper.map(mapper_state)
    
    from src.main import settings
    base_url = getattr(settings, "tmf621_base_url", "http://localhost:8080")
    
    ticket_id = None
    try:
        async with TMF621Client(base_url=base_url) as client:
            response = await client.post_ticket(payload)
            ticket_id = response.get("id") or payload.id
    except Exception as exc:
        logger.exception("tmf621_post_failed", extra={"error": str(exc)})
        ticket_id = f"error-unsent-{payload.id}"
        
    return {
        **state,
        "tmf_ticket_id": ticket_id,
        "_node_state": node_state,
    }


# --------------------------------------------------------------------------- #
# Deterministic routing function (Rule 15 – safety layer must be deterministic)#
# --------------------------------------------------------------------------- #


def _route_after_safety(
    state: GraphState,
) -> Literal["safe", "unsafe"]:
    """
    Pure deterministic router executed after the SAFETY node.

    Reads the ``verdict`` field from ``safety_evaluation`` and maps it to
    the appropriate downstream branch.  Any missing or malformed verdict is
    treated as ``"unsafe"`` to preserve the fail-safe posture of the system.

    Parameters
    ----------
    state:
        Current pipeline state after SAFETY node execution.

    Returns
    -------
    Literal["safe", "unsafe"]
        Edge label consumed by LangGraph's conditional routing.
    """
    safety_eval = state.get("safety_evaluation") or {}
    verdict: str = safety_eval.get("verdict", "unsafe")

    if verdict == _ROUTE_SAFE:
        logger.info(
            "safety_routing",
            extra={
                "verdict": verdict,
                "risk_score": safety_eval.get("risk_score"),
                "event_id": (state.get("raw_event") or {}).get("event_id"),
            },
        )
        return _ROUTE_SAFE

    # Treat anything that is not explicitly "safe" as unsafe (fail-closed).
    logger.warning(
        "safety_routing_blocked",
        extra={
            "verdict": verdict,
            "violated_policies": safety_eval.get("violated_policies", []),
            "risk_score": safety_eval.get("risk_score"),
            "event_id": (state.get("raw_event") or {}).get("event_id"),
        },
    )
    return _ROUTE_UNSAFE


# --------------------------------------------------------------------------- #
# Graph factory                                                                #
# --------------------------------------------------------------------------- #


def build_graph() -> StateGraph:
    """
    Construct and return a *compiled* TelcOS Lite cognitive pipeline graph.

    The compiled graph is a ``CompiledGraph`` (LangGraph internal type) that
    exposes ``.invoke()``, ``.stream()``, and async equivalents.  Callers
    should treat the return value as opaque and interact with it only through
    the LangGraph public API.

    Returns
    -------
    StateGraph
        Compiled LangGraph instance ready for invocation.

    Raises
    ------
    RuntimeError
        If graph compilation fails due to topology misconfiguration.

    Examples
    --------
    >>> graph = build_graph()
    >>> result = graph.invoke({"raw_event": {...}})
    """
    logger.info("telcos_graph_build_start")

    builder: StateGraph = StateGraph(GraphState)

    # ------------------------------------------------------------------ #
    # Register nodes                                                       #
    # ------------------------------------------------------------------ #
    builder.add_node(NODE_TRIAGE, wrapped_triage)
    builder.add_node(NODE_STRATEGY, wrapped_strategy)
    builder.add_node(NODE_SAFETY, wrapped_safety)
    builder.add_node(NODE_EXECUTE, wrapped_execute)
    builder.add_node(NODE_TMF621, wrapped_tmf621)
    builder.add_node(NODE_BLOCKED, wrapped_blocked)

    # ------------------------------------------------------------------ #
    # Linear edges                                                         #
    # ------------------------------------------------------------------ #
    builder.add_edge(START, NODE_TRIAGE)
    builder.add_edge(NODE_TRIAGE, NODE_STRATEGY)
    builder.add_edge(NODE_STRATEGY, NODE_SAFETY)

    # ------------------------------------------------------------------ #
    # Conditional edge: SAFETY → {EXECUTE | BLOCKED}                      #
    # ------------------------------------------------------------------ #
    builder.add_conditional_edges(
        NODE_SAFETY,
        _route_after_safety,
        {
            _ROUTE_SAFE: NODE_EXECUTE,
            _ROUTE_UNSAFE: NODE_BLOCKED,
        },
    )

    # ------------------------------------------------------------------ #
    # Terminal edges for the safe path                                     #
    # ------------------------------------------------------------------ #
    builder.add_edge(NODE_EXECUTE, NODE_TMF621)
    builder.add_edge(NODE_TMF621, END)

    # ------------------------------------------------------------------ #
    # Terminal edge for the unsafe / blocked path                          #
    # ------------------------------------------------------------------ #
    builder.add_edge(NODE_BLOCKED, END)

    # ------------------------------------------------------------------ #
    # Compile                                                              #
    # ------------------------------------------------------------------ #
    try:
        compiled = builder.compile()
    except Exception as exc:  # noqa: BLE001
        logger.exception("telcos_graph_compile_failed", extra={"error": str(exc)})
        raise RuntimeError(f"Failed to compile TelcOS Lite cognitive graph: {exc}") from exc

    logger.info("telcos_graph_build_complete")
    return compiled


# --------------------------------------------------------------------------- #
# Module-level singleton (lazy import pattern for application startup)        #
# --------------------------------------------------------------------------- #

_compiled_graph: StateGraph | None = None


def get_graph() -> StateGraph:
    """
    Return the module-level compiled graph singleton.

    The graph is built exactly once on first call and reused thereafter,
    avoiding repeated compilation overhead at request time.

    Returns
    -------
    StateGraph
        Compiled LangGraph instance.
    """
    global _compiled_graph  # noqa: PLW0603
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph