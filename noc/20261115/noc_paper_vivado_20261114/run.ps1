param(
    [string] $Vivado = 'vivado.bat',
    [Parameter(Mandatory)] [string] $WorkDir,
    [string] $IcarusBin
)

$ErrorActionPreference = 'Stop'
$work = [IO.Path]::GetFullPath($WorkDir)
if ($work -match '[^\x20-\x7e]') { throw 'Use an ASCII work directory for Vivado 2017.4.' }
if (Test-Path $work) { throw 'Choose a fresh work directory to preserve prior runs.' }
$null = New-Item -ItemType Directory -Path $work
Copy-Item (Join-Path $PSScriptRoot '*.sv'),(Join-Path $PSScriptRoot 'noc.xdc'),(Join-Path $PSScriptRoot 'run.tcl'),(Join-Path $PSScriptRoot 'route.tcl') $work
Push-Location $work
try {
    if ($IcarusBin) {
        $originalPath = $env:PATH
        try {
            $env:PATH = "$IcarusBin;$originalPath"
            & iverilog.exe -g2012 -s tb -o tb.vvp mesh.sv circuits.sv noc_paired.sv tb.sv
            if ($LASTEXITCODE -ne 0) { throw 'Icarus compile failed.' }
            & vvp.exe tb.vvp | Tee-Object RTL.log
            if ($LASTEXITCODE -ne 0 -or !(Select-String -Quiet -Path RTL.log -Pattern '^PASS_PAPER_NOC$')) {
                throw 'RTL regression failed.'
            }
        } finally { $env:PATH = $originalPath }
    }
    foreach ($arm in 0,1) {
        & $Vivado -mode batch -log "vivado_$arm.log" -journal "vivado_$arm.jou" -source run.tcl -tclargs $arm
        if ($LASTEXITCODE -ne 0) { throw "Vivado synthesis failed for ENHANCED=$arm." }
    }
} finally { Pop-Location }


