param([Parameter(Position=0)][ValidateSet('status','preview','capture','crop')][string]$Action='status', [string]$BridgeUrl='http://127.0.0.1:8765', [string]$Config=(Join-Path $PSScriptRoot '..\agent-config.json'), [string]$Camera='rear', [string]$Aspect='4:3', [string]$OutFile, [string]$ImageId, [int]$X, [int]$Y, [int]$Width, [int]$Height)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$arguments=@((Join-Path $root 'bridge\lumia_cli.py'),'--url',$BridgeUrl,'--config',$Config,$Action)
if ($Action -in @('preview','capture')) {
    if (!$OutFile) { throw 'Provide -OutFile for the JPEG.' }
    $arguments+=@('--camera',$Camera,'--aspect',$Aspect,'--out',$OutFile)
}
if ($Action -eq 'crop') {
    if (!$ImageId -or !$OutFile) { throw 'Provide -ImageId, coordinates, dimensions and -OutFile.' }
    $arguments+=@($ImageId,$X,$Y,$Width,$Height,'--out',$OutFile)
}
& (Join-Path $root '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
