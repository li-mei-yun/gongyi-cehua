$curvePlotPython = 'C:\Users\MGA\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$curvePlotScript = 'C:\Users\MGA\Documents\ChatGPT\工艺策划\label-studio-setup\batch-curves\plot_server.py'
$curvePlotHealth = 'http://127.0.0.1:8091/health'

try {
    $curvePlotResponse = Invoke-WebRequest -Uri $curvePlotHealth -UseBasicParsing -TimeoutSec 2
    if ($curvePlotResponse.Content -eq 'tightening-curve-plot-v1') {
        Write-Host '拧紧曲线实时绘图服务已经在运行：http://127.0.0.1:8091'
        exit 0
    }
    throw '端口 8091 被其它服务占用。'
} catch {
    if ($_.Exception.Message -eq '端口 8091 被其它服务占用。') { throw }
}

$curvePlotProcess = Start-Process -FilePath $curvePlotPython -ArgumentList @($curvePlotScript) -WindowStyle Hidden -PassThru
$curvePlotDeadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $curvePlotDeadline) {
    Start-Sleep -Milliseconds 300
    try {
        $curvePlotResponse = Invoke-WebRequest -Uri $curvePlotHealth -UseBasicParsing -TimeoutSec 2
        if ($curvePlotResponse.Content -eq 'tightening-curve-plot-v1') {
            Write-Host "拧紧曲线实时绘图服务已启动，进程号 $($curvePlotProcess.Id)：http://127.0.0.1:8091"
            exit 0
        }
        throw '端口 8091 返回了其它内容。'
    } catch {
        if ($curvePlotProcess.HasExited) { throw "绘图服务启动失败，退出码 $($curvePlotProcess.ExitCode)。" }
    }
}
throw '绘图服务在10秒内没有就绪。'
