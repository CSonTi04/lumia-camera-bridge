param([string]$Profiles=(Join-Path $PSScriptRoot '..\usb\profiles'))
$ErrorActionPreference='Stop'
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if(!$admin){
 $profilePath=(Resolve-Path -LiteralPath $Profiles).Path
 $arguments=@('-NoProfile','-File',('"'+$PSCommandPath+'"'),'-Profiles',('"'+$profilePath+'"'))
 $process=Start-Process -FilePath (Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe') -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -Wait -PassThru
 if($process.ExitCode -ne 0){throw 'Administrative device-profile registration failed.'}
 return
}
$destination=Join-Path $env:ProgramData 'Microsoft\Phone Tools\CoreCon\11.0\addons'
if(!(Test-Path -LiteralPath $destination)){throw 'Install USB connectivity first.'}
$profile=[xml](Get-Content -LiteralPath (Join-Path $Profiles 'ImageConfig.xsl') -Raw)
if($profile.SelectSingleNode("//*[local-name()='PLATFORM']").Name -ne 'Windows Phone 8'){throw 'Expected the Microsoft Windows Phone 8 profile.'}
foreach($name in @('ImageConfig.xsl')) {
 $source=Join-Path $Profiles $name
 if(!(Test-Path -LiteralPath $source)){throw "Missing Microsoft device descriptor: $source"}
 $target=Join-Path $destination $name
 if((Test-Path -LiteralPath $target) -and (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $source).Hash){
  $legacy=Join-Path $Profiles ('legacy\'+$name)
  if(!(Test-Path -LiteralPath $legacy) -or (Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $legacy).Hash){throw "An existing device descriptor differs: $target"}
  Move-Item -LiteralPath $target -Destination ($target+'.wp7-backup') -Force
 }
 Copy-Item -LiteralPath $source -Destination $target -Force
 (Get-Item -LiteralPath $target).LastWriteTimeUtc=[DateTime]::UtcNow
}
$obsolete=Join-Path $destination 'ImageConfig.en-US.xsl'
$legacy=Join-Path $Profiles 'legacy\ImageConfig.en-US.xsl'
if((Test-Path -LiteralPath $obsolete) -and (Test-Path -LiteralPath $legacy) -and (Get-FileHash -LiteralPath $obsolete).Hash -eq (Get-FileHash -LiteralPath $legacy).Hash){Move-Item -LiteralPath $obsolete -Destination ($obsolete+'.wp7-backup') -Force}
Write-Output 'Registered the Microsoft shared physical-device descriptor with the SDK 8 transport.'
