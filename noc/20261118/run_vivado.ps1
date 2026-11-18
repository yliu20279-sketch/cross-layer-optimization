param([Parameter(Mandatory)][int]$Arm)
$ErrorActionPreference='Stop'
$runRoot = Join-Path $env:TEMP 'noc_dual_plane_hw_20261118'
$null = New-Item -ItemType Directory -Path $runRoot -Force
$sources=@('mesh.sv','circuits.sv','noc_paired.sv','coherence_mesh.sv','dual_plane_noc.sv','vivado.tcl','noc.xdc')
foreach ($name in $sources) {
    $source=Join-Path $PSScriptRoot $name
    $destination=Join-Path $runRoot $name
    if (Test-Path -LiteralPath $destination) {
        if ((Get-FileHash -LiteralPath $source).Hash -ne (Get-FileHash -LiteralPath $destination).Hash) {
            throw "Source changed during the paired FPGA run: $name"
        }
    } else {
        Copy-Item -LiteralPath $source -Destination $destination
    }
}
Push-Location $runRoot
try {
    & 'D:/xilinx/Vivado/2017.4/bin/vivado.bat' -mode batch -log "vivado_$Arm.log" -journal "vivado_$Arm.jou" -source vivado.tcl -tclargs $Arm
    if ($LASTEXITCODE -ne 0) { throw "Vivado arm $Arm failed." }
    if (!(Select-String -LiteralPath "vivado_$Arm.log" -Pattern "^PASS_ROUTE $Arm$" -Quiet)) { throw 'Missing route completion' }
    Copy-Item -LiteralPath (Join-Path $runRoot "reports_$Arm") -Destination $PSScriptRoot -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $runRoot "vivado_$Arm.log") -Destination $PSScriptRoot -Force
    $manifest=@($sources | ForEach-Object { [pscustomobject]@{Name=$_;Hash=(Get-FileHash -LiteralPath (Join-Path $runRoot $_)).Hash} })
    $manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot "fpga_sources_$Arm.json") -Encoding utf8
} finally { Pop-Location }
