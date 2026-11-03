param([string]$Root = (Join-Path $PSScriptRoot '..'))
$ErrorActionPreference = 'Stop'
$rootPath = [IO.Path]::GetFullPath($Root)
$cache = Join-Path $rootPath 'cache'
$sdk = Join-Path $rootPath 'sdk'
$iso = Join-Path $cache 'wpsdkv80_enu1.iso'
$sevenzip = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
if (!$sevenzip) { $sevenzip = 'C:\Program Files\7-Zip\7z.exe' }
if (!(Test-Path -LiteralPath $sevenzip)) { throw 'Install 7-Zip or add 7z.exe to PATH.' }
New-Item -ItemType Directory -Path $cache -Force | Out-Null
if (!(Test-Path -LiteralPath $iso)) {
    Invoke-WebRequest -Uri 'https://download.microsoft.com/download/9/3/8/938A5074-461F-4E3D-89F4-5CE2F42C1E36/wpsdkv80_enu1.iso' -OutFile ($iso + '.partial')
    Move-Item -LiteralPath ($iso + '.partial') -Destination $iso
}
if ((Get-Item -LiteralPath $iso).Length -ne 1721982976) { throw 'SDK ISO size mismatch; download is incomplete.' }
if ((Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne 'A33244DDD3DCFC731763F23159D36A77C96A870CEA03F0FD88F9AB52D397CE8A') { throw 'SDK ISO does not match the pinned Microsoft download used to build this kit.' }
$payloads = Join-Path $cache 'payloads'
& $sevenzip x $iso 'packages\MobileTools\wpsdk\*' 'packages\MobileTools\wpsdkcore\*' ('-o' + $payloads) -y
if ($LASTEXITCODE -ne 0) { throw 'ISO extraction failed.' }
Get-ChildItem -LiteralPath $payloads -Recurse -Filter '*.msi' | ForEach-Object {
    $signature = Get-AuthenticodeSignature -LiteralPath $_.FullName
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw ('Microsoft MSI signature validation failed: ' + $_.Name) }
}
python (Join-Path $PSScriptRoot 'extract_sdk.py') $payloads $sdk --sevenzip $sevenzip
if ($LASTEXITCODE -ne 0) { throw 'SDK extraction failed.' }
Write-Output 'SDK files extracted. No MSI, Visual Studio installer, driver, or emulator was installed.'
