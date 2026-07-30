param(
    [string]$Python = "python",
    [string]$ComponentsDir = "",
    [string]$LocalKbWindowsRoot = "",
    [string]$BuildVenv = "",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$WebSource = Split-Path $Root -Parent
if (-not $ComponentsDir) { $ComponentsDir = Join-Path $WebSource "localkb\tool_kylin_x86\offline_components" }
if (-not $LocalKbWindowsRoot) { $LocalKbWindowsRoot = Join-Path $WebSource "localkb\tool" }
if (-not $BuildVenv) { $BuildVenv = Join-Path $Root ".build-venv-windows" }
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"
$Cache = Join-Path $Root ".build-cache"
$TableModel = if ($env:DOCUMENT_OCR_TABLE_MODEL) { $env:DOCUMENT_OCR_TABLE_MODEL } else { Join-Path $Cache "slanet-plus.onnx" }
$PackageRoot = Join-Path $Root "dist\文档OCR助手-windows-x86_64"
$PyiDist = Join-Path $Root "build\windows\pyi-dist"
$PyiWork = Join-Path $Root "build\windows\pyi-work"

if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x86_64 构建需要 64 位系统。" }
if (-not (Test-Path $ComponentsDir)) { throw "找不到 LocalKB 离线组件：$ComponentsDir" }
if (-not (Test-Path $LocalKbWindowsRoot)) { throw "找不到 LocalKB Windows 实现：$LocalKbWindowsRoot" }
if (-not (Test-Path $VenvPython)) { & $Python -m venv $BuildVenv }
if ($LASTEXITCODE) { throw "无法创建 Windows 构建环境。" }

if (-not $SkipDependencyInstall) {
    & $VenvPython -m pip install --upgrade pip wheel setuptools
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-windows.txt") -r (Join-Path $Root "requirements-table.txt")
    & $VenvPython -m pip install "pyinstaller==6.18.0" "pyinstaller-hooks-contrib==2026.0" "pytest>=7.4,<9"
}

New-Item -ItemType Directory -Force $Cache | Out-Null
if (-not (Test-Path $TableModel)) { & $VenvPython (Join-Path $Root "scripts\fetch_table_model.py") $TableModel }
& $VenvPython (Join-Path $Root "scripts\create_windows_icon.py") (Join-Path $Root "assets\app-icon.svg") (Join-Path $Root "assets\app-icon.ico")

Remove-Item -LiteralPath $PyiDist,$PyiWork,$PackageRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $PyiDist,$PyiWork,$PackageRoot,(Join-Path $PackageRoot "app"),(Join-Path $PackageRoot "assets") | Out-Null
& $VenvPython -m PyInstaller --noconfirm --clean --distpath $PyiDist --workpath $PyiWork (Join-Path $Root "packaging\document_ocr_assistant_windows.spec")
if ($LASTEXITCODE) { throw "PyInstaller Windows 构建失败。" }

$BuiltApp = Join-Path $PyiDist "文档OCR助手"
Copy-Item -Path (Join-Path $BuiltApp "*") -Destination (Join-Path $PackageRoot "app") -Recurse -Force
Copy-Item (Join-Path $Root "assets\app-icon.svg") (Join-Path $PackageRoot "assets\app-icon.svg")
Copy-Item (Join-Path $Root "assets\app-icon.ico") (Join-Path $PackageRoot "assets\app-icon.ico")
Copy-Item (Join-Path $Root "packaging\启动文档OCR助手.bat") (Join-Path $PackageRoot "启动文档OCR助手.bat")

& $VenvPython (Join-Path $Root "scripts\prepare_windows_runtime.py") `
    --components-dir $ComponentsDir `
    --localkb-windows-root $LocalKbWindowsRoot `
    --output-root $PackageRoot `
    --table-model $TableModel

@"
文档OCR助手 Windows x86_64 版

运行：双击“启动文档OCR助手.bat”或 app\文档OCR助手.exe。
Office 文档：自动调用本机 Microsoft Word 或 WPS Office；本包不包含 LibreOffice。
OCR 与表格识别：PP-OCRv6 Medium + SLANet-plus，全部使用 ONNX Runtime 离线运行。
支持图片、PDF、DOC/DOCX/WPS、文件夹及 ZIP/RAR/7Z/TAR/TAR.GZ/TGZ。
批量识别可勾选“复制未转换文件”（默认关闭），将目录或压缩包内其他文件按原层级复制到新批次目录。
关闭主窗口时默认询问缩小到右下角或退出；可选择记住，并可在设置页修改。
"@ | Set-Content -LiteralPath (Join-Path $PackageRoot "使用说明.txt") -Encoding UTF8

$SmokeScreenshot = Join-Path $Root "build\windows\windows-ui-smoke.png"
$env:DOCUMENT_OCR_UI_SMOKE_SCREENSHOT = $SmokeScreenshot
$process = Start-Process -FilePath (Join-Path $PackageRoot "app\文档OCR助手.exe") -Wait -PassThru
Remove-Item Env:\DOCUMENT_OCR_UI_SMOKE_SCREENSHOT -ErrorAction SilentlyContinue
if ($process.ExitCode -ne 0 -or -not (Test-Path $SmokeScreenshot)) { throw "Windows 冻结客户端界面测试失败。" }

$PipelineSmokeDir = Join-Path $Root "build\windows\pipeline-smoke-frozen"
$PipelineSmokeInput = Join-Path $PipelineSmokeDir "merged-table.png"
$PipelineSmokeReport = Join-Path $PipelineSmokeDir "result.json"
Remove-Item -LiteralPath $PipelineSmokeDir -Recurse -Force -ErrorAction SilentlyContinue
& $VenvPython (Join-Path $Root "scripts\create_windows_smoke_input.py") $PipelineSmokeInput
if ($LASTEXITCODE) { throw "无法生成 Windows OCR 测试图片。" }
$env:DOCUMENT_OCR_PIPELINE_SMOKE_INPUT = $PipelineSmokeInput
$env:DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT = $PipelineSmokeReport
$process = Start-Process -FilePath (Join-Path $PackageRoot "app\文档OCR助手.exe") -Wait -PassThru
Remove-Item Env:\DOCUMENT_OCR_PIPELINE_SMOKE_INPUT -ErrorAction SilentlyContinue
Remove-Item Env:\DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT -ErrorAction SilentlyContinue
if ($process.ExitCode -ne 0 -or -not (Test-Path $PipelineSmokeReport)) {
    throw "Windows 冻结客户端 ONNX OCR 流水线测试失败。"
}
$PipelineSmoke = Get-Content -LiteralPath $PipelineSmokeReport -Raw -Encoding UTF8 | ConvertFrom-Json
if ($PipelineSmoke.ocr_blocks -lt 1 -or $PipelineSmoke.tables -lt 1 -or $PipelineSmoke.markdown -notmatch 'colspan') {
    throw "Windows 冻结客户端未正确输出 OCR 文字和合并单元格表格。"
}

$ZipPath = Join-Path $Root "dist\文档OCR助手-windows-x86_64.zip"
Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $PackageRoot -DestinationPath $ZipPath -CompressionLevel Optimal

$IsccCandidates = @(
    (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
    (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
) | Where-Object { $_ -and (Test-Path $_) }
if ($IsccCandidates.Count -gt 0) {
    & $IsccCandidates[0] "/DSourceRoot=$PackageRoot" "/DInstallerOutput=$(Join-Path $Root 'dist')" (Join-Path $Root "packaging\文档OCR助手.iss")
} else {
    Write-Warning "未安装 Inno Setup 6，已生成可直接使用的目录包和 ZIP；安装器脚本已保留。"
}

Write-Host "[done] $PackageRoot"
Write-Host "[done] $ZipPath"
Write-Host "[done] UI screenshot: $SmokeScreenshot"
Write-Host "[done] Frozen ONNX OCR/table smoke: $PipelineSmokeReport"
