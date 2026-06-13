# export-for-ai.ps1
# Creates a single .txt bundle of all DataSentinel source code for AI upload.
# Run from project root: powershell -ExecutionPolicy Bypass -File .\export-for-ai.ps1

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$outputFile  = Join-Path $projectRoot "DataSentinel-ai-bundle.txt"

# Clean previous output
if (Test-Path $outputFile) { Remove-Item $outputFile -Force }

Write-Host ""
Write-Host "Gathering source files..." -ForegroundColor Cyan

# Get all git-tracked files
$allFiles = git -C $projectRoot ls-files

# Exclusion patterns - files that waste AI tokens
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
    'next-env\.d\.ts$',
    'export-for-ai\.ps1$'
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

# Build the single-file bundle
$header = @"
================================================================================
DATASENTINEL - AI CODE BUNDLE
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Files: $incCount source files
================================================================================

This file contains the entire DataSentinel source code concatenated into a
single text file for AI analysis. Each file is delimited by markers.

Read CLAUDE.md (included below) first for a complete project overview.

TABLE OF CONTENTS:
$( ($includedFiles | ForEach-Object { "  - $_" }) -join "`n" )

================================================================================

"@

Set-Content -Path $outputFile -Value $header -Encoding UTF8

foreach ($file in $includedFiles) {
    $filePath = Join-Path $projectRoot $file
    $separator = "=" * 80
    $fileHeader = @"

$separator
FILE: $file
$separator

"@
    Add-Content -Path $outputFile -Value $fileHeader -Encoding UTF8

    try {
        $content = Get-Content -Path $filePath -Raw -Encoding UTF8
        Add-Content -Path $outputFile -Value $content -Encoding UTF8
    } catch {
        Add-Content -Path $outputFile -Value "[Binary or unreadable file - skipped]" -Encoding UTF8
    }
}

# Add footer
$footer = @"

================================================================================
END OF DATASENTINEL AI CODE BUNDLE
================================================================================
"@
Add-Content -Path $outputFile -Value $footer -Encoding UTF8

# Stats
$totalSize = (Get-Item $outputFile).Length
$sizeKB = [math]::Round($totalSize / 1KB, 0)
$sizeMB = [math]::Round($totalSize / 1MB, 2)

Write-Host ""
Write-Host "Bundle created: DataSentinel-ai-bundle.txt ($sizeKB KB / $sizeMB MB)" -ForegroundColor Green
Write-Host "Upload this single .txt file to Gemini, Claude, or ChatGPT." -ForegroundColor Magenta
Write-Host ""
