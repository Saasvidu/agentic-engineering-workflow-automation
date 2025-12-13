# Setup script for Orchestrator service using uv (PowerShell)

Write-Host "Setting up Orchestrator service..." -ForegroundColor Cyan

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

Write-Host "✅ Orchestrator setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To activate the virtual environment:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "To run Streamlit UI:"
Write-Host "  streamlit run streamlit_app.py"
Write-Host ""
Write-Host "To run CLI version:"
Write-Host "  python orchestrator.py"


