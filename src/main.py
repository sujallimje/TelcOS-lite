"""
TelcOS Lite – Application Entrypoint.

Module: src.main

Responsibilities
----------------
* Bootstrap FastAPI with lifespan context (startup / shutdown hooks).
* Initialise structured logging via *structlog*.
* Load typed configuration from environment via *pydantic-settings*.
* Register the ``GET /health`` liveness probe.
* Reserve a background-task slot for the Kafka consumer (not yet wired).

SLA target: individual request p99 ≤ 30 seconds.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Set

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables.

    All fields have sensible defaults so the service starts in a local
    development environment without any additional setup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = Field(default="development", description="Runtime environment name.")
    app_name: str = Field(default="TelcOS Lite", description="Human-readable service name.")
    app_version: str = Field(default="0.1.0", description="Semantic version string.")
    log_level: str = Field(default="INFO", description="Minimum log level (DEBUG/INFO/WARNING/ERROR).")

    # Uvicorn / FastAPI
    host: str = Field(default="0.0.0.0", description="Bind host.")
    port: int = Field(default=8000, description="Bind port.")
    workers: int = Field(default=1, description="Number of Uvicorn worker processes.")

    # Kafka  (consumer wired in a later sprint)
    kafka_bootstrap_servers: str = Field(
        default="localhost:9092",
        description="Comma-separated Kafka bootstrap server addresses.",
    )
    kafka_consumer_group: str = Field(
        default="telcos-lite-cg",
        description="Kafka consumer group identifier.",
    )

    # ChromaDB
    chroma_host: str = Field(default="localhost", description="ChromaDB HTTP host.")
    chroma_port: int = Field(default=8001, description="ChromaDB HTTP port.")

    # Mock SSH Device (Netmiko)
    ssh_device_host: str = Field(default="localhost", description="Target SSH device host.")
    ssh_device_port: int = Field(default=2222, description="Target SSH device port.")
    ssh_device_user: str = Field(default="admin", description="SSH username.")
    ssh_device_password: str = Field(default="telcos123", description="SSH password.")

    # TMF621 ServiceNow Mock Endpoint
    tmf621_base_url: str = Field(
        default="http://localhost:8080",
        description="Downstream mock-ServiceNow integration base URL.",
    )


# Module-level singleton – imported by other modules via ``from src.main import settings``.
settings = Settings()


# ---------------------------------------------------------------------------
# WebSocket and Serialization helpers
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Manages active WebSocket connections for streaming real-time updates."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.active_connections.discard(connection)


manager = ConnectionManager()


def serialize_chunk(obj: Any) -> Any:
    """Recursively serialize objects, converting datetimes and Pydantic models to JSON-safe structures."""
    from datetime import datetime
    if isinstance(obj, dict):
        return {k: serialize_chunk(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_chunk(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, BaseModel):
        return obj.model_dump()
    elif hasattr(obj, "model_dump"):
        return obj.model_dump()
    elif hasattr(obj, "__dict__"):
        return {k: serialize_chunk(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    else:
        return obj


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


def _configure_logging(log_level: str) -> None:
    """Configure *structlog* with a JSON renderer suitable for production.

    In development environments the ``ConsoleRenderer`` provides human-readable
    colourised output; in all other environments a machine-parseable JSON
    renderer is used so log aggregation pipelines (e.g. ELK, Loki) can ingest
    records without further pre-processing.

    Args:
        log_level: Minimum log level string (e.g. ``"INFO"``).
    """
    stdlib_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure the standard-library root logger so that third-party libraries
    # (uvicorn, aiokafka, netmiko, …) also emit structured records.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=stdlib_level,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.app_env == "development":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(stdlib_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def _start_kafka_consumer() -> None:
    """Start the real Kafka consumer, listen to events, and run the LangGraph workflow."""
    import os
    import time
    import uuid
    from datetime import datetime, timezone
    from src.ingestion.kafka_consumer import TelemetryConsumer, ConsumerSettings
    from src.cognitive.graph import get_graph
    
    log = structlog.get_logger(__name__)
    log.info(
        "kafka_consumer_starting",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        consumer_group=settings.kafka_consumer_group,
    )
    
    # Configure SSH environment variables for execution
    os.environ["TELCOS_SSH_USERNAME"] = settings.ssh_device_user
    os.environ["TELCOS_SSH_PASSWORD"] = settings.ssh_device_password
    
    # Instantiate TelemetryConsumer settings
    consumer_settings = ConsumerSettings(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        auto_offset_reset="earliest",
    )
    
    consumer = TelemetryConsumer(settings=consumer_settings)
    
    try:
        await consumer.start()
        log.info("kafka_consumer_started")
        
        graph = get_graph()
        
        async for event in consumer.consume():
            t_start = time.monotonic()
            log.info("telemetry_event_received", event=event.model_dump())
            
            # Map TelemetryEvent to the LangGraph GraphState inputs
            raw_alarm = {
                "alarm_id": f"alarm-{event.alarm}-{int(time.time())}",
                "alarm_type": event.alarm,
                "device": event.asset,
                "source_device": event.asset,
                "ip": event.ip,
                "severity": "CRITICAL",  # standard default severity
                "timestamp": event.telemetry_timestamp.isoformat(),
                "power_pct": 50.0,      # default to avoid power threshold block
            }
            
            # We can also pass raw event context
            inputs = {
                "raw_event": {
                    "event_id": f"evt-{uuid.uuid4()}",
                    "source": "Kafka",
                    "category": "fault",
                    "severity": "CRITICAL",
                    "payload": raw_alarm,
                    "received_at": datetime.now(tz=timezone.utc).isoformat(),
                }
            }
            
            log.info("langgraph_execution_started", event_id=inputs["raw_event"]["event_id"])
            
            try:
                # Stream the state updates and broadcast them in real time
                async for chunk in graph.astream(inputs, stream_mode="updates"):
                    # Broadcast to WebSocket subscribers
                    serialized = serialize_chunk(chunk)
                    await manager.broadcast(serialized)
                    log.info("langgraph_state_update", chunk=serialized)
            except Exception as exc:
                log.exception("langgraph_execution_failed", error=str(exc))
                
            t_end = time.monotonic()
            execution_time = t_end - t_start
            
            log.info(
                "telemetry_event_processed",
                execution_time_seconds=execution_time,
                event_id=inputs["raw_event"]["event_id"],
            )
            
            # SLA target check: individual request <= 30 seconds
            if execution_time > 30.0:
                log.warning(
                    "sla_exceeded_warning",
                    message="Total execution time exceeded SLA target of 30 seconds",
                    execution_time_seconds=execution_time,
                    event_id=inputs["raw_event"]["event_id"],
                )
                
    except asyncio.CancelledError:
        log.info("kafka_consumer_loop_cancelled")
    except Exception as exc:
        log.exception("kafka_consumer_loop_error", error=str(exc))
    finally:
        await consumer.stop()
        log.info("kafka_consumer_stopped")


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager.

    Executes startup logic before yielding, and teardown logic after the
    ``yield`` when the application receives a shutdown signal.

    Args:
        app: The ``FastAPI`` application instance (provided by the framework).

    Yields:
        None – control is passed to FastAPI to serve requests.
    """
    log = structlog.get_logger(__name__)

    # --- Startup -----------------------------------------------------------
    _configure_logging(settings.log_level)

    log.info(
        "telcos_lite_starting",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        log_level=settings.log_level,
    )

    # Register background tasks.
    # Each task is wrapped in asyncio.create_task so that it runs concurrently
    # with the request-serving loop.  References are stored to allow graceful
    # cancellation on shutdown.
    kafka_task: asyncio.Task[None] = asyncio.create_task(
        _start_kafka_consumer(),
        name="kafka_consumer",
    )

    log.info("background_tasks_registered", tasks=["kafka_consumer"])

    yield  # ← FastAPI serves requests from here

    # --- Shutdown ----------------------------------------------------------
    log.info("telcos_lite_shutting_down")

    kafka_task.cancel()
    try:
        await kafka_task
    except asyncio.CancelledError:
        log.info("kafka_consumer_task_cancelled")

    log.info("telcos_lite_stopped")


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application instance.

    Returns:
        A fully configured ``FastAPI`` application ready to be served.
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Level 3/4 Autonomous Operations Framework for Communication Service Providers. "
            "Provides AI-driven fault detection, root-cause analysis, and automated remediation."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Health endpoint
    # ------------------------------------------------------------------

    @app.get(
        "/health",
        summary="Liveness probe",
        response_description="Service health status.",
        tags=["observability"],
    )
    async def health_check() -> JSONResponse:
        """Return a minimal liveness response consumed by Docker / Kubernetes probes.

        Returns:
            JSON body ``{"status": "healthy"}`` with HTTP 200.
        """
        return JSONResponse(content={"status": "healthy"})

    # ------------------------------------------------------------------
    # WebSocket streaming endpoint
    # ------------------------------------------------------------------

    @app.websocket("/api/v1/demo/stream")
    async def websocket_stream(websocket: WebSocket):
        """Websocket endpoint to stream graph state updates in real time."""
        log = structlog.get_logger(__name__)
        log.info("websocket_client_connecting")
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            log.info("websocket_client_disconnected")
        except Exception as exc:
            log.warning("websocket_client_error", error=str(exc))
        finally:
            manager.disconnect(websocket)

    return app


# ---------------------------------------------------------------------------
# Module-level application instance
# ---------------------------------------------------------------------------

# Exposed at module scope so that Uvicorn can locate it via
# ``uvicorn src.main:app`` and so that test fixtures can import it directly.
app: FastAPI = create_app()


# ---------------------------------------------------------------------------
# Development entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        log_level=settings.log_level.lower(),
        reload=settings.app_env == "development",
    )