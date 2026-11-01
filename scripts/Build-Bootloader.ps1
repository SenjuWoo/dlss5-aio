# Rebuild PyInstaller's Windows bootloader from the pinned sdist, with MSVC.
#
# Why: the prebuilt run.exe/runw.exe shipped in the PyInstaller wheel are what
# Microsoft Defender's ML signatures flag on every build of this app
# (Trojan:Win32/Bearfoos.B!ml, and Wacatac.B!ml on the single-file era). The
# same source compiled here produces different bytes and scans clean on the
# same signature set. PyInstaller documents replacing the bootloader binaries
# in its own package as the supported way to use a self-built one.
#
# Best effort by design: a machine without MSVC keeps the stock bootloader and
# this script says so. The caller (Build-Release.ps1) logs which one was used,
# so a release built with the stock stub is visible, never silent.
[CmdletBinding()]
param([string]$Python, [string]$CacheDir)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
# Build in the user's local app data, not under the repo: this repo can live
# on a mapped drive, and the long-path prefix bsdtar uses for deep archive
# members is rejected there ("Invalid argument").
if (-not $CacheDir) {
    $root = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $env:TEMP }
    $CacheDir = Join-Path $root 'dlss5-aio-bootloader'
}

# The sdist this was verified against. A different version is a different
# source tree: refuse rather than compile something nobody checked.
$SDIST_SHA256 = '4e7ed495fccb9974d47cf72ef8cffc92afa05d60bc265c5585a68f3d229ca8d1'

function Say([string]$text) { Write-Host $text }

if (-not $Python) {
    $candidates = @(Get-Command python.exe -All -ErrorAction SilentlyContinue | ForEach-Object Source)
    $Python = $candidates | Where-Object { $_ -notlike '*\WindowsApps\*' -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $Python) { Write-Warning 'No Python found; keeping the stock PyInstaller bootloader.'; return }
$Python = (Resolve-Path -LiteralPath $Python).Path

$requirements = Get-Content -LiteralPath (Join-Path $repo 'requirements-build.txt') -Raw
if ($requirements -notmatch 'PyInstaller==([0-9.]+)') {
    Write-Warning 'requirements-build.txt names no PyInstaller version; keeping the stock bootloader.'
    return
}
$version = $Matches[1]

# Where the installed PyInstaller keeps the binaries it will actually use.
$pkg = (& $Python -c 'import PyInstaller, os; print(os.path.dirname(PyInstaller.__file__))' | Out-String).Trim()
if (-not $pkg -or -not (Test-Path -LiteralPath $pkg)) {
    Write-Warning 'PyInstaller is not installed for this interpreter; keeping the stock bootloader.'
    return
}
$target = Join-Path $pkg 'bootloader\Windows-64bit-intel'

# A compiler is the one hard requirement. Find MSVC the way every other tool
# does, through vswhere, and give up quietly when it is not there.
$vcvars = $null
$vswhere = $null
if (${env:ProgramFiles(x86)}) {
    $candidate = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path -LiteralPath $candidate) { $vswhere = $candidate }
}
if ($vswhere) {
    $install = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Out-String).Trim()
    if ($install) {
        $candidate = Join-Path $install 'VC\Auxiliary\Build\vcvars64.bat'
        if (Test-Path -LiteralPath $candidate) { $vcvars = $candidate }
    }
}
if (-not $vcvars) {
    foreach ($guess in @(
        (Join-Path ${env:ProgramFiles} 'Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'),
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'))) {
        if (Test-Path -LiteralPath $guess) { $vcvars = $guess; break }
    }
}
if (-not $vcvars) {
    Write-Warning 'No MSVC found (vcvars64.bat); keeping the stock PyInstaller bootloader. Defender may flag the build.'
    return
}

[IO.Directory]::CreateDirectory($CacheDir) | Out-Null
$tarball = Join-Path $CacheDir ("pyinstaller-$version.tar.gz")
if (-not (Test-Path -LiteralPath $tarball)) {
    Say "  fetching PyInstaller $version sdist"
    & $Python -m pip download "pyinstaller==$version" --no-binary :all: --no-deps -d $CacheDir --quiet
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Could not download the PyInstaller sdist; keeping the stock bootloader.'; return }
    $downloaded = Get-ChildItem -LiteralPath $CacheDir -Filter 'pyinstaller-*.tar.gz' | Select-Object -First 1
    if ($downloaded -and $downloaded.FullName -ne $tarball) { Move-Item -LiteralPath $downloaded.FullName -Destination $tarball -Force }
}
if (-not (Test-Path -LiteralPath $tarball)) { Write-Warning 'The PyInstaller sdist is missing; keeping the stock bootloader.'; return }

$hash = (Get-FileHash -LiteralPath $tarball -Algorithm SHA256).Hash.ToLower()
if ($hash -ne $SDIST_SHA256) {
    Write-Warning "The PyInstaller sdist hash is $hash, not the verified $SDIST_SHA256; keeping the stock bootloader."
    return
}

$tree = Join-Path $CacheDir "pyinstaller-$version"
$bootloader = Join-Path $tree 'bootloader'
if (-not (Test-Path -LiteralPath (Join-Path $bootloader 'waf'))) {
    if (Test-Path -LiteralPath $tree) { Remove-Item -LiteralPath $tree -Recurse -Force }
    Say "  extracting to $tree"
    # The Windows bsdtar by full path: a PATH that starts with MSYS's GNU tar
    # reads "Z:\..." as a remote host and fails with "Cannot connect to Z:".
    # Only the bootloader subtree is taken: the sdist's news/ and AppImage
    # test data carry symlinks, which bsdtar cannot create on Windows.
    & (Join-Path $env:SystemRoot 'System32\tar.exe') -xzf $tarball -C $CacheDir `
        "pyinstaller-$version/bootloader" "pyinstaller-$version/PyInstaller/_shared_with_waf.py"
    $install_dir = Join-Path $tree 'PyInstaller\bootloader\Windows-64bit-intel'
    if ($LASTEXITCODE -eq 0 -and -not (Test-Path -LiteralPath $install_dir)) {
        [IO.Directory]::CreateDirectory($install_dir) | Out-Null
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $bootloader 'waf'))) {
        Write-Warning 'Could not extract the PyInstaller sdist; keeping the stock bootloader.'
        return
    }
}

# waf needs the compiler on PATH, so it runs inside the vcvars environment.
$log = Join-Path $CacheDir 'waf.log'
$cmd = 'call "{0}" >nul && "{1}" waf all' -f $vcvars, $Python
$process = $null
Push-Location $bootloader
try {
    $process = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', $cmd -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $log -RedirectStandardError (Join-Path $CacheDir 'waf.err.log')
} catch {
    Write-Warning "Could not start the bootloader build ($_); keeping the stock bootloader."
} finally { Pop-Location }
if (-not $process) { return }
if ($process.ExitCode -ne 0) {
    Write-Warning "The bootloader build failed (see $log); keeping the stock bootloader."
    return
}

$built = Join-Path $tree 'PyInstaller\bootloader\Windows-64bit-intel'
foreach ($name in @('run.exe', 'runw.exe')) {
    $source = Join-Path $built $name
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Warning "The bootloader build produced no $name; keeping the stock one."
        return
    }
}
# Only now touch the installed package: both files exist and came from waf.
foreach ($name in @('run.exe', 'runw.exe')) {
    Copy-Item -LiteralPath (Join-Path $built $name) -Destination (Join-Path $target $name) -Force
}
foreach ($name in @('run.exe', 'runw.exe')) {
    $h = (Get-FileHash -LiteralPath (Join-Path $target $name) -Algorithm SHA256).Hash.ToLower()
    Say ("  bootloader {0} {1}" -f $name, $h)
}
Say '  PyInstaller bootloader rebuilt from source with MSVC (Defender-clean build)'
