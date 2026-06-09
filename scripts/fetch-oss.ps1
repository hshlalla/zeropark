[CmdletBinding()]
param(
    [switch]$Core,
    [switch]$All,
    [string[]]$Repos = @(),
    [string]$Destination = "external"
)

$ErrorActionPreference = "Stop"

$sources = @(
    @{ id = "deer-flow"; url = "https://github.com/bytedance/deer-flow.git"; branch = "main"; tier = "core" },
    @{ id = "dify"; url = "https://github.com/langgenius/dify.git"; branch = "main"; tier = "core" },
    @{ id = "presenton"; url = "https://github.com/presenton/presenton.git"; branch = "main"; tier = "core" },
    @{ id = "crawl4ai"; url = "https://github.com/unclecode/crawl4ai.git"; branch = "main"; tier = "core" },
    @{ id = "browser-use"; url = "https://github.com/browser-use/browser-use.git"; branch = "main"; tier = "core" },
    @{ id = "openmanus"; url = "https://github.com/FoundationAgents/OpenManus.git"; branch = "main"; tier = "optional" },
    @{ id = "searxng"; url = "https://github.com/searxng/searxng.git"; branch = "master"; tier = "optional" },
    @{ id = "coze-studio"; url = "https://github.com/coze-dev/coze-studio.git"; branch = "main"; tier = "optional" },
    @{ id = "ui-tars-desktop"; url = "https://github.com/bytedance/UI-TARS-desktop.git"; branch = "main"; tier = "optional" }
)

if (-not $Core -and -not $All -and $Repos.Count -eq 0) {
    $Core = $true
}

if ($All) {
    $selected = $sources
}
elseif ($Core) {
    $selected = $sources | Where-Object { $_.tier -eq "core" }
}
else {
    $repoSet = @{}
    foreach ($repo in $Repos) {
        $repoSet[$repo.ToLowerInvariant()] = $true
    }

    $selected = $sources | Where-Object { $repoSet.ContainsKey($_.id.ToLowerInvariant()) }
    $missing = $Repos | Where-Object {
        $candidate = $_.ToLowerInvariant()
        -not ($sources | Where-Object { $_.id.ToLowerInvariant() -eq $candidate })
    }

    if ($missing.Count -gt 0) {
        throw "Unknown repo id(s): $($missing -join ', ')"
    }
}

$root = (Resolve-Path ".").Path
$destinationRoot = Join-Path $root $Destination
New-Item -ItemType Directory -Force -Path $destinationRoot | Out-Null

foreach ($source in $selected) {
    $target = Join-Path $destinationRoot $source.id

    if (Test-Path $target) {
        Write-Host "skip $($source.id): $target already exists"
        continue
    }

    Write-Host "clone $($source.id) -> $target"
    git clone --depth 1 --branch $source.branch $source.url $target
}

Write-Host "done"

