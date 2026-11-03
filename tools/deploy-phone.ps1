param([string]$Xap = (Join-Path $PSScriptRoot '..\build\LumiaAgent.xap'), [string]$DeployCommand, [switch]$Update)
$ErrorActionPreference = 'Stop'
if (!$DeployCommand) {
    $portable=Join-Path $PSScriptRoot '..\usb\PhoneDeploy.exe'
    if(Test-Path -LiteralPath $portable){
        & $portable --install ((Resolve-Path -LiteralPath $Xap).Path)
        if($LASTEXITCODE -ne 0){throw 'USB deployment failed. Read the JSON error above; keep the screen unlocked. A developer-lock error requires a separate phone-side sideloading setup.'}
        return
    }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Microsoft SDKs\Windows Phone\v8.0\Tools\XAP Deployment\XapDeployCmd.exe",
        "${env:ProgramFiles(x86)}\Microsoft SDKs\Windows Phone\v8.1\Tools\AppDeploy\AppDeployCmd.exe"
    )
    $DeployCommand = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (!$DeployCommand -or !(Test-Path -LiteralPath $DeployCommand)) {
    throw 'USB command-line deployment is not configured. Portable build references do not install the USB service or unlock the phone. Supply -DeployCommand pointing at an existing XapDeployCmd.exe/AppDeployCmd.exe after phone sideloading is enabled. See README.md.'
}
$package = (Resolve-Path -LiteralPath $Xap).Path
$action = if ($Update) { '/update' } else { '/installlaunch' }
& $DeployCommand $action $package '/targetdevice:de'
if ($LASTEXITCODE -ne 0) { throw "Phone deployment returned exit code $LASTEXITCODE. Confirm the device is unlocked for sideloading and the USB deployment service is present." }
