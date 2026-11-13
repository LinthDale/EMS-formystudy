$ErrorActionPreference='Stop'
$nodeRuntime='C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$serverFile=Join-Path $PSScriptRoot 'server.mjs'
$listeners=Get-NetTCPConnection -LocalPort 4179 -State Listen -ErrorAction SilentlyContinue
if($listeners){
    $processIds=@($listeners.OwningProcess | Select-Object -Unique)
    if($processIds.Count -ne 1){throw 'Port 4179 has unexpected owners'}
    $running=Get-CimInstance Win32_Process -Filter ('ProcessId='+$processIds[0])
    if(!$running.CommandLine.Contains($serverFile)){throw 'Port 4179 belongs to another program'}
    Write-Output 'EMS publication already running: https://synaiq-ai.com/ems/#Monitor'
    return
}
$tailAddress='100.114.126.85'
if(!(Get-NetIPAddress -IPAddress $tailAddress -ErrorAction SilentlyContinue)){throw 'Tailscale is not connected at the expected address'}
$health=Invoke-WebRequest -Uri 'http://127.0.0.1:8003/api/auth/session' -SkipHttpErrorCheck -TimeoutSec 5
if($health.StatusCode -notin @(200,401)){throw 'EMS BFF unavailable; start the existing EMS Docker services first'}
$process=Start-Process -FilePath $nodeRuntime -ArgumentList ('"'+$serverFile+'"') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'server.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'server.stderr.log')
$process.Id | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'server.pid')
Start-Sleep -Milliseconds 700
if($process.HasExited){throw 'EMS publication did not start; inspect server.stderr.log'}
Write-Output ('EMS publication running, PID '+$process.Id+': https://synaiq-ai.com/ems/#Monitor')

