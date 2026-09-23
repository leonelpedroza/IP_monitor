# Remove build artefacts (keeps .venv).
Set-Location -Path $PSScriptRoot
foreach ($d in @("build", "dist", ".pytest_cache", ".ruff_cache", ".mypy_cache", "src\ip_monitor.egg-info")) {
    if (Test-Path $d) { Remove-Item $d -Recurse -Force; Write-Host "removed $d" }
}
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Where-Object { $_.FullName -notmatch "\\.venv\\" } | Remove-Item -Recurse -Force
Write-Host "clean."
