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
    [switch]$SkipNR,
    [switch]$ForceOnline,
    [switch]$Restore,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Continue'
# "-File" passes a comma-joined string as ONE argument - split it, and drop blanks
$Roots = @($Roots | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
$Exclude = @($Exclude | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
$script:Here = $PSScriptRoot
if (-not $script:Here) { $script:Here = Split-Path -Parent $MyInvocation.MyCommand.Path }
# Everything DLSS-related the pack ships and a game/app may also carry. If the pack starts
# shipping something else, add its filename here or it will be scanned for but never resolved.
$script:Names = @(
    'nvngx_dlss.dll', 'nvngx_dlssg.dll', 'nvngx_dlssd.dll',             # 01 - SR / FrameGen / RayReconstruction
    'nvngx_dlssnr.dll',                                                 # 02 - DLSS 5 neural rendering runtime
    'renodx-dlss5.addon64',                                             # 02 - the DLSS 5 ReShade add-on
    'sl.common.dll', 'sl.dlss.dll', 'sl.dlss_g.dll', 'sl.dlss_nr.dll',  # 01\Streamline-* - Streamline runtime
    'sl.interposer.dll', 'sl.nis.dll', 'sl.pcl.dll', 'sl.reflex.dll',
    'dlss5-feed.addon64', 'dlss5-feed.addon32', 'DLSS5_Feed.fx'         # 04 - the feeder
)
if ($SkipNR) { $script:Names = @($script:Names | Where-Object { $_ -ne 'nvngx_dlssnr.dll' }) }
# Kernel-anti-cheat online games: skipped by default, because a swapped DLL can read as
# tampering. Matched against the path with spaces/punctuation stripped, so "Marvel Rivals"
# and "MarvelRivals" both hit. -ForceOnline overrides.
$script:Online = @('fortnite', 'marvelrivals', 'starcitizen', 'battlefield', 'callofduty',
                   'overwatch', 'thefinals', 'helldivers', 'palworld', 'haloinfinite',
                   'halothemasterchief', 'grandtheftautov', 'gtavenhanced', 'blackdesert',
                   'destiny2', 'valorant', 'apexlegends', 'escapefromtarkov', 'pubg',
                   'rainbowsix', 'warframe', 'eldenring', 'thedivision')
# never touch other tools' backups - rewriting one silently breaks their restore
$script:SkipPath = @('_dlss_originals', '_DLSS5_Backup', 'dlss5-backup', 'DLSS-Backup', '\Backup\',
                     '\Windows\', '\WindowsApps\', '$Recycle.Bin', 'System Volume Information')

# ---------- helpers ----------

function Get-NumVersion {
    param([string]$s)
    if (-not $s) { return $null }
    if ($s -notmatch '\d') { return $null }   # no digits at all -> unreadable, caller skips
    # Count EVERY segment; a build tag is 0, not a full stop:
    #   310,9,1,0  -> 310.9.1.0
    #   310.8.SF.0 -> 310.8.0.0  (same release line as 310,8,0,0 - the hash decides between builds)
    # Stopping at 'SF' used to make the production build look OLDER than the community one.
    $parts = @()
    foreach ($seg in ($s -split '[,.]')) {
        $n = 0
        if ($seg -match '^\d+$') { $n = [int]$seg }
        $parts += $n
        if ($parts.Count -eq 4) { break }
    }
    while ($parts.Count -lt 4) { $parts += 0 }
    try { return [version]($parts -join '.') } catch { return $null }
}

# Hashing is the expensive part of a scan (tens of MB per DLL); read each file once at most.
$script:ShaCache = @{}
function Get-ShaCached {
    param([string]$p)
    if (-not $script:ShaCache.ContainsKey($p)) { $script:ShaCache[$p] = (Get-Sha $p) }
    return $script:ShaCache[$p]
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

# strip spaces and punctuation so "Marvel Rivals" and "MarvelRivals" compare equal
function Get-Norm {
    param([string]$s)
    if (-not $s) { return '' }
    return ($s -replace '[\s_\-\.\*]', '').ToLower()
}

# Look for an extracted pack near this script (the repo carries the tool, not the binaries).
# Breadth-first, name-filtered and capped: a pack's folder is always DLSS5-AIO*, so we only
# descend into names that can lead to one. Unfiltered this walks 400 directories (~20s on a
# slow drive) to find what the filter reaches in about fifteen.
function Find-Pack {
    param([string]$start, [int]$maxDirs = 400)
    if (-not $start -or -not (Test-Path -LiteralPath $start)) { return $null }
    $q = New-Object System.Collections.Queue
    $q.Enqueue($start)
    $seen = 0; $best = $null; $bestVer = $null
    while ($q.Count -gt 0 -and $seen -lt $maxDirs) {
        $d = $q.Dequeue(); $seen++
        if ((Split-Path -Leaf $d) -eq '01-Official-NVIDIA-DLLs') {
            $dll = Join-Path $d 'nvngx_dlss.dll'
            if (Test-Path -LiteralPath $dll) {
                # two packs can share a subtree - the newest DLLs win, never the first found
                $v = Get-NumVersion (Get-FileVersionText $dll)
                if ($null -ne $v -and ($null -eq $bestVer -or $v -gt $bestVer)) { $best = $d; $bestVer = $v }
                continue        # a pack has no nested pack; don't spend budget inside it
            }
        }
        foreach ($c in (Get-ChildItem -LiteralPath $d -Directory -Force -ErrorAction SilentlyContinue)) {
            if ($c.Name -match '^(01-Official-NVIDIA-DLLs|.*dlss)' -and
                $c.Name -notmatch '^(\$Recycle|System Volume|Windows$|WindowsApps|Program Files)') { $q.Enqueue($c.FullName) }
        }
    }
    return $best
}

function Resolve-Source {
    param([string]$dir)
    if (-not $dir) {
        $dir = Join-Path (Split-Path -Parent $script:Here) '01-Official-NVIDIA-DLLs'
    }
    $pack = Split-Path -Parent $dir
    if (-not (Test-Path -LiteralPath $dir) -or -not (Test-Path -LiteralPath (Join-Path $dir 'nvngx_dlss.dll'))) {
        # not next to us - look for an extracted pack nearby before giving up.
        # One budget per ancestor: a single shared budget gets eaten by the first
        # (often huge) ancestor and never reaches a pack nested three deep.
        $walk = @(); $up = $script:Here
        for ($i = 0; $i -lt 3; $i++) {
            $up = Split-Path -Parent $up
            if (-not $up) { break }
            $walk += $up
        }
        $found = $null; $foundVer = $null
        foreach ($root in $walk) {
            $hit = Find-Pack -start $root
            if (-not $hit) { continue }
            $v = Get-NumVersion (Get-FileVersionText (Join-Path $hit 'nvngx_dlss.dll'))
            if ($null -ne $v -and ($null -eq $foundVer -or $v -gt $foundVer)) { $found = $hit; $foundVer = $v }
        }
        if ($found) {
            Write-Host ("  using the pack found nearby: {0}  (nvngx_dlss {1})" -f $found, $foundVer) -ForegroundColor DarkGray
            $dir  = $found
            $pack = Split-Path -Parent $dir
        }
    }
    if (-not (Test-Path -LiteralPath $dir)) {
        throw ("Can't find the pack's DLL folder:`n  {0}`n`nExtract the DLSS 5 AIO release and run folder 06 from inside it, or point at the folder that holds the official DLLs:`n  .\DLSS-DLL-Refresher.ps1 -SourceDir 'D:\DLSS5-AIO\01-Official-NVIDIA-DLLs'" -f $dir)
    }
    # the pack spreads its files over 01 (NVIDIA + Streamline), 02 (DLSS 5) and 04 (feeder)
    $search = @($dir)
    foreach ($sub in @('02-DLSS5-Neural-Rendering', '04-DLSS5-Feeder')) {
        $p = Join-Path $pack $sub
        if (Test-Path -LiteralPath $p) { $search += $p }
    }
    Get-ChildItem -LiteralPath $dir -Directory -Filter 'Streamline-*' -ErrorAction SilentlyContinue |
        ForEach-Object { $search += $_.FullName }

    $map = @{}
    foreach ($n in $script:Names) {
        foreach ($d in $search) {
            $cand = Join-Path $d $n
            if (Test-Path -LiteralPath $cand) {
                $map[$n] = [pscustomobject]@{
                    Path    = (Resolve-Path -LiteralPath $cand).Path
                    Version = (Get-NumVersion (Get-FileVersionText $cand))
                    VerText = (Get-FileVersionText $cand)
                    Machine = (Get-PEMachine $cand)
                }
                break
            }
        }
    }
    if ($map.Count -eq 0) {
        throw ("Found the folder, but no DLSS files inside it:`n  {0}`n`nThat is what the source repo looks like - it carries the tool, not the binaries.`nExtract the release pack (DLSS5-AIO-v*.7z.001) and run folder 06 from there." -f $dir)
    }
    # The feeder/add-on files live in the repo too, so a repo run can resolve *something* while
    # the actual NVIDIA DLLs are missing. Without them there is no source of truth - say so.
    $core = @($script:Names | Where-Object { $_ -like 'nvngx_*' -and $map.ContainsKey($_) })
    if ($core.Count -eq 0) {
        throw ("The pack's NVIDIA DLLs are not here:`n  {0}`n`nThis looks like the source repo, which carries the tool but not the binaries.`nExtract the release pack (DLSS5-AIO-v*.7z.001) and run folder 06 from inside it, or point at the DLLs:`n  .\DLSS-DLL-Refresher.ps1 -SourceDir 'D:\DLSS5-AIO\01-Official-NVIDIA-DLLs'" -f $dir)
    }
    $missing = @($script:Names | Where-Object { -not $map.ContainsKey($_) })
    if ($missing.Count -gt 0) {
        Write-Host ("  note: not in this pack, so not checked: {0}" -f ($missing -join ', ')) -ForegroundColor DarkYellow
    }
    return $map
}

function Get-ScanRoots {
    param([string[]]$r)
    if ($r.Count -gt 0) { return $r }
    return (Get-PSDrive -PSProvider FileSystem |
            Where-Object { $_.Free -ne $null -and $_.Root -match '^[A-Za-z]:\\$' } |
            ForEach-Object { $_.Root })
}

# Walk a root and keep only the filenames we care about. Get-ChildItem builds a FileInfo for
# every file it meets (44s over 900k files); raw .NET enumeration of names costs 14s, and the
# per-directory try/catch keeps one unreadable folder from aborting the whole scan.
function Get-FilesByName {
    param([string]$root, [hashtable]$want)
    $stack = New-Object System.Collections.Stack
    $stack.Push($root)
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        try {
            foreach ($f in [IO.Directory]::EnumerateFiles($d)) {
                if ($want.ContainsKey([IO.Path]::GetFileName($f))) { $f }
            }
            foreach ($s in [IO.Directory]::EnumerateDirectories($d)) {
                # junctions and symlinks can loop back on themselves
                try { if (([IO.File]::GetAttributes($s) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue } } catch { continue }
                $stack.Push($s)
            }
        }
        catch { }
    }
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
        # one walk per root, matching names as we go: 16 filtered walks of a 500k-file tree
        # is the difference between ~1 minute and ~7 for the same answer.
        $want = @{}
        foreach ($n in $names) { $want[$n.ToLower()] = $true }
        Get-FilesByName -root $root -want $want | ForEach-Object {
            $p = $_
            $skip = $false
            foreach ($s in $script:SkipPath) { if ($p -like "*$s*") { $skip = $true; break } }
            if (-not $skip) {
                $np = Get-Norm $p
                foreach ($e in $Exclude) { if ($p -like "*$e*" -or $np -like "*$(Get-Norm $e)*") { $skip = $true; break } }
            }
            if (-not $skip) { [void]$found.Add($p) }
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

        if (-not $ForceOnline) {
            $np = Get-Norm $p
            $hit = $null
            foreach ($a in $script:Online) { if ($np -like "*$a*") { $hit = $a; break } }
            if ($hit) { $row.Action = 'SKIP'; $row.Note = 'online game with kernel anti-cheat - skipped (safe default)' }
        }
        if ($row.Action -eq '' -and (Get-PEMachine $p) -ne $src.Machine) {
            $row.Action = 'SKIP'; $row.Note = '32-bit file - the pack ships the 64-bit build'
        }
        elseif ($row.Action -eq '') {
            $have = Get-NumVersion $row.Have
            if ($null -ne $have -and $null -ne $src.Version -and $have -ne $src.Version) {
                # the version alone settles it - no need to read a byte
                if ($have -gt $src.Version) { $row.Action = 'SKIP'; $row.Note = 'newer than the pack - left alone' }
                else                        { $row.Action = 'SWAP'; $row.Note = 'older' }
            }
            else {
                # equal or unreadable versions: only content can tell them apart, so hash now.
                # Hashing up front costs 200 MB of reads per scan for an answer nothing used.
                if ((Get-ShaCached $p) -eq (Get-ShaCached $src.Path)) { $row.Action = 'SKIP'; $row.Note = 'already current' }
                elseif ($null -eq $src.Version) { $row.Action = 'SWAP'; $row.Note = 'content differs' }
                elseif ($null -eq $have)        { $row.Action = 'SKIP'; $row.Note = 'version unreadable - check by hand' }
                else                            { $row.Action = 'SWAP'; $row.Note = 'same version, different build' }
            }
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
    return ,$rows   # comma keeps a 1-row result a collection; otherwise .Count comes back null
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

    if ($rows.Count -eq 0) { Write-Host "`nNothing to report: no file the pack ships a source for was found under the scanned roots." -ForegroundColor Yellow; return }

    Write-Host "`nNOTE: online games with kernel anti-cheat (Fortnite, Marvel Rivals, Star Citizen, ...)" -ForegroundColor Yellow
    Write-Host "      are skipped by default - they show in 'left alone' with the reason. -ForceOnline" -ForegroundColor Yellow
    Write-Host "      overrides that; -Exclude skips extra folders by name." -ForegroundColor Yellow

    Write-Host "`n=== Files that need the update ===" -ForegroundColor Cyan
    if ($swap.Count -eq 0) { Write-Host "  (none - everything is current)" -ForegroundColor Green }
    else {
        # full paths on their own line: a Format-Table column silently truncates them
        foreach ($r in $swap) {
            Write-Host ("  {0} -> {1}   {2}" -f $r.Have, $r.Want, $r.Note)
            Write-Host ("    {0}" -f $r.Path) -ForegroundColor DarkGray
        }
    }

    Write-Host "=== Left alone ===" -ForegroundColor DarkGray
    foreach ($r in $skip) { Write-Host ("  {0,-14} {1,-48} {2}" -f $r.Have, $r.Note, $r.Path) }
    if ($fail.Count -gt 0) {
        Write-Host "=== Failed ===" -ForegroundColor Red
        foreach ($r in $fail) { Write-Host ("  {0}   {1}" -f $r.Note, $r.Path) }
    }

    $online = @($skip | Where-Object { $_.Note -like '*anti-cheat*' })
    Write-Host ("Scanned: {0} file(s) | to update: {1} | current: {2} | skipped online: {3} | failed: {4}" -f $rows.Count, $swap.Count, ($skip.Count - $online.Count), $online.Count, $fail.Count) -ForegroundColor Cyan
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

    # 4. an online game folder -> must be skipped by default (anti-cheat), swapped only with -ForceOnline
    $ac = Join-Path $fix 'MarvelRivals'; New-Item -ItemType Directory -Path $ac -Force | Out-Null
    [IO.File]::WriteAllBytes((Join-Path $ac $name), ($bytes + [byte]0))

    $rows = Invoke-Refresher -map $map -roots @($fix)
    $byPath = @{}; foreach ($r in $rows) { $byPath[(Split-Path -Leaf (Split-Path -Parent $r.Path))] = $r }

    $script:ok = $true
    function Assert($cond, $msg) { if ($cond) { Write-Host "  ok   $msg" -ForegroundColor Green } else { Write-Host "  FAIL $msg" -ForegroundColor Red; $script:ok = $false } }

    Assert ($byPath['current'].Action -eq 'SKIP')  'identical file is left alone'
    Assert ($byPath['modified'].Action -eq 'SWAP') 'same-version different-build is flagged'
    Assert ($byPath['x86'].Action -eq 'SKIP' -and $byPath['x86'].Note -like '*32-bit*') '32-bit file is skipped'
    Assert ($byPath['MarvelRivals'].Action -eq 'SKIP' -and $byPath['MarvelRivals'].Note -like '*anti-cheat*') 'online game folder is skipped by default'

    $script:Apply = $true
    $rows2 = Invoke-Refresher -map $map -roots @($fix)
    Assert ((Get-Sha (Join-Path $mod $name)) -eq (Get-ShaCached $src.Path)) 'apply: file now matches the official build'
    Assert (Test-Path -LiteralPath (Join-Path $mod '_dlss_originals\nvngx_dlss.dll')) 'apply: original was backed up'
    Assert ((Get-Sha (Join-Path $x86 $name)) -ne (Get-ShaCached $src.Path)) 'apply: 32-bit file untouched'
    Assert ((Get-Sha (Join-Path $ac $name)) -ne (Get-ShaCached $src.Path)) 'apply: online game folder left untouched'
    $script:ForceOnline = $true
    Invoke-Refresher -map $map -roots @($fix) | Out-Null
    Assert ((Get-Sha (Join-Path $ac $name)) -eq (Get-ShaCached $src.Path)) '-ForceOnline overrides the online skip'
    $script:ForceOnline = $false
    Assert ((Get-Norm 'Marvel Rivals') -eq (Get-Norm 'MarvelRivals')) 'name matching ignores spaces'
    $one = Invoke-Refresher -map $map -roots @($cur)
    Assert ($one.Count -eq 1) 'a single-row result still reports a count'

    # version parsing: a build tag must not make a release line look newer/older than it is
    Assert ((Get-NumVersion '310.8.SF.0') -eq (Get-NumVersion '310,8,0,0')) 'build-tagged version equals its numeric form'
    Assert ((Get-NumVersion '310.8.SF.0') -lt (Get-NumVersion '310.9.1.0')) 'build-tagged version sorts below a newer release'
    Assert ((Get-NumVersion '310,9,1,0') -gt (Get-NumVersion '310.7.129.0')) 'numeric versions sort correctly'
    Assert ($null -eq (Get-NumVersion 'not-a-version')) 'unreadable version returns null'
    $script:Apply = $false

    Invoke-Restore -roots @($fix) | Out-Null
    Assert ((Get-Sha (Join-Path $mod $name)) -ne (Get-ShaCached $src.Path)) 'restore: original put back'

    Remove-Item -LiteralPath $fix -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host ""
    if ($script:ok) { Write-Host "SELF TEST PASSED" -ForegroundColor Green; exit 0 }
    Write-Host "SELF TEST FAILED" -ForegroundColor Red; exit 1
}

# ---------- main ----------

$map = $null
try { $map = Resolve-Source -dir $SourceDir }
catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    exit 1
}
Write-Host "Official set:" -ForegroundColor Cyan
foreach ($k in ($map.Keys | Sort-Object)) { Write-Host ("  {0,-22} {1}" -f $k, $map[$k].VerText) }
Write-Host ("  ({0} file(s) will be used as the source of truth)" -f $map.Count) -ForegroundColor DarkGray

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