param(
    [string]$Python = "python",
    [ValidateSet("ocr", "full")][string]$Edition = "full",
    [string]$ComponentsDir = "",
    [string]$WindowsRuntimeRoot = "",
    [string]$BuildVenv = "",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
$Version = "0.2.0"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $ComponentsDir) { $ComponentsDir = Join-Path $Root "offline_components" }
if (-not $WindowsRuntimeRoot) { $WindowsRuntimeRoot = Join-Path $ComponentsDir "windows-runtime" }
if (-not $BuildVenv) { $BuildVenv = Join-Path $Root ".build-venv-windows" }
$VenvPython = Join-Path $BuildVenv "Scripts\python.exe"
$Cache = Join-Path $Root ".build-cache"
$TableModel = if ($env:DOCUMENT_OCR_TABLE_MODEL) { $env:DOCUMENT_OCR_TABLE_MODEL } else { Join-Path $Cache "slanet-plus.onnx" }
$OrientationModel = Join-Path $Cache "orientation\rapid_orientation.onnx"
$AppName = if ($Edition -eq "ocr") { "文档OCR助手OCR版" } else { "文档OCR助手完整版" }
$AssetStem = "document-ocr-assistant-$Version-windows-x86_64-$Edition"
$PackageRoot = Join-Path $Root "dist\$AssetStem"
$PyiDist = Join-Path $Root "build\windows\pyi-dist"
$PyiWork = Join-Path $Root "build\windows\pyi-work"
$BuildInfo = Join-Path $Root "build\windows\metadata\$Edition\build-info.json"

if (-not [Environment]::Is64BitOperatingSystem) { throw "Windows x86_64 构建需要 64 位系统。" }
if (-not (Test-Path $ComponentsDir)) { throw "找不到离线组件：$ComponentsDir" }
if (-not (Test-Path $WindowsRuntimeRoot)) { throw "找不到 Windows 运行时组件：$WindowsRuntimeRoot" }
if (-not (Test-Path $VenvPython)) { & $Python -m venv $BuildVenv }
if ($LASTEXITCODE) { throw "无法创建 Windows 构建环境。" }

if (-not $SkipDependencyInstall) {
    & $VenvPython -m pip install --upgrade pip wheel setuptools
    & $VenvPython -m pip install -r (Join-Path $Root "requirements-windows.txt") -r (Join-Path $Root "requirements-table.txt")
    if ($Edition -eq "full") {
        & $VenvPython -m pip install -r (Join-Path $Root "requirements-windows-full.txt")
    }
    & $VenvPython -m pip install "pyinstaller==6.18.0" "pyinstaller-hooks-contrib==2026.0" "pytest>=7.4,<9"
}

New-Item -ItemType Directory -Force $Cache | Out-Null
if (-not (Test-Path $TableModel)) { & $VenvPython (Join-Path $Root "scripts\fetch_table_model.py") $TableModel }
if (-not (Test-Path $OrientationModel)) {
    $OrientationArchive = Join-Path $ComponentsDir "rapid_orientation_models_v2.zip"
    if (Test-Path $OrientationArchive) {
        & $VenvPython (Join-Path $Root "scripts\fetch_orientation_model.py") (Split-Path $OrientationModel -Parent) --source-archive $OrientationArchive
    } else {
        & $VenvPython (Join-Path $Root "scripts\fetch_orientation_model.py") (Split-Path $OrientationModel -Parent)
    }
}
& $VenvPython (Join-Path $Root "scripts\create_windows_icon.py") (Join-Path $Root "assets\app-icon.svg") (Join-Path $Root "assets\app-icon.ico")

Remove-Item -LiteralPath $PyiDist,$PyiWork,$PackageRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $PyiDist,$PyiWork,$PackageRoot,(Join-Path $PackageRoot "app"),(Join-Path $PackageRoot "assets") | Out-Null
& $VenvPython (Join-Path $Root "scripts\write_build_info.py") $BuildInfo --edition $Edition --version $Version --platform windows --architecture x86_64
$env:DOCUMENT_OCR_BUILD_EDITION = $Edition
$env:DOCUMENT_OCR_BUILD_INFO = $BuildInfo
$env:DOCUMENT_OCR_BUILD_VERSION = $Version
& $VenvPython -m PyInstaller --noconfirm --clean --distpath $PyiDist --workpath $PyiWork (Join-Path $Root "packaging\document_ocr_assistant_windows.spec")
Remove-Item Env:\DOCUMENT_OCR_BUILD_EDITION,Env:\DOCUMENT_OCR_BUILD_INFO,Env:\DOCUMENT_OCR_BUILD_VERSION -ErrorAction SilentlyContinue
if ($LASTEXITCODE) { throw "PyInstaller Windows 构建失败。" }

$BuiltApp = Join-Path $PyiDist $AppName
Copy-Item -Path (Join-Path $BuiltApp "*") -Destination (Join-Path $PackageRoot "app") -Recurse -Force
Copy-Item $BuildInfo (Join-Path $PackageRoot "app\build-info.json")
Copy-Item (Join-Path $Root "assets\app-icon.svg") (Join-Path $PackageRoot "assets\app-icon.svg")
Copy-Item (Join-Path $Root "assets\app-icon.ico") (Join-Path $PackageRoot "assets\app-icon.ico")
$Launcher = Join-Path $PackageRoot "启动$AppName.bat"
"@echo off`r`nchcp 65001 >nul`r`nstart `"`" `"%~dp0app\$AppName.exe`"`r`n" | Set-Content -LiteralPath $Launcher -Encoding UTF8

& $VenvPython (Join-Path $Root "scripts\prepare_windows_runtime.py") `
    --components-dir $ComponentsDir `
    --windows-runtime-root $WindowsRuntimeRoot `
    --output-root $PackageRoot `
    --table-model $TableModel `
    --orientation-model $OrientationModel

@"
文档OCR助手 Windows x86_64 $Edition 版

运行：双击“启动$AppName.bat”或 app\$AppName.exe。
Office 策略：$(if ($Edition -eq "ocr") { "仅支持图片/PDF，不包含 pywin32、LibreOffice 或 Word/WPS 转换。" } else { "自动调用本机 Microsoft Word 或 WPS Office；本包不包含 LibreOffice。" })
OCR 与表格识别：PP-OCRv6 Medium + SLANet-plus，全部使用 ONNX Runtime 离线运行。
支持图片、PDF、DOC/DOCX/WPS、文件夹及 ZIP/RAR/7Z/TAR/TAR.GZ/TGZ。
批量识别可勾选“复制未转换文件”（默认关闭），将目录或压缩包内其他文件按原层级复制到新批次目录。
关闭主窗口时默认询问缩小到右下角或退出；可选择记住，并可在设置页修改。
"@ | Set-Content -LiteralPath (Join-Path $PackageRoot "使用说明.txt") -Encoding UTF8

$SmokeScreenshot = Join-Path $Root "build\windows\windows-ui-smoke.png"
$env:DOCUMENT_OCR_UI_SMOKE_SCREENSHOT = $SmokeScreenshot
$Executable = Join-Path $PackageRoot "app\$AppName.exe"

function Invoke-FrozenCli {
    param(
        [Parameter(Mandatory)][string[]]$CliArguments,
        [string]$StdoutPath = "",
        [string]$StderrPath = "",
        [switch]$AllowFailure
    )
    $quotedArguments = foreach ($argument in $CliArguments) {
        '"' + $argument.Replace('"', '\"') + '"'
    }
    $startParameters = @{
        FilePath = $Executable
        ArgumentList = ($quotedArguments -join ' ')
        Wait = $true
        PassThru = $true
    }
    if ($StdoutPath) {
        Remove-Item -LiteralPath $StdoutPath -Force -ErrorAction SilentlyContinue
        $startParameters.RedirectStandardOutput = $StdoutPath
    }
    if ($StderrPath) {
        Remove-Item -LiteralPath $StderrPath -Force -ErrorAction SilentlyContinue
        $startParameters.RedirectStandardError = $StderrPath
    }
    $frozenProcess = Start-Process @startParameters
    if (-not $AllowFailure -and $frozenProcess.ExitCode -ne 0) {
        $detail = if ($StderrPath -and (Test-Path $StderrPath)) {
            Get-Content -LiteralPath $StderrPath -Raw -Encoding UTF8
        } else { "" }
        throw "冻结客户端退出码异常：$($frozenProcess.ExitCode) $detail"
    }
    return $frozenProcess
}

$process = Start-Process -FilePath $Executable -Wait -PassThru
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
$process = Start-Process -FilePath $Executable -Wait -PassThru
Remove-Item Env:\DOCUMENT_OCR_PIPELINE_SMOKE_INPUT -ErrorAction SilentlyContinue
Remove-Item Env:\DOCUMENT_OCR_PIPELINE_SMOKE_OUTPUT -ErrorAction SilentlyContinue
if ($process.ExitCode -ne 0 -or -not (Test-Path $PipelineSmokeReport)) {
    throw "Windows 冻结客户端 ONNX OCR 流水线测试失败。"
}
$PipelineSmoke = Get-Content -LiteralPath $PipelineSmokeReport -Raw -Encoding UTF8 | ConvertFrom-Json
if ($PipelineSmoke.ocr_blocks -lt 1 -or $PipelineSmoke.tables -lt 1 -or $PipelineSmoke.markdown -notmatch 'colspan') {
    throw "Windows 冻结客户端未正确输出 OCR 文字和合并单元格表格。"
}

$ReleaseMaterials = Join-Path $PipelineSmokeDir "generated-release-materials"
& $VenvPython (Join-Path $Root "scripts\create_release_test_materials.py") $ReleaseMaterials
foreach ($Angle in @(0, 90, 180, 270)) {
    $DirectionOutput = Join-Path $PipelineSmokeDir "orientation-$Angle"
    $DirectionReport = Join-Path $PipelineSmokeDir "orientation-$Angle.json"
    Invoke-FrozenCli -CliArguments @(
        '--cli',
        (Join-Path $ReleaseMaterials "orientation-$Angle.png"),
        '-o', $DirectionOutput,
        '--report-json', $DirectionReport,
        '--no-table'
    ) | Out-Null
    $DirectionTextFound = Get-ChildItem $DirectionOutput -Recurse -File |
        Where-Object { $_.Extension -in '.txt', '.md' } |
        Select-String -Pattern 'Document|OCR' -Quiet
    if (-not $DirectionTextFound) {
        throw "Windows 冻结客户端未通过 $Angle 度页面方向测试。"
    }
    $DirectionMetadata = Get-Content -LiteralPath $DirectionReport -Raw -Encoding UTF8 | ConvertFrom-Json
    $ExpectedAngle = @{ 0 = 0; 90 = 270; 180 = 180; 270 = 90 }[$Angle]
    if ($DirectionMetadata[0].metadata.pages[0].applied_angle -ne $ExpectedAngle) {
        throw "Windows 冻结客户端方向角度错误：source=$Angle expected=$ExpectedAngle actual=$($DirectionMetadata[0].metadata.pages[0].applied_angle)"
    }
}

$OfficeSmokeInput = Join-Path $PipelineSmokeDir "office.docx"
& $VenvPython (Join-Path $Root "scripts\create_office_smoke_input.py") $OfficeSmokeInput
if ($Edition -eq "full") {
    $OfficeOutput = Join-Path $PipelineSmokeDir "office-output"
    Invoke-FrozenCli -CliArguments @('--cli', $OfficeSmokeInput, '-o', $OfficeOutput, '--no-table') | Out-Null
    $OfficeTextFound = Get-ChildItem $OfficeOutput -Recurse -File |
        Where-Object { $_.Extension -in '.txt', '.md' } |
        Select-String -Pattern 'LibreOffice bundled conversion test' -Quiet
    if (-not $OfficeTextFound) {
        throw "Windows 完整版未通过本机 Word/WPS 转换测试。"
    }
} else {
    $RefusalStdout = Join-Path $PipelineSmokeDir "office-refusal-stdout.txt"
    $RefusalStderr = Join-Path $PipelineSmokeDir "office-refusal-stderr.txt"
    $RefusalProcess = Invoke-FrozenCli -CliArguments @('--cli', $OfficeSmokeInput, '--no-table') `
        -StdoutPath $RefusalStdout -StderrPath $RefusalStderr -AllowFailure
    $Refusal = ((Get-Content -LiteralPath $RefusalStdout,$RefusalStderr -Raw -Encoding UTF8) -join "`n")
    if ($RefusalProcess.ExitCode -eq 0 -or $Refusal -notmatch 'OCR版不支持 Word/WPS.*下载完整版') {
        throw "Windows OCR 版未清晰拒绝 Word/WPS：$Refusal"
    }
}

$VersionStdout = Join-Path $PipelineSmokeDir "version-stdout.txt"
$VersionStderr = Join-Path $PipelineSmokeDir "version-stderr.txt"
Invoke-FrozenCli -CliArguments @('--cli', '--version') `
    -StdoutPath $VersionStdout -StderrPath $VersionStderr | Out-Null
$VersionOutput = Get-Content -LiteralPath $VersionStdout -Raw -Encoding UTF8
if ($VersionOutput -notmatch "\($Edition, windows, x86_64\)") { throw "冻结程序 --version edition 信息不正确：$VersionOutput" }
if ($Edition -eq "ocr") {
    $Forbidden = Get-ChildItem -LiteralPath $PackageRoot -Recurse -Force | Where-Object {
        $_.FullName -match '(?i)libreoffice|pywin32|win32com|pythoncom|\.docx?$|\.wps$'
    }
    if ($Forbidden) { throw "OCR 版包含 Office 组件：$($Forbidden.FullName -join ', ')" }
}

$ZipPath = Join-Path $Root "dist\$AssetStem.zip"
Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $PackageRoot -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "[done] $PackageRoot"
Write-Host "[done] $ZipPath"
Write-Host "[done] UI screenshot: $SmokeScreenshot"
Write-Host "[done] Frozen ONNX OCR/table smoke: $PipelineSmokeReport"
