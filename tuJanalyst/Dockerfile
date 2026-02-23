# Stage 1: Install dependencies with uv
FROM python:3.11-slim AS builder

WORKDIR /build

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency definition and lockfile
COPY pyproject.toml uv.lock* ./

# Install dependencies into a virtual environment
RUN uv venv /opt/venv && \
    uv pip install --python /opt/venv/bin/python -r pyproject.toml

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime system dependencies (for pdfplumber/lxml)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY src/ /app/src/
COPY config/ /app/config/

# Create data directory for ChromaDB and downloads
RUN mkdir -p /app/data/chromadb /app/data/downloads

# Expose FastAPI port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
