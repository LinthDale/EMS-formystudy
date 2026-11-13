$ErrorActionPreference='Stop'
$nodeRuntime='C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
if(Get-NetTCPConnection -LocalPort 4178 -State Listen -ErrorAction SilentlyContinue){throw 'Port 4178 already in use. Open http://127.0.0.1:4178/#Monitor or inspect the owning process.'}
$serverProcess=Start-Process -FilePath $nodeRuntime -ArgumentList ('"'+(Join-Path $PSScriptRoot 'server.mjs')+'"') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'server-node.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server-node.stderr.log')
$serverProcess.Id | Set-Content (Join-Path $PSScriptRoot 'server.pid')
Write-Output ('Preview: http://127.0.0.1:4178/#Monitor (PID '+$serverProcess.Id+')')