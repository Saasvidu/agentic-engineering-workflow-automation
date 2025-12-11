# Setup script for MCP Server service using uv (PowerShell)

Write-Host "Setting up MCP Server service..." -ForegroundColor Cyan

# Check if uv is installed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: uv is not installed. Install it with: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Red
    exit 1
}

# Create virtual environment
Write-Host "Creating virtual environment..." -ForegroundColor Yellow
uv venv

# Activate virtual environment and install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt

Write-Host "✅ MCP Server setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To activate the virtual environment:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "To run the server:"
Write-Host "  uvicorn mcp_server:app --reload"

