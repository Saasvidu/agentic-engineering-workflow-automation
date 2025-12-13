#!/bin/bash
# Setup script for MCP Server service using uv

set -e

echo "Setting up MCP Server service..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create virtual environment and sync dependencies from pyproject.toml
echo "Creating virtual environment and installing dependencies..."
uv sync

echo "✅ MCP Server setup complete!"
echo ""
echo "To activate the virtual environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run the server:"
echo "  uvicorn mcp_server:app --reload"


