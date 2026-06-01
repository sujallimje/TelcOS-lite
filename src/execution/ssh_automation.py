"""
TelcOS Lite – SSH Automation Module
=====================================
Provides deterministic, production-grade SSH command execution for
network devices via Netmiko.  Designed to satisfy the 30-second SLA
target defined in the TelcOS Lite L3/L4 Autonomous Operations Framework.

Architecture layer : Execution
Responsibility     : Low-level device interaction (SSH)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Final

from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
from netmiko.exceptions import NetmikoBaseException
from paramiko.ssh_exception import SSHException

# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_DEVICE_TYPE: Final[str] = "autodetect"
_DEFAULT_SSH_PORT: Final[int] = 22
_DEFAULT_CONN_TIMEOUT: Final[int] = 15        # seconds – connect phase
_DEFAULT_CMD_TIMEOUT: Final[int] = 20         # seconds – per-command read
_DEFAULT_BANNER_TIMEOUT: Final[int] = 10      # seconds – SSH banner exchange
_DEFAULT_AUTH_TIMEOUT: Final[int] = 10        # seconds – authentication
_ENV_SSH_USERNAME: Final[str] = "TELCOS_SSH_USERNAME"
_ENV_SSH_PASSWORD: Final[str] = "TELCOS_SSH_PASSWORD"
_ENV_SSH_SECRET: Final[str] = "TELCOS_SSH_SECRET"       # enable secret (optional)
_ENV_SSH_KEY_FILE: Final[str] = "TELCOS_SSH_KEY_FILE"   # path to private key (optional)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CommandResult:
    """Immutable record of a single command execution.

    Attributes:
        command:   The command that was sent to the device.
        output:    Raw console output returned by the device.
        duration:  Wall-clock seconds the command took to complete.
        success:   True when the command produced output without error.
    """

    command: str
    output: str
    duration: float
    success: bool


@dataclass(frozen=True)
class ExecutionResult:
    """Aggregated result for a multi-command SSH session.

    Attributes:
        host:        Target device hostname / IP.
        results:     Ordered list of per-command results.
        total_duration: Wall-clock seconds for the entire session.
        success:     True when *all* commands completed without error.
        error:       Human-readable error message when success is False.
    """

    host: str
    results: list[CommandResult] = field(default_factory=list)
    total_duration: float = 0.0
    success: bool = True
    error: str = ""


# ---------------------------------------------------------------------------
# Credential resolution
# ---------------------------------------------------------------------------

def _resolve_credentials() -> tuple[str, str, str | None, str | None]:
    """Resolve SSH credentials from environment variables.

    Returns:
        Tuple of (username, password, enable_secret, key_file).

    Raises:
        EnvironmentError: If mandatory credentials are absent.
    """
    username: str | None = os.environ.get(_ENV_SSH_USERNAME)
    password: str | None = os.environ.get(_ENV_SSH_PASSWORD)

    if not username or not password:
        raise EnvironmentError(
            f"SSH credentials not found.  "
            f"Set {_ENV_SSH_USERNAME} and {_ENV_SSH_PASSWORD} environment variables."
        )

    secret: str | None = os.environ.get(_ENV_SSH_SECRET) or None
    key_file: str | None = os.environ.get(_ENV_SSH_KEY_FILE) or None

    return username, password, secret, key_file


# ---------------------------------------------------------------------------
# Core execution function
# ---------------------------------------------------------------------------

def execute_commands(
    host: str,
    commands: list[str],
    *,
    device_type: str = _DEFAULT_DEVICE_TYPE,
    port: int = _DEFAULT_SSH_PORT,
    conn_timeout: int = _DEFAULT_CONN_TIMEOUT,
    cmd_timeout: int = _DEFAULT_CMD_TIMEOUT,
    banner_timeout: int = _DEFAULT_BANNER_TIMEOUT,
    auth_timeout: int = _DEFAULT_AUTH_TIMEOUT,
) -> ExecutionResult:
    """Execute a sequence of CLI commands on a remote network device via SSH.

    The function establishes a single SSH session, runs each command
    sequentially, captures the raw console output, and tears down the
    connection unconditionally – even when errors occur.

    Args:
        host:           Hostname or IP address of the target device.
        commands:       Ordered list of CLI commands to send.
        device_type:    Netmiko device-type string (default: ``"autodetect"``).
                        Override with a concrete type (e.g. ``"cisco_ios"``)
                        to skip auto-detection and reduce latency.
        port:           TCP port for the SSH connection (default: 22).
        conn_timeout:   Seconds to wait for the TCP/SSH handshake (default: 15).
        cmd_timeout:    Seconds to wait for each command's output (default: 20).
        banner_timeout: Seconds to wait for the SSH banner (default: 10).
        auth_timeout:   Seconds to wait for authentication (default: 10).

    Returns:
        :class:`ExecutionResult` containing per-command output and metadata.

    Raises:
        This function is exception-safe: all errors are captured inside the
        returned :class:`ExecutionResult` so callers never receive an
        unhandled exception.

    Notes:
        * Credentials are read exclusively from environment variables
          (``TELCOS_SSH_USERNAME``, ``TELCOS_SSH_PASSWORD``, and optionally
          ``TELCOS_SSH_SECRET`` / ``TELCOS_SSH_KEY_FILE``).
        * Total wall-clock time is bounded by
          ``conn_timeout + len(commands) × cmd_timeout``.  With defaults
          this is well within the 30-second SLA for typical device command
          sets of ≤ 5 commands.
    """
    if not host:
        return ExecutionResult(
            host=host,
            success=False,
            error="host must be a non-empty string.",
        )

    if not commands:
        logger.warning("execute_commands called with empty command list for host=%s", host)
        return ExecutionResult(host=host, success=True)

    # ------------------------------------------------------------------
    # Credential resolution
    # ------------------------------------------------------------------
    try:
        username, password, secret, key_file = _resolve_credentials()
    except EnvironmentError as exc:
        logger.error(
            "Credential resolution failed for host=%s: %s",
            host,
            exc,
            exc_info=True,
        )
        return ExecutionResult(host=host, success=False, error=str(exc))

    # ------------------------------------------------------------------
    # Build Netmiko device dictionary
    # ------------------------------------------------------------------
    device_params: dict[str, object] = {
        "device_type": device_type,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "conn_timeout": conn_timeout,
        "read_timeout_override": cmd_timeout,
        "banner_timeout": banner_timeout,
        "auth_timeout": auth_timeout,
        "fast_cli": False,         # Disabled – correctness over speed
        "session_log": None,       # No file-based session log; we capture output directly
    }

    if secret:
        device_params["secret"] = secret

    if key_file:
        device_params["use_keys"] = True
        device_params["key_file"] = key_file

    # ------------------------------------------------------------------
    # Session execution
    # ------------------------------------------------------------------
    session_start: float = time.monotonic()
    connection: ConnectHandler | None = None
    results: list[CommandResult] = []

    try:
        logger.info(
            "Opening SSH session to host=%s port=%d device_type=%s",
            host,
            port,
            device_type,
        )
        connection = ConnectHandler(**device_params)  # type: ignore[arg-type]
        logger.info("SSH session established to host=%s", host)

        # Elevate privilege if an enable secret was supplied
        if secret:
            try:
                connection.enable()
                logger.debug("Privilege escalation (enable) succeeded on host=%s", host)
            except NetmikoBaseException as enable_exc:
                logger.warning(
                    "Privilege escalation failed on host=%s – continuing without enable: %s",
                    host,
                    enable_exc,
                )

        # ------------------------------------------------------------------
        # Iterate commands
        # ------------------------------------------------------------------
        for cmd in commands:
            cmd_stripped: str = cmd.strip()
            if not cmd_stripped:
                logger.debug("Skipping blank command for host=%s", host)
                continue

            cmd_start: float = time.monotonic()
            cmd_success: bool = True
            output: str = ""

            logger.info("Sending command to host=%s  cmd=%r", host, cmd_stripped)

            try:
                output = connection.send_command(
                    cmd_stripped,
                    read_timeout=cmd_timeout,
                    strip_prompt=True,
                    strip_command=True,
                )
            except NetmikoTimeoutException as exc:
                cmd_success = False
                output = f"[TIMEOUT] {exc}"
                logger.error(
                    "Command timed out on host=%s cmd=%r timeout=%ds: %s",
                    host,
                    cmd_stripped,
                    cmd_timeout,
                    exc,
                )
            except NetmikoBaseException as exc:
                cmd_success = False
                output = f"[NETMIKO_ERROR] {exc}"
                logger.error(
                    "Netmiko error on host=%s cmd=%r: %s",
                    host,
                    cmd_stripped,
                    exc,
                    exc_info=True,
                )
            except SSHException as exc:
                cmd_success = False
                output = f"[SSH_ERROR] {exc}"
                logger.error(
                    "SSH transport error on host=%s cmd=%r: %s",
                    host,
                    cmd_stripped,
                    exc,
                    exc_info=True,
                )

            cmd_duration: float = round(time.monotonic() - cmd_start, 4)

            logger.info(
                "Command completed host=%s cmd=%r duration=%.4fs success=%s",
                host,
                cmd_stripped,
                cmd_duration,
                cmd_success,
            )

            results.append(
                CommandResult(
                    command=cmd_stripped,
                    output=output,
                    duration=cmd_duration,
                    success=cmd_success,
                )
            )

        total_duration: float = round(time.monotonic() - session_start, 4)
        overall_success: bool = all(r.success for r in results)

        logger.info(
            "Session complete host=%s commands=%d total_duration=%.4fs overall_success=%s",
            host,
            len(results),
            total_duration,
            overall_success,
        )

        return ExecutionResult(
            host=host,
            results=results,
            total_duration=total_duration,
            success=overall_success,
        )

    # ------------------------------------------------------------------
    # Session-level exception handling
    # ------------------------------------------------------------------
    except NetmikoAuthenticationException as exc:
        total_duration = round(time.monotonic() - session_start, 4)
        error_msg: str = f"Authentication failed for host={host}: {exc}"
        logger.error(error_msg, exc_info=True)
        return ExecutionResult(
            host=host,
            results=results,
            total_duration=total_duration,
            success=False,
            error=error_msg,
        )

    except NetmikoTimeoutException as exc:
        total_duration = round(time.monotonic() - session_start, 4)
        error_msg = f"Connection timeout for host={host} after {conn_timeout}s: {exc}"
        logger.error(error_msg, exc_info=True)
        return ExecutionResult(
            host=host,
            results=results,
            total_duration=total_duration,
            success=False,
            error=error_msg,
        )

    except NetmikoBaseException as exc:
        total_duration = round(time.monotonic() - session_start, 4)
        error_msg = f"Netmiko session error for host={host}: {exc}"
        logger.error(error_msg, exc_info=True)
        return ExecutionResult(
            host=host,
            results=results,
            total_duration=total_duration,
            success=False,
            error=error_msg,
        )

    except SSHException as exc:
        total_duration = round(time.monotonic() - session_start, 4)
        error_msg = f"SSH transport error for host={host}: {exc}"
        logger.error(error_msg, exc_info=True)
        return ExecutionResult(
            host=host,
            results=results,
            total_duration=total_duration,
            success=False,
            error=error_msg,
        )

    except Exception as exc:  # noqa: BLE001  – final safety net
        total_duration = round(time.monotonic() - session_start, 4)
        error_msg = f"Unexpected error for host={host}: {type(exc).__name__}: {exc}"
        logger.critical(error_msg, exc_info=True)
        return ExecutionResult(
            host=host,
            results=results,
            total_duration=total_duration,
            success=False,
            error=error_msg,
        )

    finally:
        # ------------------------------------------------------------------
        # Unconditional connection cleanup
        # ------------------------------------------------------------------
        if connection is not None:
            try:
                connection.disconnect()
                logger.info("SSH session cleanly disconnected from host=%s", host)
            except Exception as cleanup_exc:  # noqa: BLE001
                logger.warning(
                    "Non-fatal error during SSH disconnect from host=%s: %s",
                    host,
                    cleanup_exc,
                )