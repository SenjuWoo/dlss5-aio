# Exercise DLL refresher writes against disposable local files, including recovery failures.
# Requires Windows PowerShell 5.1 or newer; no games, installed DLLs, or network are touched.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$tool = Join-Path $repo '06-DLL-Refresher\DLSS-DLL-Refresher.ps1'
$fixture = Join-Path (Split-Path -Parent $repo) ('refresher-tests-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixture) | Out-Null
$checks = 0
$savedLocalAppData = $env:LOCALAPPDATA

# Import the actual functions without dispatching the whole-PC command-line entrypoint.
$prefix = (Get-Content -LiteralPath $tool -Raw) -split '# ---------- main ----------'
$helpers = Join-Path $fixture 'helpers.ps1'
[IO.File]::WriteAllText($helpers, $prefix[0], (New-Object Text.UTF8Encoding($true)))
. $helpers
$script:SourceRoots = @()
$script:LogPath = Join-Path $fixture 'logs\refresher.log'
$script:Apply = $false
$script:ForceOnline = $false
$name = 'dlss5-feed.addon64'

function Check($Condition, [string]$Message) {
    if (-not $Condition) { throw ('FAIL: ' + $Message) }
    $script:checks++
    Write-Host ('ok ' + $Message)
}

function Expect-Throw([scriptblock]$Action, [string]$Message) {
    $threw = $false
    try { & $Action | Out-Null } catch { $threw = $true }
    Check $threw $Message
}

# Small PE-shaped fixtures test architecture and transaction logic without executing native code.
function Write-Fixture([string]$Path, [byte]$Marker = 0, [int]$Machine = 0x8664) {
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    $bytes = New-Object byte[] 256
    $bytes[0] = 0x4d; $bytes[1] = 0x5a; $bytes[0x3c] = 0x40
    $bytes[0x40] = 0x50; $bytes[0x41] = 0x45
    $bytes[0x44] = $Machine -band 255; $bytes[0x45] = ($Machine -shr 8) -band 255
    $bytes[255] = $Marker
    [IO.File]::WriteAllBytes($Path, $bytes)
}

function Game([string]$Leaf, [byte]$Marker = 1) {
    $path = Join-Path (Join-Path $fixture $Leaf) $name
    Write-Fixture $path $Marker
    return $path
}

function Refresh([string]$Path) {
    $rows = Invoke-Refresher -map $map -roots @((Split-Path -Parent $Path))
    return ,$rows
}

try {
    $source = Join-Path $fixture 'sources\source.addon64'
    Write-Fixture $source
    $map = @{ $name = [pscustomobject]@{ Path=$source; Version=$null; VerText=$null; Machine=0x8664; Sha256=(Get-Sha $source) } }
    $game = Game 'normal'
    $originalHash = Get-Sha $game
    $rows = Refresh $game
    Check ($rows.Count -eq 1 -and $rows[0].Action -eq 'SWAP') 'dry run detects one update'
    Check ((Get-Sha $game) -eq $originalHash -and -not (Test-Path (Join-Path (Split-Path $game) '_dlss_originals'))) 'dry run writes no game files'

    $script:Apply = $true
    $rows = Refresh $game
    $backup = Join-Path (Split-Path -Parent $game) ('_dlss_originals\' + $name)
    Check ($rows[0].Action -eq 'SWAP' -and (Get-Sha $game) -eq $map[$name].Sha256) ('apply replaces and verifies bytes: ' + $rows[0].Note)
    Check ((Get-Sha $backup) -eq $originalHash) 'first original is backed up exactly'
    $rows = Refresh $game
    Check ($rows[0].Action -eq 'SKIP') 'repeated scan observes installed bytes without a stale hash cache'
    Write-Fixture $source 2
    $map[$name].Sha256 = Get-Sha $source
    $rows = Refresh $game
    Check ($rows[0].Action -eq 'SWAP' -and (Get-Sha $backup) -eq $originalHash) 'second update keeps the first original'
    $failures = Invoke-Restore @((Split-Path -Parent $game))
    Check ($failures -eq 0 -and (Get-Sha $game) -eq $originalHash) 'restore verifies the original'
    $failures = Invoke-Restore @((Split-Path -Parent $game))
    Check ($failures -eq 0) 'restore is repeatable'

    # Fail the final recovery-record commit after a real replacement to prove rollback, not just staging.
    $rollbackGame = Game 'rollback'
    $rollbackOriginal = Get-Sha $rollbackGame
    $script:actualLedgerSave = (Get-Command Save-BackupLedger).ScriptBlock
    $script:ledgerWriteCount = 0
    function Save-BackupLedger {
        param([string]$Backup, $Ledger)
        $script:ledgerWriteCount++
        if ($script:ledgerWriteCount -eq 3) { throw 'Injected final ledger write failure.' }
        & $script:actualLedgerSave $Backup $Ledger
    }
    try { $rows = Refresh $rollbackGame }
    finally { Set-Item -Path Function:\Save-BackupLedger -Value $script:actualLedgerSave }
    Check ($rows[0].Action -eq 'FAIL' -and (Get-Sha $rollbackGame) -eq $rollbackOriginal) 'failure after replacement rolls the actual target back'
    $rows = Refresh $rollbackGame
    Check ($rows[0].Action -eq 'SWAP') 'rolled-back transaction can be retried'
    $interruptedBackup = Join-Path (Split-Path -Parent $rollbackGame) '_dlss_originals'
    $interruptedLedger = Read-BackupLedger $interruptedBackup
    $interruptedLedger.Files[$name].PendingSha256 = $interruptedLedger.Files[$name].InstalledSha256
    $interruptedLedger.Files[$name].InstalledSha256 = $interruptedLedger.Files[$name].OriginalSha256
    Save-BackupLedger $interruptedBackup $interruptedLedger
    $failures = Invoke-Restore @((Split-Path -Parent $rollbackGame))
    Check ($failures -eq 0 -and (Get-Sha $rollbackGame) -eq $rollbackOriginal) 'restore recovers a pending replacement after interruption'

    # Real Windows sharing locks verify that filesystem errors reach the failure report.
    $locked = Game 'locked'
    $lockedHash = Get-Sha $locked
    $handle = [IO.File]::Open($locked, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try { $rows = Refresh $locked } finally { $handle.Dispose() }
    Check ($rows[0].Action -eq 'FAIL' -and (Get-Sha $locked) -eq $lockedHash) 'locked target fails without changing it'
    $rows = Refresh $locked
    Check ($rows[0].Action -eq 'SWAP') 'failed replacement can be retried safely'
    $handle = [IO.File]::Open($locked, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try { $failures = Invoke-Restore @((Split-Path -Parent $locked)) } finally { $handle.Dispose() }
    Check ($failures -eq 1 -and (Get-Sha $locked) -eq $map[$name].Sha256) 'locked restore fails without changing installed bytes'

    $blocked = Game 'blocked-backup'
    $blockedHash = Get-Sha $blocked
    [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $blocked) '_dlss_originals'), 'not a directory')
    $rows = Refresh $blocked
    Check ($rows[0].Action -eq 'FAIL' -and (Get-Sha $blocked) -eq $blockedHash) 'failed backup never permits replacement'

    $legacy = Game 'legacy-backup'
    $legacyHash = Get-Sha $legacy
    Write-Fixture (Join-Path (Split-Path -Parent $legacy) ('_dlss_originals\' + $name)) 9
    $rows = Refresh $legacy
    Check ($rows[0].Action -eq 'FAIL' -and (Get-Sha $legacy) -eq $legacyHash) 'untracked old backup is preserved'
    $failures = Invoke-Restore @((Split-Path -Parent $legacy))
    Check ($failures -eq 1 -and (Get-Sha $legacy) -eq $legacyHash) 'untracked restore cannot overwrite newer game files'

    $edited = Game 'personal-edit'
    $null = Refresh $edited
    Write-Fixture $edited 7
    $editedHash = Get-Sha $edited
    $rows = Refresh $edited
    Check ($rows[0].Action -eq 'FAIL' -and (Get-Sha $edited) -eq $editedHash) 'later personal edits block another update'
    $failures = Invoke-Restore @((Split-Path -Parent $edited))
    Check ($failures -eq 1 -and (Get-Sha $edited) -eq $editedHash) 'later personal edits block restore'

    $tampered = Game 'tampered-backup'
    $null = Refresh $tampered
    Write-Fixture (Join-Path (Split-Path -Parent $tampered) ('_dlss_originals\' + $name)) 8
    $failures = Invoke-Restore @((Split-Path -Parent $tampered))
    Check ($failures -eq 1 -and (Get-Sha $tampered) -eq $map[$name].Sha256) 'tampered backup cannot be restored'
    Write-Fixture $source 3
    $map[$name].Sha256 = Get-Sha $source
    $rows = Refresh $tampered
    Check ($rows[0].Action -eq 'FAIL') 'tampered backup also blocks future replacements'

    $changedSource = Game 'changed-source'
    $changedSourceHash = Get-Sha $changedSource
    Write-Fixture $source 4
    $rows = Refresh $changedSource
    Check ($rows[0].Action -eq 'FAIL' -and (Get-Sha $changedSource) -eq $changedSourceHash) 'changed source fails staging hash verification'
    $map[$name].Sha256 = Get-Sha $source

    $x86 = Game 'x86'
    Write-Fixture $x86 1 0x14c
    $rows = Refresh $x86
    Check ($rows[0].Action -eq 'SKIP') 'wrong architecture is left untouched'
    $invalid = Game 'invalid-pe'
    [IO.File]::WriteAllText($invalid, 'not a PE file')
    $rows = Refresh $invalid
    Check ($rows[0].Action -eq 'SKIP') 'invalid target PE is left untouched'
    $onlineGame = Game 'Marvel Rivals'
    $rows = Refresh $onlineGame
    Check ($rows[0].Action -eq 'SKIP') 'known online title is skipped by default'

    # Protected paths are pruned before enumeration; a junction never widens the scan.
    foreach ($protected in @('Backup', '.codex', 'zzReference', 'profiles', 'DLSS 5 Swapper')) {
        $path = Game ($protected + '\game')
        $rows = Refresh $path
        Check ($rows.Count -eq 0) ('protected subtree skipped: ' + $protected)
    }
    $junction = Join-Path (Split-Path -Parent $env:USERPROFILE) 'All Users'
    Check (Test-ReparsePath $junction) 'Windows compatibility junction is available for a read-only boundary test'
    Expect-Throw { Get-FilesByName -root $junction -want @{ $name=$true } } 'linked scan root is rejected'

    Expect-Throw { Resolve-Source (Join-Path $fixture 'missing-source') } 'explicit missing source never silently selects a different pack'
    $badPack = Join-Path $fixture 'bad-pack'
    $badSource = Join-Path $badPack '01-Official-NVIDIA-DLLs'
    [IO.Directory]::CreateDirectory($badSource) | Out-Null
    [IO.File]::WriteAllText((Join-Path $badSource 'nvngx_dlss.dll'), 'invalid DLL')
    [IO.File]::WriteAllText((Join-Path $badPack 'SHA256SUMS.txt'), (('0' * 64) + ' *01-Official-NVIDIA-DLLs/nvngx_dlss.dll'))
    Expect-Throw { Resolve-Source $badSource } 'source manifest hash mismatch is rejected'
    [IO.File]::WriteAllText((Join-Path $badPack 'SHA256SUMS.txt'), ((Get-Sha (Join-Path $badSource 'nvngx_dlss.dll')) + ' *01-Official-NVIDIA-DLLs/nvngx_dlss.dll'))
    Expect-Throw { Resolve-Source $badSource } 'hash-matching malformed source PE is rejected'

    Check ((Get-NumVersion '310.8.SF.0') -eq (Get-NumVersion '310,8,0,0')) 'build-tagged numeric version remains comparable'
    Check ($null -eq (Get-NumVersion '99999999999999999999.1')) 'overflowing version fails safely'
    Check ($null -eq (Get-NumVersion 'version1')) 'nonnumeric version prefix is rejected'
    Check ((Get-NumVersion '310, 9, 1, 0') -eq [version]'310.9.1.0') 'whitespace in numeric version is accepted'

    # Exercise the public CLI after removing the source, including its exit code.
    $cliGame = Game 'cli-restore'
    $cliOriginal = Get-Sha $cliGame
    $null = Refresh $cliGame
    Remove-Item -LiteralPath $source
    $env:LOCALAPPDATA = Join-Path $fixture 'appdata'
    $shell = (Get-Command powershell.exe -ErrorAction Stop).Source
    & $shell -NoProfile -ExecutionPolicy Bypass -File $tool -Restore -Roots (Split-Path -Parent $cliGame) -SourceDir (Join-Path $fixture 'no-pack')
    Check ($LASTEXITCODE -eq 0 -and (Get-Sha $cliGame) -eq $cliOriginal) 'public restore succeeds without source pack'
    & (Join-Path (Split-Path -Parent $tool) 'Refresh-DLSS-DLLs.bat') -Restore -Roots (Split-Path -Parent $cliGame)
    Check ($LASTEXITCODE -eq 0 -and (Get-Sha $cliGame) -eq $cliOriginal) 'batch restore succeeds with inherited shell module paths'
    Write-Fixture $cliGame 6
    $cliEdited = Get-Sha $cliGame
    & $shell -NoProfile -ExecutionPolicy Bypass -File $tool -Restore -Roots (Split-Path -Parent $cliGame)
    Check ($LASTEXITCODE -eq 1 -and (Get-Sha $cliGame) -eq $cliEdited) 'public CLI returns nonzero when restore refuses changed data'
    & (Join-Path (Split-Path -Parent $tool) 'Refresh-DLSS-DLLs.bat') -Restore -Roots (Split-Path -Parent $cliGame)
    Check ($LASTEXITCODE -eq 1 -and (Get-Sha $cliGame) -eq $cliEdited) 'batch argument forwarding preserves the PowerShell failure exit code'
    $mutex = New-Object Threading.Mutex($false, 'Local\DLSS5AIO-Mutation')
    $held = $mutex.WaitOne(0)
    if (-not $held) { throw 'Could not acquire test mutation mutex.' }
    try {
        & $shell -NoProfile -ExecutionPolicy Bypass -File $tool -Restore -Roots (Split-Path -Parent $cliGame)
        Check ($LASTEXITCODE -eq 1 -and (Get-Sha $cliGame) -ne $cliOriginal) 'concurrent public mutation is refused without touching files'
    } finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
    Check (@(Get-ChildItem -LiteralPath $fixture -Recurse -File | Where-Object { $_.Name -match '\.(tmp|rollback)$' }).Count -eq 0) 'failed and successful transactions leave no temporary files'
    Write-Host ('PASS: {0} functional refresher checks' -f $checks)
} finally {
    $env:LOCALAPPDATA = $savedLocalAppData
    # Remove only this invocation's verified workspace fixture.
    $expectedParent = [IO.Path]::GetFullPath((Split-Path -Parent $repo)).TrimEnd('\')
    if ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($fixture)) -ne $expectedParent) { throw 'Unsafe fixture cleanup path.' }
    Remove-Item -LiteralPath $fixture -Recurse -Force
}
