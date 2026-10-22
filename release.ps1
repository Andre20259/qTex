# Makes a new QTeX release.
#
#   .\release.bat 1.2.0        (or double-click release.bat and type the version)
#
# 1. Checks you have no uncommitted changes and the version is new.
# 2. Moves the notes under "## [Unreleased]" in CHANGELOG.md to a "## [1.2.0] - <date>" section.
# 3. Sets APP_VERSION in texeditor.py.
# 4. Commits, creates the tag v1.2.0 and pushes both to GitHub.
# GitHub Actions then builds the installer and publishes the release (see .github/workflows/release.yml).

param(
    [Parameter(Mandatory = $true, HelpMessage = "New version number, e.g. 1.2.0")]
    [string]$Version,
    [switch]$NoPush
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding $false

function Fail($msg) { Write-Host "`n$msg" -ForegroundColor Red; exit 1 }
function RunGit { & git @args; if ($LASTEXITCODE) { Fail "git $($args -join ' ') failed." } }
# Runs git quietly and returns $true on success. (Local "Continue" so Windows PowerShell 5.1
# doesn't turn git's stderr into a terminating error.)
function GitOk { $ErrorActionPreference = "Continue"; & git @args *> $null; return ($LASTEXITCODE -eq 0) }

$Version = $Version.Trim().TrimStart("v", "V")
if ($Version -notmatch '^\d+\.\d+\.\d+$') { Fail "Version must look like 1.2.0 (got '$Version')." }
$tag = "v$Version"

# ---- checks
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail "git isn't installed. Get it from https://git-scm.com/download/win" }
if (-not (GitOk rev-parse --is-inside-work-tree)) { Fail "This folder isn't a git repository." }
if (git status --porcelain) { Fail "You have uncommitted changes. Commit them first (or stash them), then run this again." }
if (GitOk rev-parse -q --verify "refs/tags/$tag") { Fail "Tag $tag already exists. Choose a new version number." }
if (-not $NoPush) {
    if (-not (GitOk remote get-url origin)) { Fail "No GitHub remote yet. Add it with: git remote add origin https://github.com/<you>/<repo>.git" }
}

# ---- CHANGELOG.md
$changelogPath = Join-Path $PSScriptRoot "CHANGELOG.md"
$changelog = [IO.File]::ReadAllText($changelogPath)
$nl = if ($changelog.Contains("`r`n")) { "`r`n" } else { "`n" }
if ($changelog -notmatch "(?m)^## \[$([regex]::Escape($Version))\]") {
    $m = [regex]::Match($changelog, '(?ms)^## \[Unreleased\][^\r\n]*\r?\n(.*?)(?=^## \[|\z)')
    if (-not $m.Success -or -not $m.Groups[1].Value.Trim()) {
        Fail "Write what changed under '## [Unreleased]' in CHANGELOG.md first (and commit it). Those notes become the release notes."
    }
    $date = Get-Date -Format "yyyy-MM-dd"
    $heading = [regex]::Match($changelog, '(?m)^## \[Unreleased\][^\r\n]*').Value
    $changelog = $changelog.Replace($heading, "## [Unreleased]$nl$nl## [$Version] - $date")
    [IO.File]::WriteAllText($changelogPath, $changelog, $utf8)
    Write-Host "CHANGELOG.md: Unreleased notes moved to [$Version] - $date"
}

# ---- APP_VERSION
$srcPath = Join-Path $PSScriptRoot "texeditor.py"
$src = [IO.File]::ReadAllText($srcPath)
$newSrc = [regex]::Replace($src, 'APP_VERSION\s*=\s*"[^"]*"', "APP_VERSION = `"$Version`"")
if ($newSrc -eq $src -and $src -notmatch "APP_VERSION = `"$([regex]::Escape($Version))`"") { Fail "APP_VERSION not found in texeditor.py." }
if ($newSrc -ne $src) {
    [IO.File]::WriteAllText($srcPath, $newSrc, $utf8)
    Write-Host "texeditor.py: APP_VERSION = $Version"
}

# ---- commit, tag, push
if (git status --porcelain) {
    RunGit add CHANGELOG.md texeditor.py
    RunGit commit -q -m "Release $tag"
}
RunGit tag -a $tag -m "QTeX $Version"
Write-Host "Created tag $tag" -ForegroundColor Green

if ($NoPush) {
    Write-Host "`nNot pushed (-NoPush). When ready:  git push origin HEAD $tag"
    exit 0
}
RunGit push origin HEAD
RunGit push origin $tag

$url = (git remote get-url origin).Trim() -replace '^git@github\.com:', 'https://github.com/' -replace '\.git$', ''
Write-Host "`nPushed $tag. GitHub is now building the release (takes about 5 minutes):" -ForegroundColor Green
Write-Host "  Progress: $url/actions"
Write-Host "  Release:  $url/releases/tag/$tag"
