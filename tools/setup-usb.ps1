param([string]$Msi = (Join-Path $PSScriptRoot '..\cache\usb-core\wpsdk_en.msi'), [switch]$IncludeDeploymentSupport)
$ErrorActionPreference='Stop'
$package=(Resolve-Path -LiteralPath $Msi).Path
$signature=Get-AuthenticodeSignature -LiteralPath $package
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Microsoft MSI signature verification failed' }
$log=Join-Path (Split-Path $package) 'usb-install.log'
$features='MT_WPSDK_CoreConFeature_x86_enu_V3'
if ($IncludeDeploymentSupport) { $features+=',MT_WPSDK_WP8_Tools_x86_enu_V3' }
$arguments=@('/i',('"'+$package+'"'),'/qn','/norestart',('ADDLOCAL='+$features),'REBOOT=ReallySuppress','/l*v',('"'+$log+'"'))
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$start=@{FilePath=(Join-Path $env:WINDIR 'System32\msiexec.exe'); ArgumentList=$arguments; Wait=$true; PassThru=$true; WindowStyle='Hidden'}
if (!$admin) { $start.Verb='RunAs' }
$process=Start-Process @start
if ($process.ExitCode -notin @(0,3010)) { throw "USB connectivity installation failed with code $($process.ExitCode). Log: $log" }
Get-Service -Name IpOverUsbSvc | Select-Object Name,Status
Write-Output "Configured Microsoft's USB connectivity feature (about 3.5 MB)$(if($IncludeDeploymentSupport){' and standalone deployment support (about 60 MB)'}) without Visual Studio IDE or emulator. Log: $log"
