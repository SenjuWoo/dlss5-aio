<#
  DLSS-DLL-Refresher.ps1  -  part of DLSS 5 AIO (folder 06)

  Finds every nvngx_dlss*.dll on your PC and brings it up to the pack's
  official version. No injection, no hooks, no proxy DLLs - it only swaps
  NVIDIA's own runtime files, which is what anti-cheat cares about.

  Dry run by default (just reports). Nothing is written without -Apply.
  Every file it replaces is backed up to "_dlss_originals\" next to it first,
  and -Restore puts them all back.

  Usage
    .\DLSS-DLL-Refresher.ps1                          # report only (all fixed drives)
    .\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games'        # report only (one folder)
    .\DLSS-DLL-Refresher.ps1 -Apply                   # do it
    .\DLSS-DLL-Refresher.ps1 -Apply -IncludeNR        # also nvngx_dlssnr.dll (DLSS 5 runtime)
    .\DLSS-DLL-Refresher.ps1 -Restore                 # put the originals back
    .\DLSS-DLL-Refresher.ps1 -SelfTest                # prove it works, then exit
#>
[CmdletBinding()]
param(
    [string[]]$Roots = @(),
    [string]$SourceDir,
    [string[]]$Exclude = @(),
    [switch]$Apply,
    [switch]$IncludeNR,
    [switch]$Restore,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Continue'
# "-File" passes a comma-joined string as ONE argument - split it, and drop blanks
$Roots = @($Roots | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
$Exclude = @($Exclude | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
$script:Names = @('nvngx_dlss.dll', 'nvngx_dlssg.dll', 'nvngx_dlssd.dll')
if ($IncludeNR) { $script:Names += 'nvngx_dlssnr.dll' }
# never touch other tools' backups - rewriting one silently breaks their restore
$script:SkipPath = @('_dlss_originals', '_DLSS5_Backup', 'dlss5-backup', 'DLSS-Backup', '\Backup\',
                     '\Windows\', '\WindowsApps\', '$Recycle.Bin', 'System Volume Information')

# ---------- helpers ----------

function Get-NumVersion {
    param([string]$s)
    if (-not $s) { return $null }
    $t = $s -replace ',', '.'            # 310,9,1,0 -> 310.9.1.0
    $m = [regex]::Match($t, '^\d+(\.\d+)*')
    if (-not $m.Success) { return $null }
    try { return [version]$m.Value } catch { return $null }
}

function Get-PEMachine {
    param([string]$path)
    try {
        $fs = [IO.File]::OpenRead($path)
        try {
            $br = New-Object IO.BinaryReader($fs)
            if ($br.ReadUInt16() -ne 0x5A4D) { return $null }   # 'MZ'
            $fs.Position = 0x3C
            $pe = $br.ReadInt32()
            $fs.Position = $pe
            if ($br.ReadUInt32() -ne 0x00004550) { return $null } # 'PE\0\0'
            return $br.ReadUInt16()                                # 0x8664 = x64, 0x14C = x86
        } finally { $fs.Close() }
    } catch { return $null }
}

function Get-FileVersionText {
    param([string]$path)
    try { return (Get-Item -LiteralPath $path).VersionInfo.FileVersion } catch { return $null }
}

function Get-Sha {
    param([string]$path)
    try { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } catch { return $null }
}

function Resolve-Source {
    param([string]$dir)
    if (-not $dir) {
        $here = Split-Path -Parent $MyInvocation.MyCommand.Path
        $dir  = Join-Path (Split-Path -Parent $here) '01-Official-NVIDIA-DLLs'
    }
    if (-not (Test-Path -LiteralPath $dir)) {
        throw "Source folder not found: $dir`nRun this from inside the DLSS 5 AIO pack (folder 06), or pass -SourceDir."
    }
    $nr = Join-Path (Split-Path -Parent $dir) '02-DLSS5-Neural-Rendering'
    $map = @{}
    foreach ($n in $script:Names) {
        $cand = Join-Path $dir $n
        if (-not (Test-Path -LiteralPath $cand)) { $cand = Join-Path $nr $n }
        if (Test-Path -LiteralPath $cand) {
            $map[$n] = [pscustomobject]@{
                Path    = (Resolve-Path -LiteralPath $cand).Path
                Version = (Get-NumVersion (Get-FileVersionText $cand))
                VerText = (Get-FileVersionText $cand)
                Sha     = (Get-Sha $cand)
                Machine = (Get-PEMachine $cand)
            }
        }
    }
    if ($map.Count -eq 0) { throw "No nvngx_dlss*.dll found in $dir" }
    return $map
}

function Get-ScanRoots {
    param([string[]]$r)
    if ($r.Count -gt 0) { return $r }
    return (Get-PSDrive -PSProvider FileSystem |
            Where-Object { $_.Free -ne $null -and $_.Root -match '^[A-Za-z]:\\$' } |
            ForEach-Object { $_.Root })
}

function Find-Targets {
    param([string[]]$scanRoots, [string[]]$names)
    $found = New-Object System.Collections.ArrayList
    foreach ($root in $scanRoots) {
        if (-not (Test-Path -LiteralPath $root)) {
            Write-Host ("  !! root not found, skipped: {0}" -f $root) -ForegroundColor Yellow
            continue
        }
        Write-Host ("  scanning {0} ..." -f $root) -ForegroundColor DarkGray
        foreach ($n in $names) {
            Get-ChildItem -LiteralPath $root -Recurse -File -Filter $n -Force -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $p = $_.FullName
                    $skip = $false
                    foreach ($s in $script:SkipPath) { if ($p -like "*$s*") { $skip = $true; break } }
                    if (-not $skip) { foreach ($e in $Exclude) { if ($p -like "*$e*") { $skip = $true; break } } }
                    if (-not $skip) { [void]$found.Add($p) }
                }
        }
    }
    return $found
}

function Invoke-Refresher {
    param($map, [string[]]$roots)

    $rows = New-Object System.Collections.ArrayList
    foreach ($p in (Find-Targets -scanRoots $roots -names $script:Names)) {
        $name = Split-Path -Leaf $p
        if (-not $map.ContainsKey($name)) { continue }
        $src = $map[$name]

        $row = [pscustomobject]@{
            Path = $p; Name = $name
            Have = (Get-FileVersionText $p); Want = $src.VerText
            Action = ''; Note = ''
        }

        if ((Get-PEMachine $p) -ne $src.Machine) {
            $row.Action = 'SKIP'; $row.Note = '32-bit file - the pack ships the 64-bit build'
        }
        else {
            $have = Get-NumVersion $row.Have
            $same = ((Get-Sha $p) -eq $src.Sha)
            if ($same)                       { $row.Action = 'SKIP'; $row.Note = 'already current' }
            elseif ($null -eq $have)         { $row.Action = 'SKIP'; $row.Note = 'version unreadable - check by hand' }
            elseif ($have -gt $src.Version)  { $row.Action = 'SKIP'; $row.Note = 'newer than the pack - left alone' }
            elseif ($have -eq $src.Version)  { $row.Action = 'SWAP'; $row.Note = 'same version, different build' }
            else                             { $row.Action = 'SWAP'; $row.Note = 'older' }
        }

        if ($row.Action -eq 'SWAP' -and $Apply) {
            $dir = Split-Path -Parent $p
            $bak = Join-Path $dir '_dlss_originals'
            try {
                if (-not (Test-Path -LiteralPath $bak)) { New-Item -ItemType Directory -Path $bak -Force | Out-Null }
                $keep = Join-Path $bak $name
                if (-not (Test-Path -LiteralPath $keep)) { Copy-Item -LiteralPath $p -Destination $keep -Force }
                Copy-Item -LiteralPath $src.Path -Destination $p -Force
                $row.Note += ' -> replaced (original kept)'
            } catch {
                $row.Action = 'FAIL'
                $row.Note = "locked or denied: $($_.Exception.Message.Split([char]10)[0])"
            }
        }
        [void]$rows.Add($row)
    }
    return $rows
}

function Invoke-Restore {
    param([string[]]$roots)
    $n = 0
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -Recurse -Directory -Filter '_dlss_originals' -Force -ErrorAction SilentlyContinue |
            ForEach-Object {
                $dest = Split-Path -Parent $_.FullName
                Get-ChildItem -LiteralPath $_.FullName -File | ForEach-Object {
                    try {
                        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dest $_.Name) -Force
                        Write-Host ("  restored {0}" -f (Join-Path $dest $_.Name)) -ForegroundColor Green
                        $n++
                    } catch { Write-Host ("  FAILED {0}: {1}" -f $_.Name, $_.Exception.Message) -ForegroundColor Red }
                }
            }
    }
    Write-Host ("`nRestored {0} file(s)." -f $n) -ForegroundColor Cyan
}

function Show-Report {
    param($rows)
    $swap = @($rows | Where-Object Action -eq 'SWAP')
    $skip = @($rows | Where-Object Action -eq 'SKIP')
    $fail = @($rows | Where-Object Action -eq 'FAIL')

    if ($rows.Count -eq 0) { Write-Host "`nNo nvngx_dlss*.dll found under the scanned roots." -ForegroundColor Yellow; return }

    Write-Host "`nNOTE: online games with anti-cheat (Battlefield, Marvel Rivals, GTA Online, ...) can" -ForegroundColor Yellow
    Write-Host "      flag a swapped DLL. Skip those folders with -Exclude before you -Apply." -ForegroundColor Yellow

    Write-Host "`n=== Files that need the update ===" -ForegroundColor Cyan
    if ($swap.Count -eq 0) { Write-Host "  (none - everything is current)" -ForegroundColor Green }
    else { $swap | Format-Table @{L='have';E={$_.Have}}, @{L='want';E={$_.Want}}, @{L='note';E={$_.Note}}, Path -AutoSize | Out-String | Write-Host }

    Write-Host "=== Left alone ===" -ForegroundColor DarkGray
    $skip | Format-Table @{L='have';E={$_.Have}}, @{L='note';E={$_.Note}}, Path -AutoSize | Out-String | Write-Host
    if ($fail.Count -gt 0) {
        Write-Host "=== Failed ===" -ForegroundColor Red
        $fail | Format-Table @{L='note';E={$_.Note}}, Path -AutoSize | Out-String | Write-Host
    }

    Write-Host ("Scanned: {0} file(s) | to update: {1} | untouched: {2} | failed: {3}" -f $rows.Count, $swap.Count, $skip.Count, $fail.Count) -ForegroundColor Cyan
    if (-not $Apply -and $swap.Count -gt 0) {
        Write-Host "`nDry run - nothing was written. Re-run with -Apply to replace them (originals are kept in _dlss_originals\)." -ForegroundColor Yellow
    }
}

# ---------- self test ----------

function Invoke-SelfTest {
    param($map)
    Write-Host "Self test: fixture in a temp folder" -ForegroundColor Cyan
    $fix = Join-Path $env:TEMP ('dlssrefresher_' + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory -Path $fix -Force | Out-Null
    $name = 'nvngx_dlss.dll'
    $src = $map[$name]

    # 1. identical copy -> must be left alone
    $cur = Join-Path $fix 'current'; New-Item -ItemType Directory -Path $cur -Force | Out-Null
    Copy-Item -LiteralPath $src.Path -Destination (Join-Path $cur $name)

    # 2. same version, one byte appended -> must be swapped, with a backup
    $mod = Join-Path $fix 'modified'; New-Item -ItemType Directory -Path $mod -Force | Out-Null
    $bytes = [IO.File]::ReadAllBytes($src.Path)
    [IO.File]::WriteAllBytes((Join-Path $mod $name), ($bytes + [byte]0))

    # 3. 32-bit PE stub named like a DLSS dll -> must be skipped, not overwritten
    $x86 = Join-Path $fix 'x86'; New-Item -ItemType Directory -Path $x86 -Force | Out-Null
    $b = New-Object byte[] 256
    $b[0] = 0x4D; $b[1] = 0x5A
    $b[0x3C] = 0x40
    $b[0x40] = 0x50; $b[0x41] = 0x45
    $b[0x44] = 0x4C; $b[0x45] = 0x01        # machine 0x014C = x86
    [IO.File]::WriteAllBytes((Join-Path $x86 $name), $b)

    $rows = Invoke-Refresher -map $map -roots @($fix)
    $byPath = @{}; foreach ($r in $rows) { $byPath[(Split-Path -Leaf (Split-Path -Parent $r.Path))] = $r }

    $script:ok = $true
    function Assert($cond, $msg) { if ($cond) { Write-Host "  ok   $msg" -ForegroundColor Green } else { Write-Host "  FAIL $msg" -ForegroundColor Red; $script:ok = $false } }

    Assert ($byPath['current'].Action -eq 'SKIP')  'identical file is left alone'
    Assert ($byPath['modified'].Action -eq 'SWAP') 'same-version different-build is flagged'
    Assert ($byPath['x86'].Action -eq 'SKIP' -and $byPath['x86'].Note -like '*32-bit*') '32-bit file is skipped'

    $script:Apply = $true
    $rows2 = Invoke-Refresher -map $map -roots @($fix)
    Assert ((Get-Sha (Join-Path $mod $name)) -eq $src.Sha) 'apply: file now matches the official build'
    Assert (Test-Path -LiteralPath (Join-Path $mod '_dlss_originals\nvngx_dlss.dll')) 'apply: original was backed up'
    Assert ((Get-Sha (Join-Path $x86 $name)) -ne $src.Sha) 'apply: 32-bit file untouched'
    $script:Apply = $false

    Invoke-Restore -roots @($fix) | Out-Null
    Assert ((Get-Sha (Join-Path $mod $name)) -ne $src.Sha) 'restore: original put back'

    Remove-Item -LiteralPath $fix -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ""
    if ($script:ok) { Write-Host "SELF TEST PASSED" -ForegroundColor Green; exit 0 }
    Write-Host "SELF TEST FAILED" -ForegroundColor Red; exit 1
}

# ---------- main ----------

$map = Resolve-Source -dir $SourceDir
Write-Host "Official set:" -ForegroundColor Cyan
foreach ($k in $map.Keys) { Write-Host ("  {0,-18} {1}" -f $k, $map[$k].VerText) }

if ($SelfTest) { Invoke-SelfTest -map $map }

$roots = Get-ScanRoots -r $Roots
if ($Restore) {
    Write-Host "`nRestoring originals under: $($roots -join ', ')" -ForegroundColor Cyan
    Invoke-Restore -roots $roots
    exit 0
}

Write-Host "`nScanning: $($roots -join ', ')" -ForegroundColor Cyan
if (-not $Apply) { Write-Host "DRY RUN - nothing will be written. Add -Apply to make changes.`n" -ForegroundColor Yellow }
$rows = Invoke-Refresher -map $map -roots $roots
Show-Report -rows $rows