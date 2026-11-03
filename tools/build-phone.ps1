param([string]$SdkRoot = (Join-Path $PSScriptRoot '..\sdk'))
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$sdk = (Resolve-Path -LiteralPath $SdkRoot).Path
$refs = Get-ChildItem -LiteralPath $sdk -Recurse -Filter mscorlib.dll | Where-Object { $_.FullName -match 'WindowsPhone\\v8\.0\\mscorlib.dll$' } | Select-Object -First 1
$metadata = Get-ChildItem -LiteralPath $sdk -Recurse -Filter Windows.winmd | Where-Object { $_.FullName -match '8\.0\\Windows MetaData' } | Select-Object -First 1
if (!$refs -or !$metadata) { throw 'SDK reference assemblies missing. Run tools\setup-sdk.ps1 first.' }
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
$out = Join-Path $root 'build'
$package = Join-Path $out 'xap'
New-Item -ItemType Directory -Path $package -Force | Out-Null
$resources = Join-Path $out 'LumiaAgent.g.resources'
$writer = [System.Resources.ResourceWriter]::new($resources)
try {
    $stream = [System.IO.MemoryStream]::new([System.IO.File]::ReadAllBytes((Join-Path $root 'phone\MainPage.xaml')))
    $writer.AddResource('mainpage.xaml', $stream, $true)
    $writer.Generate()
} finally { $writer.Dispose() }
$arguments = @('/nologo','/noconfig','/nostdlib+','/target:library','/platform:anycpu','/optimize+','/define:SILVERLIGHT;WINDOWS_PHONE',('/out:' + (Join-Path $package 'LumiaAgent.dll')),('/resource:' + $resources + ',LumiaAgent.g.resources'))
$arguments += Get-ChildItem -LiteralPath $refs.DirectoryName -Filter '*.dll' | ForEach-Object { '/reference:' + $_.FullName }
$arguments += '/reference:' + $metadata.FullName
$arguments += Get-ChildItem -LiteralPath (Join-Path $root 'phone') -Filter '*.cs' | ForEach-Object { $_.FullName }
& $compiler @arguments
if ($LASTEXITCODE -ne 0) { throw 'Phone compilation failed.' }
Copy-Item -LiteralPath (Join-Path $root 'phone\AppManifest.xaml'),(Join-Path $root 'phone\WMAppManifest.xml'),(Join-Path $root 'phone\ApplicationIcon.png'),(Join-Path $root 'phone\Tile.png') -Destination $package -Force
# Remove the obsolete name from builds made before the manifest correction.
$obsoleteManifest = Join-Path $package 'AppManifest.xml'
if (Test-Path -LiteralPath $obsoleteManifest) { Remove-Item -LiteralPath $obsoleteManifest }
$archive = Join-Path $out 'LumiaAgent.xap'
if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive }
[System.IO.Compression.ZipFile]::CreateFromDirectory($package, $archive)
$check = [System.IO.Compression.ZipFile]::OpenRead($archive)
try {
    foreach ($required in @('AppManifest.xaml','WMAppManifest.xml','LumiaAgent.dll')) {
        if (!$check.GetEntry($required)) { throw ('Invalid XAP: missing ' + $required) }
    }
} finally { $check.Dispose() }
Get-FileHash -Algorithm SHA256 -LiteralPath $archive | Select-Object Path,Hash
