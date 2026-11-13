$ErrorActionPreference='Stop'
$pidFile=Join-Path $PSScriptRoot 'server.pid'
if(!(Test-Path -LiteralPath $pidFile)){Write-Output 'No publication PID file';return}
$publicationPid=[int](Get-Content -LiteralPath $pidFile -Raw)
$process=Get-CimInstance Win32_Process -Filter ('ProcessId='+$publicationPid)
if(!$process){Write-Output 'Publication process is not running';return}
$serverFile=Join-Path $PSScriptRoot 'server.mjs'
if(!$process.CommandLine -or !$process.CommandLine.Contains($serverFile)){throw 'PID was reused by another process; nothing stopped'}
Stop-Process -Id $publicationPid
Write-Output 'EMS publication stopped. Existing backend and local 4178 preview are unchanged.'
