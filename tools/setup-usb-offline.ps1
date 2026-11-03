$ErrorActionPreference='Stop'
# Requires the cached, signed SDK MSI/CAB, usb\profiles\ImageConfig.xsl,
# SirepClient.dll, its MSI-derived registration manifest, and the managed SDK DLLs.
# It configures the PC. It does not reset, flash, root, or unlock a phone.
& (Join-Path $PSScriptRoot 'setup-usb.ps1')
& (Join-Path $PSScriptRoot 'register-device-profile.ps1')
& (Join-Path $PSScriptRoot 'register-sirep.ps1')
& (Join-Path $PSScriptRoot 'build-deployer.ps1')
$deployer=Join-Path $PSScriptRoot '..\usb\PhoneDeploy.exe'
& $deployer --list
if($LASTEXITCODE -ne 0){throw 'SDK target discovery failed'}
Write-Output 'PC USB setup is ready. Unlock the phone screen and run tools\lumia.ps1 usb-status, then tools\lumia.ps1 deploy.'
