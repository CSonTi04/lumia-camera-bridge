$ErrorActionPreference='Stop'
$usb=(Resolve-Path (Join-Path $PSScriptRoot '..\usb')).Path
$client=Join-Path $usb 'SirepClient.dll'
$signature=Get-AuthenticodeSignature -LiteralPath $client
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation'){throw 'Microsoft SirepClient signature verification failed'}
$records=Get-Content -LiteralPath (Join-Path $usb 'sirep-registry.json') -Raw | ConvertFrom-Json
$base=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,[Microsoft.Win32.RegistryView]::Registry32)
try {
 foreach($entry in $records){
  if($entry.key -notmatch '^(CLSID\\\{F2E2D1E2-429A-4B9A-A84E-1083773CEA4A\}|Interface\\\{(C3A050CA-35FC-4C19-9109-2E09A0C86D39|F1B918F2-3FCC-4F2F-BEBC-1E0B42693826)\}|TypeLib\\\{2AA82072-70CF-4F71-AF60-4F773B28A38A\}|SirepClient\.SirepClient)'){throw 'Unexpected registry entry in the SDK manifest'}
  $key=$base.CreateSubKey('Software\Classes\'+$entry.key)
  try {
   if($entry.name -eq '*'){continue}
   $value=$entry.value.Replace('@CLIENT@',$client).Replace('@DIR@',$usb)
   $existing=$key.GetValue($entry.name,$null)
   if($null -ne $existing -and $existing -ne $value){throw ('A different Sirep registration already exists: '+$entry.key)}
   $key.SetValue($entry.name,$value,[Microsoft.Win32.RegistryValueKind]::String)
  } finally {$key.Dispose()}
 }
} finally {$base.Dispose()}
Write-Output 'Registered the signed Microsoft Sirep client for the current user. No browser plugin or emulator was installed.'
