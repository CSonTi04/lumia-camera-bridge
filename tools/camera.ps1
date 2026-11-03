param(
    [Parameter(Position=0)][ValidateSet('status','capabilities','preview','capture','crop')][string]$Action='status',
    [string]$BridgeUrl='http://127.0.0.1:8765',
    [string]$Config=(Join-Path $PSScriptRoot '..\agent-config.json'),
    [string]$Camera='rear', [string]$Aspect='4:3', [string]$OutFile, [string]$ImageId,
    [int]$X, [int]$Y, [int]$Width, [int]$Height,
    [switch]$Focus, [switch]$NoFocus,
    [ValidateSet('auto','normal','macro','full','infinity','hyperfocal')][string]$FocusRange='auto',
    [string]$ControlsFile,
    [double[]]$FocusRegion
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$arguments=@((Join-Path $root 'bridge\lumia_cli.py'),'--url',$BridgeUrl,'--config',$Config,$Action)
if ($Action -in @('preview','capture')) {
    if (!$OutFile) { throw 'Provide -OutFile for the JPEG.' }
    if ($Focus -and $NoFocus) { throw 'Choose -Focus or -NoFocus.' }
    $arguments+=@('--camera',$Camera,'--aspect',$Aspect,'--focus-range',$FocusRange,'--out',$OutFile)
    if ($Focus) { $arguments+='--focus' }
    if ($NoFocus) { $arguments+='--no-focus' }
    if ($ControlsFile) { $arguments+=@('--controls-file',$ControlsFile) }
    if ($FocusRegion) {
        if ($FocusRegion.Length -ne 4) { throw '-FocusRegion requires x,y,width,height in normalized preview coordinates.' }
        $arguments+='--focus-region'
        $arguments+=@($FocusRegion | ForEach-Object { $_.ToString('R',[Globalization.CultureInfo]::InvariantCulture) })
    }
}
if ($Action -eq 'crop') {
    if (!$ImageId -or !$OutFile) { throw 'Provide -ImageId, coordinates, dimensions and -OutFile.' }
    $arguments+=@($ImageId,$X,$Y,$Width,$Height,'--out',$OutFile)
}
& (Join-Path $root '.venv\Scripts\python.exe') @arguments
exit $LASTEXITCODE
