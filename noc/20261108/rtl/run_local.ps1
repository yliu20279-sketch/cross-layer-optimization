param(
    [string]$Python = 'C:/Users/14284/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',
    [string]$ToolRoot = 'C:/Users/14284/AppData/Local/Temp/noc_aux_hdl_20261104_01/mingw64',
    [string]$StageRoot = 'C:/Users/14284/AppData/Local/Temp/noc_aux_hdl_20261104_01/run'
)
$ErrorActionPreference = 'Stop'
$auxResolvedStage = [IO.Path]::GetFullPath($StageRoot)
$auxAllowedTemp = [IO.Path]::GetFullPath('C:/Users/14284/AppData/Local/Temp/')
if (-not $auxResolvedStage.StartsWith($auxAllowedTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'StageRoot must stay within the task temporary directory tree.'
}
New-Item -ItemType Directory -Path $auxResolvedStage -Force | Out-Null
foreach ($auxFolder in @('rtl','tb','synth','negative')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $auxFolder) -Destination $auxResolvedStage -Recurse -Force
}
foreach ($auxFile in @('run_tests.py','check_artifacts.py','iverilog_direct.py','run_remote.sh','run_local.ps1','probe_local_tool.py')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $auxFile) -Destination $auxResolvedStage -Force
}
$auxOldPath = $env:PATH
$auxOldCompiler = $env:IVERILOG
$auxOldSimulator = $env:VVP
try {
    $env:PATH = (Join-Path $ToolRoot 'bin') + ';' + $env:PATH
    $env:IVERILOG = Join-Path $ToolRoot 'bin/iverilog.exe'
    $env:VVP = Join-Path $ToolRoot 'bin/vvp.exe'
    & $Python (Join-Path $auxResolvedStage 'probe_local_tool.py')
    if ($LASTEXITCODE -ne 0) { throw 'Independent compiler-core health check failed.' }
    & $Python (Join-Path $auxResolvedStage 'run_tests.py')
    $auxTestExit = $LASTEXITCODE
    Copy-Item -LiteralPath (Join-Path $auxResolvedStage 'build') -Destination $PSScriptRoot -Recurse -Force
    if ($auxTestExit -ne 0) { throw "HDL regression failed: $auxTestExit" }
    & $Python (Join-Path $PSScriptRoot 'check_artifacts.py')
    if ($LASTEXITCODE -ne 0) { throw 'Copied artifact audit failed.' }
} finally {
    $env:PATH = $auxOldPath
    $env:IVERILOG = $auxOldCompiler
    $env:VVP = $auxOldSimulator
}
