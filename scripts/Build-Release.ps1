# Build and verify a payload-only portable ZIP; never include game/runtime caches.
# Python/PyInstaller are development prerequisites. Outputs and logs stay in the chosen output folder.
[CmdletBinding()]
param([string]$OutputDir, [string]$Python)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $OutputDir) { $OutputDir = Join-Path $repo 'dist' }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
[IO.Directory]::CreateDirectory($OutputDir) | Out-Null

# Skip Windows Store aliases and use a real installed interpreter without changing PATH.
if (-not $Python) {
    $candidates = @(Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    $Python = $candidates | Where-Object { $_ -notlike '*\WindowsApps\*' -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $Python) { throw 'No working Python found. Install Python 3.12 or pass -Python with its executable path.' }
$Python = (Resolve-Path -LiteralPath $Python).Path
$version = (& $Python (Join-Path $repo 'app\dlss5_aio.py') --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Cannot read the application version.' }
$buildRoot = Join-Path $repo ('.build\' + [guid]::NewGuid().ToString('N'))
$payload = Join-Path $buildRoot ('DLSS5-AIO-v' + $version)
[IO.Directory]::CreateDirectory($payload) | Out-Null

# Freeze from the committed spec; large publisher DLLs remain runtime downloads.
Push-Location $repo
try {
    & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $buildRoot 'frozen') --workpath (Join-Path $buildRoot 'work') app/aio.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
} finally { Pop-Location }
$exe = Join-Path $buildRoot 'frozen\DLSS5-AIO.exe'
Copy-Item -LiteralPath $exe -Destination $payload
foreach ($name in @('README.md', 'START-HERE.txt', 'CHANGELOG.md', 'LICENSE', 'LICENSE.md', 'CREDITS.md')) {
    Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $payload
}
$notices = Join-Path $payload 'licenses'
[IO.Directory]::CreateDirectory($notices) | Out-Null
Copy-Item -LiteralPath (Join-Path $repo 'app\UPSTREAM-LICENSE.txt') -Destination (Join-Path $notices 'Autopilot-MIT.txt')
$pythonRoot = Split-Path -Parent $Python
foreach ($pair in @(@('LICENSE.txt', 'Python-LICENSE.txt'), @('tcl\tcl8.6\license.terms', 'Tcl-LICENSE.txt'), @('tcl\tk8.6\license.terms', 'Tk-LICENSE.txt'))) {
    $notice = Join-Path $pythonRoot $pair[0]
    # CPython's Windows distribution embeds Tcl's notice in its full license.
    if (-not (Test-Path -LiteralPath $notice) -and $pair[1] -eq 'Tcl-LICENSE.txt') {
        $notice = Join-Path $pythonRoot 'LICENSE.txt'
        if ((Get-Content -LiteralPath $notice -Raw) -notmatch 'Tcl/Tk') { throw 'Python license does not include the Tcl notice.' }
    }
    if (-not (Test-Path -LiteralPath $notice)) { throw ('Required runtime license missing: ' + $pair[0]) }
    Copy-Item -LiteralPath $notice -Destination (Join-Path $notices $pair[1])
}

# The shipped docs' relative source links need the referenced text alongside them.
[IO.Directory]::CreateDirectory((Join-Path $payload 'docs')) | Out-Null
foreach ($name in @('AUDIT.md', 'RUNTIME-SOURCES.md')) { Copy-Item -LiteralPath (Join-Path $repo ('docs\' + $name)) -Destination (Join-Path $payload 'docs') }
Copy-Item -LiteralPath (Join-Path $repo 'app\UPSTREAM.md') -Destination (Join-Path $notices 'UPSTREAM.md')
[IO.Directory]::CreateDirectory((Join-Path $payload 'app')) | Out-Null
foreach ($name in @('UPSTREAM.md', 'UPSTREAM-LICENSE.txt')) { Copy-Item -LiteralPath (Join-Path $repo ('app\' + $name)) -Destination (Join-Path $payload 'app') }
$packReadme = @"
DLSS 5 AIO $version

Run DLSS5-AIO.exe, then scan or add a game.
Use runtimes for compatible existing NVIDIA/AMD/Intel DLL updates.
Open a game for installation preview, neural-rendering routes, diagnostics and uninstall.
Verified backups and recovery records protect originals and later personal edits.
Older records without hashes require manual review; an incomplete uninstall retains its record and backups.
Close the game and other mod managers before changing it.

Log: %LOCALAPPDATA%\dlss5-aio\aio.log
Detailed logging: help > debug logging, or --debug.
Source, illustrated documentation and validation: https://github.com/SenjuWoo/dlss5-aio
Licenses: LICENSE, LICENSE.md and licenses/.
This ZIP contains no NVIDIA/AMD/Intel DLLs or third-party installers.
The faster NR model announced October 13 is scheduled for October 16.
"@
[IO.File]::WriteAllText((Join-Path $payload 'README.txt'), $packReadme, (New-Object Text.UTF8Encoding($false)))
[IO.File]::WriteAllText((Join-Path $payload 'README.md'), $packReadme, (New-Object Text.UTF8Encoding($false)))
$zip = Join-Path $OutputDir ('DLSS5-AIO-v' + $version + '-win-x64.zip')
Compress-Archive -Path $payload -DestinationPath $zip -Force
Copy-Item -LiteralPath (Join-Path $payload 'DLSS5-AIO.exe') -Destination (Join-Path $OutputDir 'DLSS5-AIO.exe') -Force
$sums = @()
foreach ($artifact in @((Join-Path $OutputDir 'DLSS5-AIO.exe'), $zip)) {
    $sums += ((Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLower() + '  ' + [IO.Path]::GetFileName($artifact))
}
[IO.File]::WriteAllLines((Join-Path $OutputDir 'SHA256SUMS.txt'), $sums, (New-Object Text.UTF8Encoding($false)))
& $Python (Join-Path $repo 'scripts\verify_package.py') $zip --version $version
if ($LASTEXITCODE -ne 0) { throw 'Fresh package verification failed.' }
Write-Output ('Verified release: ' + $zip)
