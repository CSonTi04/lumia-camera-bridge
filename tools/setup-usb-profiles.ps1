param([string]$Msi=(Join-Path $PSScriptRoot '..\cache\usb-profiles\WPSDK_en.msi'))
$ErrorActionPreference='Stop'
$package=(Resolve-Path -LiteralPath $Msi).Path
$signature=Get-AuthenticodeSignature -LiteralPath $package
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Microsoft MSI signature verification failed' }
$log=Join-Path (Split-Path $package) 'profiles-install.log'
# These three features contain the shared transport runtime, device profile XSL/XML,
# and the managed SDK adapter. They contain no emulator images, driver or IDE.
$args=@('/i',('"'+$package+'"'),'/qn','/norestart','ADDLOCAL=SdeCoreConFeature,SdkXdeFeature_v71,WPSDK_MTComponents','SKIP_IMAGEGEN=1','REBOOT=ReallySuppress','/l*v',('"'+$log+'"'))
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$start=@{FilePath=(Join-Path $env:WINDIR 'System32\msiexec.exe');ArgumentList=$args;Wait=$true;PassThru=$true;WindowStyle='Hidden'}
if(!$admin){$start.Verb='RunAs'}
$process=Start-Process @start
if($process.ExitCode -notin @(0,3010)){throw "SDK device profile installation failed ($($process.ExitCode)). Log: $log"}
Write-Output "Installed shared SDK device profiles and transport adapters (about 4 MB). Log: $log"
