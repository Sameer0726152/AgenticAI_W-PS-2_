# Demo helper for student-api-demo.
#   .\scripts\reset_demo.ps1 add     -> copy the prepared tests in, commit, push   (the live demo step)
#   .\scripts\reset_demo.ps1 reset   -> remove tests/, commit, push                (back to the starting state)
param(
    [Parameter(Mandatory = $true)][ValidateSet("add", "reset")][string]$Action,
    [string]$DemoRepo = "C:\Users\sameer\student-api-demo",
    [string]$TestsSource = "C:\Users\sameer\Desktop\demo-change\tests"
)

$ErrorActionPreference = "Stop"
Push-Location $DemoRepo
try {
    git pull --quiet
    if ($Action -eq "add") {
        if (Test-Path tests) { Write-Host "tests/ already exists - run 'reset' first."; exit 1 }
        Copy-Item -Recurse $TestsSource tests
        git add tests
        git commit -m "Add API tests"
    } else {
        if (-not (Test-Path tests)) { Write-Host "No tests/ folder - already reset."; exit 0 }
        git rm -r --quiet tests
        git commit -m "Remove tests (demo reset)"
    }
    git push --quiet
    Write-Host "Pushed: $(git log -1 --format='%h %s')"
} finally {
    Pop-Location
}
