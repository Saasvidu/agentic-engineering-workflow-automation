FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy shared schema
COPY shared /app/shared

# Copy service files
COPY services/fea-worker /app

# Create virtual environment and sync dependencies from pyproject.toml
RUN uv sync

# Run the worker using the virtual environment
CMD [".venv/bin/python", "fea_worker.py"]


