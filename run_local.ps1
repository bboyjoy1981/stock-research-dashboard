$arguments = @('-m', 'streamlit', 'run', (Join-Path $PSScriptRoot 'app.py'), '--server.address', '127.0.0.1', '--server.port', '8505')
if ($env:STOCK_PYTHON) {
    & $env:STOCK_PYTHON @arguments
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.11 @arguments
} else {
    & python @arguments
}
