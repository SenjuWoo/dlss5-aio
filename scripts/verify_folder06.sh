#!/bin/bash
# Ad-hoc verification for DLSS 5 AIO folder 06 (release gate, not a test suite).
#
#   bash scripts/verify_folder06.sh [PACK_DIR]
#
# PACK_DIR is an extracted pack (folder 06 sitting next to 01-Official-NVIDIA-DLLs);
# it defaults to ../dlss5-aio-build/DLSS5-AIO next to this repo. Windows + git-bash
# only - it drives cmd.exe and PowerShell, so CI does not run it.
#
# Covers: version parsing (build tags), apply/backup/restore, launcher under cmd.exe,
# default source resolution, argument passthrough, manifest integrity.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PACK="${1:-$(dirname "$REPO")/dlss5-aio-build/DLSS5-AIO}"
[ -d "$PACK/06-DLL-Refresher" ] || { echo "pack not found: $PACK"; echo "usage: bash scripts/verify_folder06.sh <extracted-pack-dir>"; exit 2; }
TOOL="$PACK/06-DLL-Refresher/DLSS-DLL-Refresher.ps1"
LAUNCH="$PACK/06-DLL-Refresher/Refresh-DLSS-DLLs.bat"
SRC="$PACK/01-Official-NVIDIA-DLLs"
NR="$PACK/02-DLSS5-Neural-Rendering/nvngx_dlssnr.dll"
# a real older DLSSNR build, if this machine has one (optional section)
REAL_OLD="${REAL_OLD:-/s/Apps/DLSS 5 neuralscreen-v1.17.0-full/native/_dlss_originals/nvngx_dlssnr.dll}"
FIX=$(mktemp -d "${TMPDIR:-/tmp}/hermes-verify-folder06-XXXXXX")
PASS=0; FAIL=0
ok()  { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }
W()   { cygpath -w "$1"; }
SHA() { sha256sum < "$1" | cut -d' ' -f1; }   # stdin form: no filename, no backslash escaping
RUN() { powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(W "$TOOL")" "$@" 2>&1 | tr -d '\r'; }
trap 'rm -rf "$FIX"' EXIT

echo "pack: $PACK"
echo "== A. self-test (unit assertions incl. version parsing) =="
OUT=$(RUN -SelfTest)
echo "$OUT" | grep -q "SELF TEST PASSED" && ok "self-test passed" || { bad "self-test failed"; echo "$OUT" | tail -4; }
N=$(echo "$OUT" | grep -c "  ok   ")
[ "$N" -ge 11 ] && ok "$N assertions ran" || bad "only $N assertions ran (expected >= 11)"

echo "== B. version parsing on real builds =="
if [ -f "$REAL_OLD" ] && [ -f "$NR" ]; then
    OLD_SHA=$(SHA "$REAL_OLD"); NEW_SHA=$(SHA "$NR")
    mkdir -p "$FIX/stale" "$FIX/current"
    cp "$REAL_OLD" "$FIX/stale/nvngx_dlssnr.dll"; cp "$NR" "$FIX/current/nvngx_dlssnr.dll"
    OUT=$(RUN -Roots "$(W "$FIX")")
    echo "$OUT" | grep -qE "to update: 1" && ok "older build flagged for update" || { bad "older build not flagged"; echo "$OUT" | tail -5; }
    echo "$OUT" | grep -q "newer than the pack" && bad "older build misread as newer" || ok "no bogus 'newer than the pack'"
    echo "$OUT" | grep -q "already current" && ok "current build recognised" || bad "current build not recognised"
    RUN -Roots "$(W "$FIX")" -Apply >/dev/null
    [ "$(SHA "$FIX/stale/nvngx_dlssnr.dll")" = "$NEW_SHA" ] && ok "older build replaced" || bad "not replaced"
    [ -f "$FIX/stale/_dlss_originals/nvngx_dlssnr.dll" ] && [ "$(SHA "$FIX/stale/_dlss_originals/nvngx_dlssnr.dll")" = "$OLD_SHA" ] \
        && ok "original backed up" || bad "original not backed up"
    [ "$(SHA "$FIX/current/nvngx_dlssnr.dll")" = "$NEW_SHA" ] && ok "current build untouched" || bad "current build modified"
    rm -rf "$FIX/stale" "$FIX/current"
else
    echo "  SKIP  no real older build on this machine ($REAL_OLD)"
fi

echo "== B2. source coverage: the pack resolves every managed file =="
OUT=$(RUN -Roots "$(W "$PACK/01-Official-NVIDIA-DLLs")" 2>&1)
N=$(echo "$OUT" | grep -c "file(s) will be used as the source of truth")
echo "$OUT" | grep -qE "sl\.dlss\.dll" && ok "Streamline resolved" || bad "Streamline missing from the source map"
echo "$OUT" | grep -q "dlss5-feed.addon64" && ok "feeder resolved" || bad "feeder missing from the source map"
echo "$OUT" | grep -qE "\(1[4-9]|2[0-9]) file\(s\) will be used" && ok "source set is the full managed list" || bad "source set smaller than expected"

echo "== C. launcher under cmd.exe =="
IN="$FIX/in.txt"; printf '0\n' > "$IN"
BOUT=$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' timeout 120 cmd.exe /c "$(W "$LAUNCH")" < "$IN" 2>&1 | tr -d '\r')
echo "$BOUT" | grep -q "nvngx_dlssnr.dll): included" && ok "menu renders (NR state line)" || bad "menu did not render"
echo "$BOUT" | grep -qE "was unexpected|syntax of the command is incorrect" && bad "cmd syntax error" || ok "no cmd syntax error"
BOUT=$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' timeout 240 cmd.exe /c "$(W "$LAUNCH")" -SelfTest 2>&1 | tr -d '\r')
echo "$BOUT" | grep -q "SELF TEST PASSED" && ok "arguments forwarded to the tool" || bad "argument passthrough failed"

echo "== D. default source resolution (no -SourceDir) =="
OUT=$(RUN -SelfTest)
echo "$OUT" | grep -q "SELF TEST PASSED" && ok "tool finds 01 next to itself" || bad "default resolution broken"

echo "== E. manifest integrity =="
if [ -f "$PACK/SHA256SUMS.txt" ]; then
    T="$FIX/sums.txt"
    grep -E "06-DLL-Refresher|01-Official-NVIDIA-DLLs" "$PACK/SHA256SUMS.txt" > "$T"
    if ( cd "$PACK" && sha256sum -c "$T" ) > "$FIX/chk.txt" 2>&1; then ok "manifest verified ($(wc -l < "$T") files)"
    else bad "manifest mismatch"; grep FAILED "$FIX/chk.txt" | head -3; fi
else bad "no SHA256SUMS.txt in the pack"; fi

echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && echo "AD-HOC VERIFICATION: PASS" || echo "AD-HOC VERIFICATION: FAIL"
exit "$FAIL"