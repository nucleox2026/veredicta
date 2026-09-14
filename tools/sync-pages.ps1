param(
    [string]$PagesRoot = "",
    [string]$ProductionApiBaseUrl = "https://veredicta-api.onrender.com"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $projectRoot "frontend"

if ([string]::IsNullOrWhiteSpace($PagesRoot)) {
    $PagesRoot = Join-Path (Split-Path -Parent $projectRoot) "veredicta-pages"
}

if (-not (Test-Path $frontendRoot)) {
    throw "Frontend não encontrado: $frontendRoot"
}

if (-not (Test-Path $PagesRoot)) {
    New-Item -ItemType Directory -Path $PagesRoot | Out-Null
}

# O frontend de desenvolvimento pode apontar para localhost.
# Nunca propagamos esse config local para o espelho de produção.
$existingPagesConfigPath = Join-Path $PagesRoot "assets\js\config.js"
$existingPagesConfig = $null

if (Test-Path $existingPagesConfigPath) {
    $existingPagesConfig = Get-Content $existingPagesConfigPath -Raw
}

$pages = @(
    "index.html",
    "historico.html",
    "processo.html"
)

foreach ($page in $pages) {
    $sourcePage = Join-Path $frontendRoot $page
    $targetPage = Join-Path $PagesRoot $page
    Copy-Item $sourcePage $targetPage -Force
}

$targetAssets = Join-Path $PagesRoot "assets"
if (Test-Path $targetAssets) {
    Remove-Item $targetAssets -Recurse -Force
}

$sourceAssets = Join-Path $frontendRoot "assets"
Copy-Item $sourceAssets $targetAssets -Recurse -Force

$targetConfigPath = Join-Path $PagesRoot "assets\js\config.js"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (-not [string]::IsNullOrWhiteSpace($existingPagesConfig)) {
    [System.IO.File]::WriteAllText(
        $targetConfigPath,
        $existingPagesConfig,
        $utf8NoBom
    )
}
else {
    $productionConfig = @"
window.VEREDICTA_CONFIG = {
  API_BASE_URL: "$ProductionApiBaseUrl",
  GOOGLE_CLIENT_ID: ""
};
"@

    [System.IO.File]::WriteAllText(
        $targetConfigPath,
        $productionConfig,
        $utf8NoBom
    )
}

$legacyFiles = @(
    "analises.js",
    "app.js",
    "config.js",
    "processo.js",
    "styles.css",
    "djen-valores.js"
)

foreach ($legacy in $legacyFiles) {
    $path = Join-Path $PagesRoot $legacy
    if (Test-Path $path) {
        Remove-Item $path -Force
    }
}

Write-Host "Frontend sincronizado com sucesso:" -ForegroundColor Green
Write-Host "  origem:  $frontendRoot"
Write-Host "  destino: $PagesRoot"
Write-Host "  config de produção preservado em assets/js/config.js"
Write-Host "O diretório .git do repositório de Pages não é alterado."
