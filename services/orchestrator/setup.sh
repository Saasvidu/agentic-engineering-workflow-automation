#!/bin/bash
# Setup script for Orchestrator service using uv

set -e

echo "Setting up Orchestrator service..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment..."
uv venv

# Activate virtual environment and install dependencies
echo "Installing dependencies..."
source .venv/bin/activate
uv pip install -r requirements.txt

echo "✅ Orchestrator setup complete!"
echo ""
echo "To activate the virtual environment:"
echo "  source .venv/bin/activate"
echo ""
echo "To run Streamlit UI:"
echo "  streamlit run streamlit_app.py"
echo ""
echo "To run CLI version:"
echo "  python orchestrator.py"

