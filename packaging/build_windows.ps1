# Build a portable Windows GUI executable from the project virtual environment.
# Usage from project root: powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment missing. Run 'Start PDFManipulator.bat' once first."
}
& $python "packaging\create_icon.py"
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }
$arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",
    "--windowed",
    "--name", "PDFManipulator",
    "--icon", (Join-Path $root "packaging\pdf_manipulator.ico"),
    "--collect-data", "customtkinter",
    "--collect-all", "tkinterdnd2",
    "--collect-all", "pymupdf",
    "--hidden-import", "pypdf",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", "packaging",
    "launch.py"
)
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
$exe = Join-Path $root "dist\PDFManipulator.exe"
if (-not (Test-Path $exe)) { throw "Expected executable not found: $exe" }
Write-Output "Built: $exe"
Get-Item $exe | Select-Object Name,Length,LastWriteTime
