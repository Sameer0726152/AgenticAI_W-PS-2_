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
    $tracked = git ls-files tests  # what git knows about; ignores leftover __pycache__ folders
    if ($Action -eq "add") {
        if ($tracked) { Write-Host "tests/ is already committed - run 'reset' first."; exit 1 }
        if (Test-Path tests) { Remove-Item -Recurse -Force tests }
        Copy-Item -Recurse $TestsSource tests
        Get-ChildItem tests -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
        git add tests
        git commit -m "Add API tests"
    } else {
        if (-not $tracked) {
            if (Test-Path tests) { Remove-Item -Recurse -Force tests }
            Write-Host "No committed tests/ - already reset."
            exit 0
        }
        git rm -r --quiet tests
        if (Test-Path tests) { Remove-Item -Recurse -Force tests }
        git commit -m "Remove tests (demo reset)"
    }
    git push --quiet
    Write-Host "Pushed: $(git log -1 --format='%h %s')"
} finally {
    Pop-Location
}
