param([Parameter(Position=0)][ValidateSet('doctor','build','test','init','serve','usb-status','usb-state','usb-logs','pair','deploy')][string]$Action='doctor', [string]$OutFile)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python=Join-Path $root '.venv\Scripts\python.exe'
if ($Action -in @('usb-status','usb-state','usb-logs','pair','deploy')) {
    if (Get-Process -Name WPinternals -ErrorAction SilentlyContinue) { throw 'Close Windows Phone Internals before SDK USB operations.' }
}
switch ($Action) {
    'doctor' {
        $references=@(Get-ChildItem (Join-Path $root 'sdk') -Recurse -Filter Microsoft.Phone.dll -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'WindowsPhone\\v8\.0\\Microsoft.Phone.dll$' })
        [PSCustomObject]@{Root=$root;PythonReady=(Test-Path -LiteralPath $python);CompilerReady=(Test-Path (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'));PhoneReferencesReady=($references.Count -gt 0);XapReady=(Test-Path (Join-Path $root 'build\LumiaAgent.xap'));UsbDeployerReady=(Test-Path (Join-Path $root 'usb\PhoneDeploy.exe'))} | ConvertTo-Json
    }
    'build' { & (Join-Path $PSScriptRoot 'build-phone.ps1'); exit $LASTEXITCODE }
    'test' { & $python -m unittest discover -s (Join-Path $root 'tests') -v; exit $LASTEXITCODE }
    'init' { & $python (Join-Path $root 'bridge\lumia_bridge.py') --config (Join-Path $root 'config.json') --init; exit $LASTEXITCODE }
    'serve' { & $python (Join-Path $root 'bridge\lumia_bridge.py') --config (Join-Path $root 'config.json') --data (Join-Path $root 'data'); exit $LASTEXITCODE }
    'usb-status' { & (Join-Path $root 'usb\PhoneDeploy.exe') --probe; exit $LASTEXITCODE }
    'usb-state' { & (Join-Path $root 'usb\PhoneDeploy.exe') --state; exit $LASTEXITCODE }
    'usb-logs' {
        if (!$OutFile) { throw 'Provide -OutFile with a new local log path.' }
        & (Join-Path $root 'usb\PhoneDeploy.exe') --logs $OutFile
        exit $LASTEXITCODE
    }
    'pair' {
        & (Join-Path $root 'usb\PhoneDeploy.exe') --pair (Join-Path $root 'phone-config.json')
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & (Join-Path $PSScriptRoot 'deploy-phone.ps1')
        exit $LASTEXITCODE
    }
    'deploy' { & (Join-Path $PSScriptRoot 'deploy-phone.ps1'); exit $LASTEXITCODE }
}
