[CmdletBinding()]
param(
  [string]$Configuration = "Release"
)

$ErrorActionPreference = 'Stop'

function Require-Tool($name) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if (-not $cmd) {
    throw "Required tool '$name' not found on PATH. Install WiX Toolset v3.11 and ensure candle.exe/light.exe are available."
  }
}

Require-Tool "candle.exe"
Require-Tool "light.exe"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "src"
$out = Join-Path $here "out"
$obj = Join-Path $here "obj"

New-Item -ItemType Directory -Force -Path $out,$obj | Out-Null

$wxsFiles = Get-ChildItem -Path $src -Filter *.wxs | Sort-Object Name

foreach ($wxs in $wxsFiles) {
  $name = [System.IO.Path]::GetFileNameWithoutExtension($wxs.Name)
  $wixobj = Join-Path $obj "$name.wixobj"
  $msi = Join-Path $out "$name.msi"

  Write-Host "== Building $name =="
  & candle.exe -nologo -dConfiguration=$Configuration -out $wixobj $wxs.FullName
  & light.exe -nologo -out $msi $wixobj -ext WixUIExtension
}

Write-Host "Built MSIs in: $out"
