# Setup script for all services using uv (PowerShell)

Write-Host "Setting up all services with uv..." -ForegroundColor Cyan
Write-Host ""

# Check if uv is installed
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: uv is not installed. Install it with: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"" -ForegroundColor Red
    exit 1
}

# Setup MCP Server
Write-Host "📦 Setting up MCP Server..." -ForegroundColor Yellow
Set-Location services\mcp-server
.\setup.ps1
Set-Location ..\..

# Setup Orchestrator
Write-Host ""
Write-Host "📦 Setting up Orchestrator..." -ForegroundColor Yellow
Set-Location services\orchestrator
.\setup.ps1
Set-Location ..\..

# Setup FEA Worker
Write-Host ""
Write-Host "📦 Setting up FEA Worker..." -ForegroundColor Yellow
Set-Location services\fea-worker
.\setup.ps1
Set-Location ..\..

Write-Host ""
Write-Host "✅ All services setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To run services:"
Write-Host "  Terminal 1 (MCP Server):"
Write-Host "    cd services\mcp-server && .\.venv\Scripts\Activate.ps1 && uvicorn mcp_server:app --reload"
Write-Host ""
Write-Host "  Terminal 2 (Orchestrator):"
Write-Host "    cd services\orchestrator && .\.venv\Scripts\Activate.ps1 && streamlit run streamlit_app.py"
Write-Host ""
Write-Host "  Terminal 3 (FEA Worker):"
Write-Host "    cd services\fea-worker && .\.venv\Scripts\Activate.ps1 && python fea_worker.py"

