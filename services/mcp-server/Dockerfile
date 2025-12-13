FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy shared schema
COPY shared /app/shared

# Copy service files
COPY services/mcp-server /app

# Create virtual environment and install dependencies with uv
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt

# Expose port
EXPOSE 8000

# Run the server using the virtual environment
CMD [".venv/bin/uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "8000"]


