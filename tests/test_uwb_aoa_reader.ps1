$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$latest = Join-Path $env:TEMP "drone_vision_latest_uwb_test.json"
if (Test-Path -LiteralPath $latest) {
    Remove-Item -LiteralPath $latest -Force
}

$hex = "FF FF FF FF 00 25 00 01 20 01 00 01 00 00 00 0A 00 00 00 14 00 00 00 62 FF D9 00 0D 00 00 00 01 00 00 00 00 52"
$output = python "$repo\mp257\uwb_aoa_reader.py" --hex $hex --latest $latest | ConvertFrom-Json

if (-not $output.ok) {
    throw "expected ok UWB frame"
}
if ($output.cmd -ne "location") {
    throw "expected location cmd, got $($output.cmd)"
}
if ([math]::Abs([double]$output.distance_m - 0.98) -gt 0.001) {
    throw "expected distance_m=0.98, got $($output.distance_m)"
}
if ([int]$output.azimuth_deg -ne -39) {
    throw "expected azimuth_deg=-39, got $($output.azimuth_deg)"
}
if (!(Test-Path -LiteralPath $latest)) {
    throw "latest UWB file not written"
}

$latestMsg = Get-Content -LiteralPath $latest -Raw | ConvertFrom-Json
if (-not $latestMsg._received_time) {
    throw "latest UWB file missing _received_time"
}

python "$repo\tools\validate_json_file.py" --schema "$repo\schemas\uwb_aoa.schema.json" $latest
Write-Host "OK UWB/AOA parser wrote latest distance_m=$($latestMsg.distance_m) azimuth_deg=$($latestMsg.azimuth_deg)"
