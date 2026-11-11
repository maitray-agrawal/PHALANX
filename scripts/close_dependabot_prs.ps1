<#
.SYNOPSIS
    Closes open Dependabot pull requests and leaves a reason note.

.DESCRIPTION
    Lists open pull requests created by app/dependabot and closes them
    using the GitHub CLI (gh), commenting with @dependabot close.
#>

[CmdletBinding()]
param()

$ghInstalled = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghInstalled) {
    Write-Warning "GitHub CLI (gh) is not installed or not in PATH."
    Write-Host "Please install gh or manually close Dependabot pull requests in the GitHub web UI."
    exit 1
}

Write-Host "Fetching open pull requests authored by Dependabot..." -ForegroundColor Cyan

$prsJson = gh pr list --author "app/dependabot" --state open --json number,title | ConvertFrom-Json

if (-not $prsJson -or $prsJson.Count -eq 0) {
    Write-Host "No open Dependabot pull requests found." -ForegroundColor Green
    exit 0
}

Write-Host "Found $($prsJson.Count) open Dependabot pull request(s):" -ForegroundColor Yellow

foreach ($pr in $prsJson) {
    Write-Host "Closing PR #$($pr.number): $($pr.title)..."
    gh pr comment $pr.number --body "@dependabot close"
    gh pr close $pr.number --delete-branch
}

Write-Host "All specified Dependabot PRs processed." -ForegroundColor Green
