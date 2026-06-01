"""
Tests for the LangGraph Topology and Routing Logic.
===================================================
Tests the deterministic router (_route_after_safety), graph compilation,
and execution flow along the safe and unsafe/blocked branches.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.cognitive.graph import (
    build_graph,
    get_graph,
    _route_after_safety,
    NODE_TRIAGE,
    NODE_STRATEGY,
    NODE_SAFETY,
    NODE_EXECUTE,
    NODE_TMF621,
    NODE_BLOCKED,
)
from src.cognitive.state import GraphState
from src.execution.ssh_automation import ExecutionResult, CommandResult


def run_async(coro):
    """Helper to run async coroutines in a synchronous test."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

def test_route_after_safety_safe() -> None:
    """Test that verdict='safe' routes to the safe path."""
    state: GraphState = {
        "safety_evaluation": {
            "verdict": "safe",
            "violated_policies": [],
            "risk_score": 0,
            "evaluated_at": "2026-06-01T12:00:00Z",
            "evaluator_version": "1.0.0",
        }
    }
    route = _route_after_safety(state)
    assert route == "safe"


def test_route_after_safety_unsafe() -> None:
    """Test that verdict='unsafe' routes to the unsafe path."""
    state: GraphState = {
        "safety_evaluation": {
            "verdict": "unsafe",
            "violated_policies": ["BLOCKED_COMMAND"],
            "risk_score": 100,
            "evaluated_at": "2026-06-01T12:00:00Z",
            "evaluator_version": "1.0.0",
        }
    }
    route = _route_after_safety(state)
    assert route == "unsafe"


def test_route_after_safety_missing_or_malformed() -> None:
    """Test fail-closed behavior: missing or malformed verdict routes to unsafe."""
    # Missing safety_evaluation completely
    state_empty: GraphState = {}
    assert _route_after_safety(state_empty) == "unsafe"

    # Missing verdict key
    state_no_verdict: GraphState = {"safety_evaluation": {}}  # type: ignore[typeddict-item]
    assert _route_after_safety(state_no_verdict) == "unsafe"

    # Malformed verdict value
    state_malformed: GraphState = {
        "safety_evaluation": {
            "verdict": "some-random-value",  # type: ignore[typeddict-item]
            "violated_policies": [],
            "risk_score": 0,
            "evaluated_at": "",
            "evaluator_version": "",
        }
    }
    assert _route_after_safety(state_malformed) == "unsafe"


# ---------------------------------------------------------------------------
# Graph compilation tests
# ---------------------------------------------------------------------------

def test_graph_compilation() -> None:
    """Test that the graph builds and compiles without errors."""
    compiled_graph = build_graph()
    assert compiled_graph is not None
    
    # Verify singleton getter
    singleton_graph = get_graph()
    assert singleton_graph is not None


# ---------------------------------------------------------------------------
# Graph Execution End-to-End simulation tests (with Mocks)
# ---------------------------------------------------------------------------

@patch("src.cognitive.graph.execute_commands")
@patch("src.cognitive.graph.TMF621Client")
def test_graph_execution_safe_path(mock_tmf_client_class: MagicMock, mock_execute: MagicMock) -> None:
    """Simulates graph execution for a safe event, verifying all nodes are called."""
    # Configure SSH executor mock
    mock_execute.return_value = ExecutionResult(
        host="10.0.0.1",
        results=[CommandResult(command="show version", output="Cisco IOS mock", duration=0.01, success=True)],
        total_duration=0.01,
        success=True,
    )

    # Configure TMF621 client mock
    mock_client_instance = AsyncMock()
    mock_client_instance.post_ticket.return_value = {"id": "mock-tmf-ticket-id-999"}
    mock_tmf_client_class.return_value.__aenter__.return_value = mock_client_instance

    compiled_graph = build_graph()

    # Construct safe event payload inputs
    inputs = {
        "raw_event": {
            "event_id": "evt-123",
            "source": "Kafka",
            "category": "fault",
            "severity": "CRITICAL",
            "payload": {
                "alarm_id": "alarm-bgp-123",
                "alarm_type": "link_down",
                "device": "core-router-01",
                "ip": "10.0.0.1",
                "severity": "CRITICAL",
                "timestamp": "2026-06-01T12:00:00Z",
                "power_pct": 80.0,
                "demo_mode": True,  # Ensures we use static playbook instead of Ollama
            },
            "received_at": "2026-06-01T12:00:01Z",
        }
    }

    # Run the graph
    result = run_async(compiled_graph.ainvoke(inputs))

    # Verify state updates
    assert result.get("retrieved_context") is not None
    assert result.get("proposed_commands") is not None
    assert result.get("safety_evaluation") is not None
    assert result["safety_evaluation"]["verdict"] == "safe"
    assert result.get("execution_output") is not None
    assert result["execution_output"]["success"] is True
    assert result["tmf_ticket_id"] == "mock-tmf-ticket-id-999"


@patch("src.cognitive.graph.execute_commands")
@patch("src.cognitive.graph.TMF621Client")
def test_graph_execution_unsafe_path(mock_tmf_client_class: MagicMock, mock_execute: MagicMock) -> None:
    """Simulates graph execution for an unsafe event, verifying routing to BLOCKED node."""
    compiled_graph = build_graph()

    # Construct unsafe event payload inputs (low power levels violate safety threshold of 20%)
    inputs = {
        "raw_event": {
            "event_id": "evt-456",
            "source": "Kafka",
            "category": "fault",
            "severity": "CRITICAL",
            "payload": {
                "alarm_id": "alarm-cpu-456",
                "alarm_type": "cpu_high",
                "device": "core-router-01",
                "ip": "10.0.0.1",
                "severity": "CRITICAL",
                "timestamp": "2026-06-01T12:00:00Z",
                "power_pct": 5.0,  # Unsafe power level!
                "demo_mode": True,
            },
            "received_at": "2026-06-01T12:00:01Z",
        }
    }

    # Run the graph
    result = run_async(compiled_graph.ainvoke(inputs))

    # Verify safety is unsafe
    assert result.get("safety_evaluation") is not None
    assert result["safety_evaluation"]["verdict"] == "unsafe"
    
    # Proposed commands must be cleared in the internal _node_state Pydantic model by the BLOCKED node
    assert result.get("_node_state") is not None
    assert result["_node_state"].proposed_commands == []
    
    # Outer state dictionary remains unchanged due to wrapped_blocked wrapper behavior
    assert result.get("proposed_commands") == {
        "commands": ["show processes cpu sorted", "show processes cpu history", "show platform resources"],
        "target_devices": ["core-router-01"],
        "rollback_commands": [],
        "rationale": "Generated via strategy node",
    }

    # Verify execution node and ticketing nodes are NOT called (outputs should be empty/None)
    assert result.get("execution_output") is None
    assert result.get("tmf_ticket_id") is None
    
    # Assert SSH execution and TMF621 client POST were never triggered
    mock_execute.assert_not_called()
    mock_client_instance = mock_tmf_client_class.return_value.__aenter__.return_value
    mock_client_instance.post_ticket.assert_not_called()
