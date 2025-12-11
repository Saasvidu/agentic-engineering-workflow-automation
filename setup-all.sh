#!/bin/bash
# Setup script for all services using uv

set -e

echo "Setting up all services with uv..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Setup MCP Server
echo "📦 Setting up MCP Server..."
cd services/mcp-server
./setup.sh
cd ../..

# Setup Orchestrator
echo ""
echo "📦 Setting up Orchestrator..."
cd services/orchestrator
./setup.sh
cd ../..

# Setup FEA Worker
echo ""
echo "📦 Setting up FEA Worker..."
cd services/fea-worker
./setup.sh
cd ../..

echo ""
echo "✅ All services setup complete!"
echo ""
echo "To run services:"
echo "  Terminal 1 (MCP Server):"
echo "    cd services/mcp-server && source .venv/bin/activate && uvicorn mcp_server:app --reload"
echo ""
echo "  Terminal 2 (Orchestrator):"
echo "    cd services/orchestrator && source .venv/bin/activate && streamlit run streamlit_app.py"
echo ""
echo "  Terminal 3 (FEA Worker):"
echo "    cd services/fea-worker && source .venv/bin/activate && python fea_worker.py"

