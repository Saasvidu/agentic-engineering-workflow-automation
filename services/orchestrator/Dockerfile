FROM python:3.11-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy shared schema
COPY shared /app/shared

# Copy service files
COPY services/orchestrator /app

# Create virtual environment and install dependencies with uv
RUN uv venv .venv && \
    . .venv/bin/activate && \
    uv pip install -r requirements.txt

# Expose port
EXPOSE 8501

# Run Streamlit app using the virtual environment
CMD [".venv/bin/streamlit", "run", "streamlit_app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]


