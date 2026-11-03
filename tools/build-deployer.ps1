param([string]$ConnectivityAssemblies = (Join-Path $PSScriptRoot '..\usb'))
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$out=Join-Path $root 'usb'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$sdk=(Resolve-Path -LiteralPath $ConnectivityAssemblies).Path
if($sdk -ne $out){Get-ChildItem -LiteralPath $sdk -Filter '*.dll' | Where-Object { $_.Name -match '^Microsoft\.(Smartdevice|VisualStudio.DeviceConnectivity)' } | Copy-Item -Destination $out -Force}
Copy-Item -LiteralPath (Join-Path $root 'phone\ApplicationIcon.png') -Destination $out -Force
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
& $compiler /nologo /target:exe /platform:x86 /optimize+ ('/out:'+(Join-Path $out 'PhoneDeploy.exe')) ('/reference:'+(Join-Path $out 'Microsoft.Smartdevice.Connectivity.Interface.dll')) ('/reference:'+(Join-Path $out 'Microsoft.Smartdevice.MultiTargeting.Connectivity.dll')) /reference:System.Web.Extensions.dll /reference:System.Xml.Linq.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll (Join-Path $PSScriptRoot 'PhoneDeploy.cs')
if ($LASTEXITCODE -ne 0) { throw 'Command-line deployer build failed' }
& (Join-Path $out 'PhoneDeploy.exe') --help
