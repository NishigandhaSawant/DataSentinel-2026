# export-for-ai.ps1
# Creates a lean zip of DataSentinel optimized for AI analysis.
# Run from project root: powershell -ExecutionPolicy Bypass -File .\export-for-ai.ps1

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$exportDir   = Join-Path $projectRoot "_ai_export"
$zipName     = "DataSentinel-ai-export.zip"
$zipPath     = Join-Path $projectRoot $zipName

# Clean up previous exports
if (Test-Path $exportDir) { Remove-Item $exportDir -Recurse -Force }
if (Test-Path $zipPath)   { Remove-Item $zipPath -Force }

Write-Host ""
Write-Host "Gathering source files..." -ForegroundColor Cyan

# Get all git-tracked files
$allFiles = git -C $projectRoot ls-files

# Exclusion patterns
$excludePatterns = @(
    '\.png$',
    '\.jpg$',
    '\.jpeg$',
    '\.gif$',
    '\.ico$',
    '\.svg$',
    '\.webp$',
    '\.woff2?$',
    '\.ttf$',
    '\.eot$',
    '\.pdf$',
    'package-lock\.json$',
    '\.tsbuildinfo$',
    'next-env\.d\.ts$'
)

$includedFiles = [System.Collections.ArrayList]@()
$excludedFiles = [System.Collections.ArrayList]@()

foreach ($file in $allFiles) {
    $excluded = $false
    foreach ($pattern in $excludePatterns) {
        if ($file -match $pattern) {
            $excluded = $true
            [void]$excludedFiles.Add($file)
            break
        }
    }
    if (-not $excluded) {
        [void]$includedFiles.Add($file)
    }
}

$incCount = $includedFiles.Count
$excCount = $excludedFiles.Count
Write-Host "Including $incCount files, excluding $excCount files" -ForegroundColor Green

if ($excCount -gt 0) {
    Write-Host ""
    Write-Host "Excluded:" -ForegroundColor Yellow
    foreach ($f in $excludedFiles) {
        Write-Host "   - $f" -ForegroundColor DarkGray
    }
}

# Copy included files preserving directory structure
foreach ($file in $includedFiles) {
    $src = Join-Path $projectRoot $file
    $dst = Join-Path $exportDir $file
    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) {
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    }
    Copy-Item $src $dst
}

# Calculate total size
$totalBytes = 0
Get-ChildItem $exportDir -Recurse -File | ForEach-Object { $totalBytes += $_.Length }
$sizeMB = [math]::Round($totalBytes / 1MB, 2)
$sizeKB = [math]::Round($totalBytes / 1KB, 0)
Write-Host ""
Write-Host "Total export size: $sizeKB KB ($sizeMB MB uncompressed)" -ForegroundColor Cyan

# Create zip
Compress-Archive -Path (Join-Path $exportDir "*") -DestinationPath $zipPath -Force

$zipSizeKB = [math]::Round((Get-Item $zipPath).Length / 1KB, 0)
Write-Host "Created: $zipName ($zipSizeKB KB compressed)" -ForegroundColor Green

# Cleanup temp directory
Remove-Item $exportDir -Recurse -Force

Write-Host ""
Write-Host "Upload '$zipName' to Claude, Gemini, or ChatGPT for analysis." -ForegroundColor Magenta
Write-Host ""
