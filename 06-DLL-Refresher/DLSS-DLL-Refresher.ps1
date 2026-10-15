<#
  DLSS-DLL-Refresher.ps1  -  part of DLSS 5 AIO (folder 06)

  Updates existing managed files from a hash-verified release pack. DLL
  replacement is not guaranteed compatible with every game or anti-cheat.
  Optional debug log: %LOCALAPPDATA%\DLSS5AIO\Logs\refresher.log.

  Dry run by default (just reports). Nothing is written without -Apply.
  Every file it replaces is backed up to "_dlss_originals\" next to it first,
  and -Restore puts them all back.

  Usage
    .\DLSS-DLL-Refresher.ps1                          # report only (all fixed drives)
    .\DLSS-DLL-Refresher.ps1 -Roots 'D:\Games'        # report only (one folder)
    .\DLSS-DLL-Refresher.ps1 -Apply                   # do it
    .\DLSS-DLL-Refresher.ps1 -Apply -SkipNR           # leave nvngx_dlssnr.dll alone
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
    [switch]$SelfTest,
    [switch]$DebugLog
)

$ErrorActionPreference = 'Stop'
# "-File" passes a comma-joined string as ONE argument - split it, and drop blanks
$Roots = @($Roots | ForEach-Object { if (Test-Path -LiteralPath $_) { $_ } else { $_ -split ',' } } | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
$Exclude = @($Exclude | ForEach-Object { $_ -split ',' } | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
$script:Here = $PSScriptRoot
if (-not $script:Here) { $script:Here = Split-Path -Parent $MyInvocation.MyCommand.Path }
$script:SourceRoots = @((Split-Path -Parent $script:Here))
$script:ScanErrors = New-Object System.Collections.ArrayList
$script:LogPath = Join-Path $env:LOCALAPPDATA 'DLSS5AIO\Logs\refresher.log'
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
$script:AllNames = $script:Names
if ($SkipNR) { $script:Names = @($script:Names | Where-Object { $_ -ne 'nvngx_dlssnr.dll' }) }
# Known online-title paths are skipped conservatively; this list does not detect anti-cheat.
# Matching ignores spaces/punctuation. -ForceOnline overrides this heuristic.
$script:Online = @('fortnite', 'marvelrivals', 'starcitizen', 'battlefield', 'callofduty',
                   'overwatch', 'thefinals', 'helldivers', 'palworld', 'haloinfinite',
                   'halothemasterchief', 'grandtheftautov', 'gtavenhanced', 'blackdesert',
                   'destiny2', 'valorant', 'apexlegends', 'escapefromtarkov', 'pubg',
                   'rainbowsix', 'warframe', 'eldenring', 'thedivision')
# ---------- helpers ----------

function Get-NumVersion {
    param([string]$s)
    if (-not $s) { return $null }
    if ($s -notmatch '^\s*\d+\s*(?:[,.]|$)') { return $null }
    # Count EVERY segment; a build tag is 0, not a full stop:
    #   310,9,1,0  -> 310.9.1.0
    #   310.8.SF.0 -> 310.8.0.0  (same release line as 310,8,0,0 - the hash decides between builds)
    # Stopping at 'SF' used to make the production build look OLDER than the community one.
    $parts = @()
    foreach ($seg in ($s -split '[,.]')) {
        $n = 0
        if ($seg.Trim() -match '^\d+$' -and -not [int]::TryParse($seg.Trim(), [ref]$n)) { return $null }
        $parts += $n
        if ($parts.Count -eq 4) { break }
    }
    while ($parts.Count -lt 4) { $parts += 0 }
    try { return [version]($parts -join '.') } catch { return $null }
}

# Preserve the helper's legacy name while always observing current target bytes.
function Get-ShaCached {
    param([string]$p)
    # Files can change during apply/restore; only source hashes in the resolved map are reused.
    return Get-Sha $p
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
    # A batch-launched Windows PowerShell can inherit PowerShell 7's module path.
    $hash = [Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [IO.File]::OpenRead($path)
        return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-', '')
    } finally {
        if ($stream) { $stream.Dispose() }
        $hash.Dispose()
    }
}

# Record failures even in quiet mode, without making a logging failure hide the real error.
function Write-RefresherLog {
    param([string]$Message, [switch]$Failure)
    if (-not $Failure -and -not $DebugLog) { return }
    try {
        [IO.Directory]::CreateDirectory((Split-Path -Parent $script:LogPath)) | Out-Null
        Add-Content -LiteralPath $script:LogPath -Value ('{0:o} {1}' -f [DateTime]::UtcNow, $Message) -Encoding UTF8
    } catch { Write-Warning ('Cannot write refresher log: ' + $_.Exception.Message) }
}

# Preserve references, backup trees, installed DLSS tools, and complete AI profiles before walking them.
function Test-ProtectedPath {
    param([string]$Path, [switch]$AllowBackup)
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    foreach ($source in $script:SourceRoots) {
        $prefix = [IO.Path]::GetFullPath($source).TrimEnd('\')
        if ($full -eq $prefix -or $full.StartsWith($prefix + '\', [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    foreach ($part in ($full -split '[\\/]')) {
        if ($AllowBackup -and $part -eq '_dlss_originals') { continue }
        if ($part -match '^(?:_dlss_originals|_DLSS5_Backup|dlss5-backup|DLSS-Backup|backups?|Windows|WindowsApps|\$Recycle\.Bin|System Volume Information|\.git|\.claude|\.codex|\.hermes|\.grok|\.kimi(?:-code)?|\.uabs|hermes|models|checkpoints|sessions|profiles|node_modules|\.venv|venv|zz.*)$' -or
            $part -match '^DLSS[\s5_-]*(?:AIO|Autopilot|Swapper|Manager|neuralscreen|Visual)') { return $true }
    }
    foreach ($e in $Exclude) {
        $normalized = Get-Norm $e
        if ($full.IndexOf($e, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or ($normalized -and (Get-Norm $full).Contains($normalized))) { return $true }
    }
    return $false
}

# A selected root or a file link must not escape the tree that was approved for scanning.
function Test-ReparsePath {
    param([string]$Path)
    $walk = [IO.Path]::GetFullPath($Path)
    while ($walk) {
        if ([IO.File]::Exists($walk) -or [IO.Directory]::Exists($walk)) {
            if (([IO.File]::GetAttributes($walk) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $true }
        }
        $parent = [IO.Path]::GetDirectoryName($walk.TrimEnd('\'))
        if ($parent -eq $walk) { break }
        $walk = $parent
    }
    return $false
}

# The ledger proves both the preserved original and the last files this tool installed.
function Read-BackupLedger {
    param([string]$Backup)
    $ledger = @{ SchemaVersion = 1; Files = @{} }
    $path = Join-Path $Backup 'manifest.json'
    if (-not (Test-Path -LiteralPath $path)) { return $ledger }
    if (Test-ReparsePath $path) { throw 'Linked backup manifest is not allowed.' }
    $saved = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    if ($saved.SchemaVersion -ne 1 -or $null -eq $saved.Files) { throw 'Invalid backup manifest.' }
    foreach ($property in $saved.Files.PSObject.Properties) {
        if ($property.Name -notin $script:AllNames) { throw ('Unrecognized backup entry: ' + $property.Name) }
        $record = $property.Value
        if ($record.OriginalSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $record.InstalledSha256 -notmatch '^[0-9a-fA-F]{64}$' -or
            ($record.PendingSha256 -and $record.PendingSha256 -notmatch '^[0-9a-fA-F]{64}$')) { throw 'Invalid backup hashes.' }
        $ledger.Files[$property.Name] = $record
    }
    return $ledger
}

# Replace JSON atomically so an interrupted write cannot invalidate the only recovery record.
function Save-BackupLedger {
    param([string]$Backup, $Ledger)
    $path = Join-Path $Backup 'manifest.json'
    $temp = Join-Path $Backup ([guid]::NewGuid().ToString('N') + '.json.tmp')
    try {
        [IO.File]::WriteAllText($temp, ($Ledger | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
        if (Test-Path -LiteralPath $path) { [IO.File]::Replace($temp, $path, [NullString]::Value) }
        else { [IO.File]::Move($temp, $path) }
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } }
}

# Verify a backup and the current target before an atomic replacement; never clobber later user edits.
function Install-VerifiedFile {
    param([string]$Target, [string]$Source, [string]$ExpectedHash)
    if (Test-ReparsePath $Target) { throw 'Linked target or parent is not writable by the refresher.' }
    $dir = Split-Path -Parent $Target
    $name = Split-Path -Leaf $Target
    $bak = Join-Path $dir '_dlss_originals'
    if (Test-ReparsePath $bak) { throw 'Linked backup directory is not allowed.' }
    [IO.Directory]::CreateDirectory($bak) | Out-Null
    $keep = Join-Path $bak $name
    $ledger = Read-BackupLedger $bak
    $haveHash = Get-Sha $Target
    if (Test-Path -LiteralPath $keep) {
        if (Test-ReparsePath $keep) { throw 'Linked original backup is not allowed.' }
        if (-not $ledger.Files.ContainsKey($name)) { throw 'Untracked legacy backup preserved; recover it manually before applying.' }
        $record = $ledger.Files[$name]
        if ((Get-Sha $keep) -ne $record.OriginalSha256) { throw 'Original backup changed; refusing replacement.' }
        if ($haveHash -notin @($record.OriginalSha256, $record.InstalledSha256, $record.PendingSha256)) { throw 'Target changed outside this tool; refusing replacement.' }
    } else {
        if ($ledger.Files.ContainsKey($name)) { throw 'Original backup missing; refusing replacement.' }
        Copy-Item -LiteralPath $Target -Destination $keep -ErrorAction Stop
        if ((Get-Sha $keep) -ne $haveHash) { throw 'Backup verification failed; target left unchanged.' }
        $record = [pscustomobject]@{ OriginalSha256 = $haveHash; InstalledSha256 = $haveHash; PendingSha256 = $null }
        $ledger.Files[$name] = $record
        Save-BackupLedger $bak $ledger
    }
    $stage = Join-Path $dir ('.' + $name + '.' + [guid]::NewGuid().ToString('N') + '.tmp')
    $rollback = Join-Path $bak ([guid]::NewGuid().ToString('N') + '.rollback')
    $replaced = $false
    $retainRollback = $false
    try {
        Copy-Item -LiteralPath $Source -Destination $stage -ErrorAction Stop
        if ((Get-Sha $stage) -ne $ExpectedHash) { throw 'Source changed or staging copy failed hash verification.' }
        if ((Get-Sha $Target) -ne $haveHash) { throw 'Target changed during staging; refusing replacement.' }
        $record.PendingSha256 = $ExpectedHash
        Save-BackupLedger $bak $ledger
        [IO.File]::Replace($stage, $Target, $rollback)
        $replaced = $true
        if ((Get-Sha $Target) -ne $ExpectedHash) { throw 'Installed file failed hash verification.' }
        $record.InstalledSha256 = $ExpectedHash
        $record.PendingSha256 = $null
        Save-BackupLedger $bak $ledger
        Write-RefresherLog ('Updated and verified: {0}; SHA256={1}' -f $Target, $ExpectedHash)
    } catch {
        if ($replaced) {
            try {
                [IO.File]::Replace($rollback, $Target, [NullString]::Value)
                if ((Get-Sha $Target) -ne $haveHash) { throw 'Rollback verification failed.' }
            } catch {
                $retainRollback = $true
                throw ('Rollback failed; preserve ' + $bak + ' for manual recovery. ' + $_.Exception.Message)
            }
        }
        throw
    } finally {
        foreach ($temporary in @($stage, $rollback)) {
            if ($temporary -eq $rollback -and $retainRollback) { continue }
            if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        }
    }
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
    $explicitSource = -not [string]::IsNullOrWhiteSpace($dir)
    if (-not $dir) {
        $dir = Join-Path (Split-Path -Parent $script:Here) '01-Official-NVIDIA-DLLs'
    }
    $pack = Split-Path -Parent $dir
    if (-not $explicitSource -and (-not (Test-Path -LiteralPath $dir) -or -not (Test-Path -LiteralPath (Join-Path $dir 'nvngx_dlss.dll')))) {
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
    $dir = (Resolve-Path -LiteralPath $dir).Path
    $pack = Split-Path -Parent $dir
    if (Test-ReparsePath $dir) { throw 'A linked source directory is not allowed.' }
    $manifestPath = Join-Path $pack 'SHA256SUMS.txt'
    if (-not (Test-Path -LiteralPath $manifestPath)) { throw ('Source pack needs SHA256SUMS.txt: ' + $pack) }
    $manifest = @{}
    foreach ($line in (Get-Content -LiteralPath $manifestPath)) {
        if ($line -match '^([0-9a-fA-F]{64}) [ *](.+)$') {
            $relative = $Matches[2].Replace('\', '/')
            if ($manifest.ContainsKey($relative)) { throw ('Duplicate source manifest entry: ' + $relative) }
            $manifest[$relative] = $Matches[1]
        }
    }
    $script:SourceRoots += $pack
    # the pack spreads its files over 01 (NVIDIA + Streamline), 02 (DLSS 5) and 04 (feeder)
    $search = @($dir)
    foreach ($sub in @('02-DLSS5-Neural-Rendering', '04-DLSS5-Feeder')) {
        $p = Join-Path $pack $sub
        if (Test-Path -LiteralPath $p) { $search += $p }
    }
    Get-ChildItem -LiteralPath $dir -Directory -Filter 'Streamline-*' -ErrorAction Stop |
        Sort-Object @{ Expression = { Get-NumVersion ($_.Name -replace '^Streamline-', '') }; Descending = $true }, Name |
        ForEach-Object { $search += $_.FullName }

    $map = @{}
    foreach ($n in $script:Names) {
        foreach ($d in $search) {
            $cand = Join-Path $d $n
            if (Test-Path -LiteralPath $cand) {
                if (Test-ReparsePath $cand) { throw ('Linked source file is not allowed: ' + $cand) }
                $relative = $cand.Substring($pack.Length).TrimStart('\').Replace('\', '/')
                $hash = Get-Sha $cand
                if (-not $manifest.ContainsKey($relative) -or $hash -ne $manifest[$relative]) { throw ('Source hash missing or mismatched in SHA256SUMS.txt: ' + $relative) }
                $machine = Get-PEMachine $cand
                if ($n -ne 'DLSS5_Feed.fx') {
                    $expectedMachine = 0x8664
                    if ($n -eq 'dlss5-feed.addon32') { $expectedMachine = 0x014c }
                    if ($machine -ne $expectedMachine) { throw ('Invalid source PE architecture: ' + $relative) }
                }
                $version = Get-NumVersion (Get-FileVersionText $cand)
                if ($n -like 'nvngx_*' -and $null -eq $version) { throw ('Source NVIDIA DLL has no readable version: ' + $relative) }
                $map[$n] = [pscustomobject]@{
                    Path    = (Resolve-Path -LiteralPath $cand).Path
                    Version = $version
                    VerText = (Get-FileVersionText $cand)
                    Machine = $machine
                    Sha256  = $hash
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
    return ([IO.DriveInfo]::GetDrives() | Where-Object { $_.DriveType -eq [IO.DriveType]::Fixed -and $_.IsReady } |
            ForEach-Object { $_.RootDirectory.FullName })
}

# Walk a root and keep only the filenames we care about. Get-ChildItem builds a FileInfo for
# every file it meets (44s over 900k files); raw .NET enumeration of names costs 14s, and the
# per-directory try/catch keeps one unreadable folder from aborting the whole scan.
function Get-FilesByName {
    param([string]$root, [hashtable]$want, [switch]$BackupDirectories)
    if (Test-ReparsePath $root) { throw ('Linked scan root is not allowed: ' + $root) }
    $stack = New-Object System.Collections.Stack
    $stack.Push($root)
    while ($stack.Count -gt 0) {
        $d = $stack.Pop()
        try {
            if (Test-ProtectedPath $d -AllowBackup:$BackupDirectories) { continue }
            if ($BackupDirectories -and (Split-Path -Leaf $d) -eq '_dlss_originals') { $d; continue }
            foreach ($f in [IO.Directory]::EnumerateFiles($d)) {
                if ($want.ContainsKey([IO.Path]::GetFileName($f)) -and
                    ([IO.File]::GetAttributes($f) -band [IO.FileAttributes]::ReparsePoint) -eq 0) { $f }
            }
            foreach ($s in [IO.Directory]::EnumerateDirectories($d)) {
                # junctions and symlinks can loop back on themselves
                try { if (([IO.File]::GetAttributes($s) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { continue } } catch { continue }
                $stack.Push($s)
            }
        }
        catch {
            [void]$script:ScanErrors.Add(('{0}: {1}' -f $d, $_.Exception.Message))
            Write-RefresherLog ('Scan failed: {0}: {1}' -f $d, $_.Exception.Message) -Failure
        }
    }
}

function Find-Targets {
    param([string[]]$scanRoots, [string[]]$names)
    $found = New-Object System.Collections.ArrayList
    foreach ($root in $scanRoots) {
        if (-not (Test-Path -LiteralPath $root)) {
            Write-Host ("  !! root not found, skipped: {0}" -f $root) -ForegroundColor Yellow
            [void]$script:ScanErrors.Add(('Root not found: ' + $root))
            continue
        }
        Write-Host ("  scanning {0} ..." -f $root) -ForegroundColor DarkGray
        # one walk per root, matching names as we go: 16 filtered walks of a 500k-file tree
        # is the difference between ~1 minute and ~7 for the same answer.
        $want = @{}
        foreach ($n in $names) { $want[$n.ToLower()] = $true }
        Get-FilesByName -root $root -want $want | ForEach-Object {
            $p = $_
            if (-not (Test-ProtectedPath $p) -and -not $found.Contains($p)) { [void]$found.Add($p) }
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

        try {
        if (-not $ForceOnline) {
            $np = Get-Norm $p
            $hit = $null
            foreach ($a in $script:Online) { if ($np -like "*$a*") { $hit = $a; break } }
            if ($hit) { $row.Action = 'SKIP'; $row.Note = 'known online-title path - skipped (name heuristic)' }
        }
        $targetMachine = Get-PEMachine $p
        if ($row.Action -eq '' -and $name -ne 'DLSS5_Feed.fx' -and
            ($null -eq $targetMachine -or $null -eq $src.Machine -or $targetMachine -ne $src.Machine)) {
            $row.Action = 'SKIP'; $row.Note = 'invalid PE or architecture mismatch (32-bit/64-bit)'
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
                if ((Get-Sha $p) -eq (Get-Sha $src.Path)) { $row.Action = 'SKIP'; $row.Note = 'already current' }
                elseif ($null -eq $src.Version) { $row.Action = 'SWAP'; $row.Note = 'content differs' }
                elseif ($null -eq $have)        { $row.Action = 'SKIP'; $row.Note = 'version unreadable - check by hand' }
                else                            { $row.Action = 'SWAP'; $row.Note = 'same version, different build' }
            }
        }

        if ($row.Action -eq 'SWAP' -and $Apply) {
            $sourceHash = $src.Sha256
            if (-not $sourceHash) { $sourceHash = Get-Sha $src.Path }
            Install-VerifiedFile -Target $p -Source $src.Path -ExpectedHash $sourceHash
            $row.Note += ' -> replaced and verified (original kept)'
        }
        } catch {
            $row.Action = 'FAIL'
            $row.Note = $_.Exception.Message.Split([char]10)[0]
            Write-RefresherLog ('Update failed: {0}: {1}' -f $p, $row.Note) -Failure
        }
        [void]$rows.Add($row)
    }
    return ,$rows   # comma keeps a 1-row result a collection; otherwise .Count comes back null
}

function Invoke-Restore {
    param([string[]]$roots)
    $n = 0; $failed = 0
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { $failed++; Write-Warning ('Root not found: ' + $root); continue }
        foreach ($bak in (Get-FilesByName -root $root -want @{} -BackupDirectories)) {
            try {
                $ledger = Read-BackupLedger $bak
                if ($ledger.Files.Count -eq 0) { throw 'Untracked legacy backup preserved; restore its files manually.' }
            } catch {
                $failed++; Write-Warning ('Cannot restore {0}: {1}' -f $bak, $_.Exception.Message)
                Write-RefresherLog ('Restore failed: {0}: {1}' -f $bak, $_.Exception.Message) -Failure
                continue
            }
            foreach ($name in $ledger.Files.Keys) {
                if ($name -notin $script:Names) { continue }
                $target = Join-Path (Split-Path -Parent $bak) $name
                $keep = Join-Path $bak $name
                $stage = Join-Path (Split-Path -Parent $bak) ('.' + $name + '.' + [guid]::NewGuid().ToString('N') + '.tmp')
                $rollback = Join-Path $bak ([guid]::NewGuid().ToString('N') + '.rollback')
                $replaced = $false; $retainRollback = $false
                try {
                    $record = $ledger.Files[$name]
                    if ((Test-ReparsePath $target) -or (Test-ReparsePath $keep)) { throw 'Linked target or backup is not allowed.' }
                    if ((Get-Sha $keep) -ne $record.OriginalSha256) { throw 'Original backup changed; refusing restore.' }
                    $haveHash = Get-Sha $target
                    if ($haveHash -notin @($record.OriginalSha256, $record.InstalledSha256, $record.PendingSha256)) { throw 'Target changed outside this tool; refusing restore.' }
                    if ($haveHash -eq $record.OriginalSha256) { Write-Host ('  already restored ' + $target); continue }
                    Copy-Item -LiteralPath $keep -Destination $stage -ErrorAction Stop
                    if ((Get-Sha $stage) -ne $record.OriginalSha256 -or (Get-Sha $target) -ne $haveHash) { throw 'Restore staging or target verification failed.' }
                    [IO.File]::Replace($stage, $target, $rollback)
                    $replaced = $true
                    if ((Get-Sha $target) -ne $record.OriginalSha256) { throw 'Restored file failed hash verification.' }
                    Write-RefresherLog ('Restored and verified: {0}; SHA256={1}' -f $target, $record.OriginalSha256)
                    Write-Host ('  restored and verified ' + $target) -ForegroundColor Green
                    $n++
                } catch {
                    $cause = $_.Exception.Message
                    if ($replaced) {
                        try {
                            [IO.File]::Replace($rollback, $target, [NullString]::Value)
                            if ((Get-Sha $target) -ne $haveHash) { throw 'Rollback verification failed.' }
                        } catch { $retainRollback = $true; $cause += '; rollback failed: ' + $_.Exception.Message }
                    }
                    $failed++
                    Write-Warning ('Restore failed: {0}: {1}' -f $target, $cause)
                    Write-RefresherLog ('Restore failed: {0}: {1}' -f $target, $cause) -Failure
                } finally {
                    foreach ($temporary in @($stage, $rollback)) {
                        if ($temporary -eq $rollback -and $retainRollback) { continue }
                        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
                    }
                }
            }
        }
    }
    Write-Host ("`nRestored {0} file(s); failed: {1}." -f $n, $failed) -ForegroundColor Cyan
    return $failed
}

function Show-Report {
    param($rows)
    $swap = @($rows | Where-Object Action -eq 'SWAP')
    $skip = @($rows | Where-Object Action -eq 'SKIP')
    $fail = @($rows | Where-Object Action -eq 'FAIL')

    if ($rows.Count -eq 0) { Write-Host "`nNothing to report: no file the pack ships a source for was found under the scanned roots." -ForegroundColor Yellow; return }

    Write-Host "`nNOTE: known online-title paths (Fortnite, Marvel Rivals, Star Citizen, ...)" -ForegroundColor Yellow
    Write-Host "      are skipped by default - they show in 'left alone' with the reason. -ForceOnline" -ForegroundColor Yellow
    Write-Host "      overrides that; -Exclude skips extra folders by name." -ForegroundColor Yellow

    Write-Host "`n=== Files that need the update ===" -ForegroundColor Cyan
    if ($swap.Count -eq 0) { Write-Host "  (no eligible updates; see skipped and failed files below)" -ForegroundColor Green }
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

    $online = @($skip | Where-Object { $_.Note -like '*online-title*' })
    Write-Host ("Scanned: {0} file(s) | eligible: {1} | skipped: {2} | skipped online: {3} | failed: {4}" -f $rows.Count, $swap.Count, ($skip.Count - $online.Count), $online.Count, $fail.Count) -ForegroundColor Cyan
    if (-not $Apply -and $swap.Count -gt 0) {
        Write-Host "`nDry run - nothing was written. Re-run with -Apply to replace them (originals are kept in _dlss_originals\)." -ForegroundColor Yellow
    }
}

# ---------- self test ----------

function Invoke-SelfTest {
    param($map)
    if (-not $map.ContainsKey('nvngx_dlss.dll')) { throw 'Self-test requires nvngx_dlss.dll in the source pack.' }
    $script:Apply = $false; $script:ForceOnline = $false
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
    Assert ($byPath['MarvelRivals'].Action -eq 'SKIP' -and $byPath['MarvelRivals'].Note -like '*online-title*') 'online game folder is skipped by default'

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

$operationMutex = $null; $operationHeld = $false
try {
if ($Apply -or $Restore -or $SelfTest) {
    $operationMutex = New-Object Threading.Mutex($false, 'Local\DLSS5AIO-Mutation')
    try { $operationHeld = $operationMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $operationHeld = $true }
    if (-not $operationHeld) {
        Write-RefresherLog 'Another DLSS5AIO mutation is running.' -Failure
        Write-Error 'Another DLSS5AIO mutation is running.' -ErrorAction Continue
        exit 1
    }
}
$roots = Get-ScanRoots -r $Roots
Write-RefresherLog ('DLSS5AIO refresher 2.0.0; Apply={0}; Restore={1}; SkipNR={2}; ForceOnline={3}; Roots={4}; Source={5}' -f $Apply, $Restore, $SkipNR, $ForceOnline, ($roots -join ','), $SourceDir)
if ($Restore) {
    try {
        Write-Host "`nRestoring originals under: $($roots -join ', ')" -ForegroundColor Cyan
        $failed = Invoke-Restore -roots $roots
        if ($failed -gt 0 -or $script:ScanErrors.Count -gt 0) { exit 1 }
        exit 0
    } catch { Write-Error $_ -ErrorAction Continue; exit 1 }
}

$map = $null
try { $map = Resolve-Source -dir $SourceDir }
catch {
    Write-RefresherLog ('Source resolution failed: ' + $_.Exception.Message) -Failure
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    exit 1
}
Write-Host "Verified pack set:" -ForegroundColor Cyan
foreach ($k in ($map.Keys | Sort-Object)) { Write-Host ("  {0,-22} {1}" -f $k, $map[$k].VerText) }
Write-Host ("  ({0} file(s) will be used as the source of truth)" -f $map.Count) -ForegroundColor DarkGray

if ($SelfTest) { Invoke-SelfTest -map $map }

Write-Host "`nScanning: $($roots -join ', ')" -ForegroundColor Cyan
if (-not $Apply) { Write-Host "DRY RUN - nothing will be written. Add -Apply to make changes.`n" -ForegroundColor Yellow }
$rows = Invoke-Refresher -map $map -roots $roots
Show-Report -rows $rows
if ($script:ScanErrors.Count -gt 0) {
    Write-Warning ('Incomplete scan: {0} inaccessible or missing path(s). See {1}' -f $script:ScanErrors.Count, $script:LogPath)
}
if (@($rows | Where-Object Action -eq 'FAIL').Count -gt 0 -or $script:ScanErrors.Count -gt 0) { exit 1 }
exit 0
} catch {
    Write-RefresherLog ('Command failed: ' + $_.Exception.Message) -Failure
    Write-Error $_ -ErrorAction Continue
    exit 1
} finally {
    if ($operationHeld) { $operationMutex.ReleaseMutex() }
    if ($operationMutex) { $operationMutex.Dispose() }
}
