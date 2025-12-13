FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy shared schema
COPY shared /app/shared

# Copy service files
COPY services/fea-worker /app

# Create virtual environment and install dependencies with uv
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt

# Run the worker using the virtual environment
CMD [".venv/bin/python", "fea_worker.py"]


