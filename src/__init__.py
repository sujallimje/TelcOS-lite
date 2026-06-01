"""
TelcOS Lite – Level 3/4 Autonomous Operations Framework for CSPs.

Package: src

This is the top-level application package.  Sub-packages are organised
according to Clean Architecture layers:

    src/
    ├── api/          – Transport layer  (FastAPI routers, schemas)
    ├── core/         – Domain layer     (entities, use-cases, ports)
    ├── infra/        – Infrastructure   (Kafka, ChromaDB, Netmiko adapters)
    ├── agents/       – LangGraph agents (autonomous remediation graphs)
    └── config/       – Configuration    (settings, env loading)
"""