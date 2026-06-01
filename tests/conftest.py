"""
Global Test Configuration and Stubbing.
========================================
Mocks compiled binary dependencies (chromadb, netmiko, aiokafka)
in sys.modules before any src components are loaded.
Also patches GraphState annotations at runtime to preserve _node_state.
"""

import sys
from typing import Any
from unittest.mock import MagicMock, AsyncMock


# Define actual exception classes to prevent TypeError in try/except blocks
class MockNetmikoBaseException(Exception):
    """Mock base exception for Netmiko."""
    pass


class MockNetmikoAuthenticationException(MockNetmikoBaseException):
    """Mock authentication exception for Netmiko."""
    pass


class MockNetmikoTimeoutException(MockNetmikoBaseException):
    """Mock timeout exception for Netmiko."""
    pass


class MockSSHException(Exception):
    """Mock SSH exception for Paramiko."""
    pass


class MockKafkaError(Exception):
    """Mock Kafka exception."""
    pass


# ---------------------------------------------------------------------------
# Mock Netmiko & Paramiko
# ---------------------------------------------------------------------------
netmiko_mock = MagicMock()
netmiko_mock.NetmikoAuthenticationException = MockNetmikoAuthenticationException
netmiko_mock.NetmikoTimeoutException = MockNetmikoTimeoutException
netmiko_mock.NetmikoBaseException = MockNetmikoBaseException
sys.modules['netmiko'] = netmiko_mock

netmiko_exceptions_mock = MagicMock()
netmiko_exceptions_mock.NetmikoBaseException = MockNetmikoBaseException
sys.modules['netmiko.exceptions'] = netmiko_exceptions_mock

paramiko_ssh_mock = MagicMock()
paramiko_ssh_mock.SSHException = MockSSHException
sys.modules['paramiko.ssh_exception'] = paramiko_ssh_mock
sys.modules['paramiko'] = MagicMock()


# ---------------------------------------------------------------------------
# Mock ChromaDB
# ---------------------------------------------------------------------------
chromadb_mock = MagicMock()

async def dummy_async_client(*args, **kwargs):
    """A dummy awaitable client that returns a mock collection for query checks."""
    mock_client = AsyncMock()
    mock_collection = AsyncMock()
    mock_collection.query.return_value = {
        "documents": [["rem-runbook-remediation-steps"]],
        "metadatas": [[{}]],
        "distances": [[0.0]],
    }
    mock_client.get_collection.return_value = mock_collection
    return mock_client

chromadb_mock.AsyncHttpClient = dummy_async_client
sys.modules['chromadb'] = chromadb_mock


# ---------------------------------------------------------------------------
# Mock AIOKafka
# ---------------------------------------------------------------------------
aiokafka_mock = MagicMock()
aiokafka_errors_mock = MagicMock()
aiokafka_errors_mock.KafkaError = MockKafkaError
sys.modules['aiokafka'] = aiokafka_mock
sys.modules['aiokafka.errors'] = aiokafka_errors_mock


# ---------------------------------------------------------------------------
# Inject _node_state into GraphState annotations to support StateGraph transfer
# ---------------------------------------------------------------------------
from src.cognitive.state import GraphState
GraphState.__annotations__["_node_state"] = Any
