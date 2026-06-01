# ============================================================
# TelcOS Lite – Dockerfile
# Base: Python 3.11 Slim
# ============================================================

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
# build-essential, g++, and python3-dev are needed to compile chromadb's hnswlib dependency
# curl is needed for healthcheck probes
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install Python packages
RUN pip install -r requirements.txt

# Copy source code
COPY src/ ./src/

# Expose port
EXPOSE 8000

# Run the FastAPI application via python main entrypoint
CMD ["python", "-m", "src.main"]
