[CmdletBinding()]
param(
    [string]$GatewayUrl = "http://localhost:8080",
    [string]$SearxngUrl = "http://localhost:8888"
)

$ErrorActionPreference = "Continue"

$targets = @(
    @{ name = "gateway"; url = "$GatewayUrl/health" },
    @{ name = "gateway-services"; url = "$GatewayUrl/services" },
    @{ name = "searxng"; url = "$SearxngUrl/" }
)

foreach ($target in $targets) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $target.url -TimeoutSec 5
        Write-Host ("ok   {0,-18} {1} {2}" -f $target.name, [int]$response.StatusCode, $target.url)
    }
    catch {
        Write-Host ("fail {0,-18} {1}" -f $target.name, $target.url)
    }
}

