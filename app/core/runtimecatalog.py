"""Verified, exact-filename NVIDIA, AMD and Intel runtime downloads.

Publisher pins work offline; an explicit refresh checks RHI's NVIDIA feed.
Downloads use the application's cache and log, never a game folder.
"""
from __future__ import annotations

import copy
import base64
import json
import os
import re
import shutil
import stat
import struct
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from . import log, net, pe

FAMILIES = (
    ("dlss", "nvngx_dlss.dll", "NVIDIA super resolution"),
    ("dlssg", "nvngx_dlssg.dll", "NVIDIA frame generation"),
    ("dlssd", "nvngx_dlssd.dll", "NVIDIA ray reconstruction"),
    ("xess", "libxess.dll", "Intel XeSS super resolution"),
    ("xess_dx11", "libxess_dx11.dll", "Intel XeSS DX11 bridge"),
    ("xess_fg", "libxess_fg.dll", "Intel XeSS frame generation"),
    ("xell", "libxell.dll", "Intel low latency"),
    ("fsr31_dx12", "amd_fidelityfx_dx12.dll", "AMD FSR 3.1 DX12"),
    ("fsr31_vk", "amd_fidelityfx_vk.dll", "AMD FSR 3.1 Vulkan"),
    ("fsr_loader", "amd_fidelityfx_loader_dx12.dll", "AMD FSR loader"),
    ("fsr4", "amd_fidelityfx_upscaler_dx12.dll", "AMD FSR upscaling"),
    ("fsr4_fg", "amd_fidelityfx_framegeneration_dx12.dll", "AMD FSR frame generation"),
)
FILE_OF = {family: name for family, name, _ in FAMILIES}
RHI_FEED = "https://raw.githubusercontent.com/RankFTW/RHI/main/dlss_manifest.json"
RHI_API = "https://api.github.com/repos/RankFTW/rhi-repo/releases/tags/"
MAX_FILE = 256 * 1024 * 1024
MAX_ARCHIVE = 256 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"\d+(?:\.\d+){2,3}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
_NVIDIA = "374959484e79a640feaba44c93ac8cfb0a03f5b5"
_AMD = "60f4ea81909200d8542eca14dccb2628b763a9a3"
_AMD31 = "c6efa6bf7f2027b3ec94f28578bb5965eabb9e55"
_INTEL = "8fe81bdbbaf00b3c1b733fd0d830c333dc84e6f0"
_NVIDIA_NEW = "9981c6350dc58c0ce21f024fd65e31e851c31689"      # DLSS 310.9.16 SDK, 2026-10-16
_AMD_NEW = "7539ae8b6568ad29ed78a753404351daf3b5cca7"         # AMD FSR SDK 2.4.0, 2026-10-28

# SHA256 pins were checked against the publishers' immutable Git blob identities.
_PINS = (
    ("dlss", "310.9.1", 58956912, "3975567b8943c53acce397f2b72380092f84f162d00b0d2c7d08a1025c563983", "NVIDIA/DLSS", _NVIDIA, "lib/Windows_x86_64/rel/"),
    ("dlssg", "310.9.1", 7460976, "ff6e90eb78b827927dff5b4ecc6b1c870c2e9bca29ed9f48c7d348cc9e170b82", "NVIDIA/DLSS", _NVIDIA, "lib/Windows_x86_64/rel/"),
    ("dlssd", "310.9.1", 48343664, "4bc7ea5fcb2f32cf86bc2cb072e8d2860914a0be511cbdcb2fc206c1d9d83b80", "NVIDIA/DLSS", _NVIDIA, "lib/Windows_x86_64/rel/"),
    ("xess", "2.0.2.68", 77795704, "251659dd84a3e84de67c886a4186e01f3eca49b00641906fe38bb6b807e5d5b7", "intel/xess", _INTEL, "bin/"),
    ("xess_dx11", "2.0.2.68", 156016, "c7cfe86f0c9d94e4fb3696d3cd5035e2bbb6a8b1b0572f8b7395a4cdfd0c625e", "intel/xess", _INTEL, "bin/"),
    ("xess_fg", "1.3.1.78", 22957432, "ec5e0c65e075570c6ede72618bb666d0be0c2e10b2ea9762c0fe8cb8e375ab27", "intel/xess", _INTEL, "bin/"),
    ("xell", "1.3.2.10", 415368, "d2030dcd694fda8f2ec7e044b13e6db8f0b56d4ba9113a5efad334e3f3ded8c7", "intel/xess", _INTEL, "bin/"),
    ("fsr31_dx12", "1.0.1.41314", 6675664, "12a5081257ec95b0b53ad51b4a87fb3c03f97fe0bbb59f9496968f8d50ef93a6", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD31, "PrebuiltSignedDLL/"),
    ("fsr31_vk", "1.0.1.41314", 9332432, "a1624cc4238fef046f30c4d80ce3f47be63fc5f5373f49e3ee9edb9960f54c78", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD31, "PrebuiltSignedDLL/"),
    ("fsr_loader", "2.3.0.2740", 26376, "e2d85aa05a9bd9ed8b38935fdf5199372cca6f74c12015143bb6f945ee1608aa", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD, "Kits/FidelityFX/signedbin/"),
    ("fsr4", "4.1.1.2740", 28761864, "d0dcccc74a43c44ba435b7a369b456e0970d8a4464e4bd683119b374f2c9fb46", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD, "Kits/FidelityFX/signedbin/"),
    ("fsr4_fg", "4.0.1.2740", 40085776, "02297beedd285e822d3a64f314cf00faf378dcec0edc47ff0c4dd71b3a8c2f18", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD, "Kits/FidelityFX/signedbin/"),
)
# Snapshot of the publishers' newest signed builds at the 2026-10-30 check. Each was
# downloaded from the commit-addressed URL, matched to the Git blob id GitHub lists for
# it, and checked for a valid publisher Authenticode signature and its FileVersion.
_PINS_LATEST = (
    ("dlss", "310.9.16", 58956912, "d00b5b0ab29c3ca101b70c3a5ecb3a01b7ef33766a3383a28a18623083e6123e", "NVIDIA/DLSS", _NVIDIA_NEW, "lib/Windows_x86_64/rel/"),
    ("dlssg", "310.9.16", 7506544, "8d59d49b36410dd6b62fef2503a5871d347415bd85d943fa0848563a95dd50c7", "NVIDIA/DLSS", _NVIDIA_NEW, "lib/Windows_x86_64/rel/"),
    ("dlssd", "310.9.16", 48343664, "b49435ae346f227feafe7bbe937d88277ea0ee7323975ec06488f377fdb46cee", "NVIDIA/DLSS", _NVIDIA_NEW, "lib/Windows_x86_64/rel/"),
    ("fsr_loader", "2.3.0.4555", 39184, "e2191d3c0828be45eb8affd4e3ec0378f2293adc345b772a7170edcf3b021ecb", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD_NEW, "Kits/FidelityFX/signedbin/"),
    ("fsr4", "4.1.2.4555", 57664272, "aad4fccccb29084a655f9a4f9f613bd22c8c03fb4a0f8840148cc6543b4ccace", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD_NEW, "Kits/FidelityFX/signedbin/"),
    ("fsr4_fg", "4.0.2.4555", 29679376, "e6843252f58b0341a0d80f6a20bc0d840643ee95bc48c22cac08745344577bb6", "GPUOpen-LibrariesAndSDKs/FidelityFX-SDK", _AMD_NEW, "Kits/FidelityFX/signedbin/"),
)
_BLOBS = {  # Git blob ids of the files above, so a refresh knows them without downloading
    ("dlss", "310.9.16"): "23c4672e4a31ef303e8f98ff4f0d146bd1718ccf",
    ("dlssg", "310.9.16"): "71b8070cdced79e8df3414060337c84d91e38422",
    ("dlssd", "310.9.16"): "36efb7890a7f5754935647c6b3510e21a096512f",
    ("fsr_loader", "2.3.0.4555"): "f1afee09dd3bcded005c722b1e94befb3ee3f9e6",
    ("fsr4", "4.1.2.4555"): "6d01d9f52c412fc336350f04e948eb1bee196a38",
    ("fsr4_fg", "4.0.2.4555"): "445674331676665f18b5acd1b3c8621629cb0e75",
    ("xess", "2.0.2.68"): "548837c12b215d189884d54db0a480cd3bf2bfd1",       # intel/xess v3.0.2
    ("xess_dx11", "2.0.2.68"): "1e0247ba23a841ff514841ff963b72b636802a4e",
    ("xess_fg", "1.3.1.78"): "57a5da469d79e8dceea6af01961030219d391cdf",
    ("xell", "1.3.2.10"): "c321c6c6cd148dc614e6a339a27976ce0874d2e7",
}
# Who may sign each family's DLL; a mirror's or a repository's own hash proves nothing about origin.
_NVIDIA_FAMILIES = ("dlss", "dlssg", "dlssd")
_SIGNERS = {**{f: ("NVIDIA Corporation",) for f in _NVIDIA_FAMILIES},
            **{f: ("Intel Corporation",) for f in ("xess", "xess_dx11", "xess_fg", "xell")},
            **{f: ("Advanced Micro Devices", "Advanced Micro Devices, Inc.")
               for f in ("fsr31_dx12", "fsr31_vk", "fsr_loader", "fsr4", "fsr4_fg")}}
_RHI_PINS = (
    ("dlss", 44480231, "1823ec911c77482e6731447dfb0db3def8aa710e092f59f58c4c4c55285d492d"),
    ("dlssd", 37352309, "33470176d595838fb8751023c56e1e2b56e0da8d19c5c140b1bb325a53984ff2"),
    ("dlssg", 3691810, "20f967c689e73803769df30a63b9d70fa6339257c1612d687b7414aabf847766"),
)
# These signed NVIDIA DLLs were independently checked after verified extraction.
_RHI_CONTENT = {
    ("dlss", "310.9.16"): (74187376, "858ccff96360c3098db9264cd6f13d04a027e09b6ce7ad5bbc297570e824b4f2"),
    ("dlssg", "310.9.16"): (7506544, "cadee1aa6db3907babdc3285da2aebc4553d92b89c38ba3eae8abd8bba1bea72"),
    ("dlssd", "310.9.16"): (79669360, "7006c3a729276e876e06a97c6262672a1be96a58d69b0e85877f911146b98fbe"),
}
_CATALOG: dict | None = None
_LIVE_TRIED = False


def live_first() -> bool:
    """True once per run: the first read of the catalog asks the publishers.

    A window opened after a new SDK shipped must not work from the pins alone.
    DLSS5_AIO_OFFLINE=1 turns it off (the tests set it); a failed ask keeps the pins.
    """
    global _LIVE_TRIED
    if _LIVE_TRIED or os.environ.get("DLSS5_AIO_OFFLINE"):
        return False
    _LIVE_TRIED = True
    return True
_CACHE_LOCK = threading.RLock()


def _version(value: str) -> tuple:
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (4 - len(parts))


def _order(row: dict) -> tuple:
    """Newest first; on a tie the publisher's own file comes before a community mirror's."""
    return _version(row["version"]), "mirror" not in str(row.get("source", ""))


def _rhi_build(family: str, version: str, archive_size: int, digest: str) -> dict:
    name = f"nvngx_{family}_{version}.zip"
    size, raw_digest = _RHI_CONTENT.get((family, version), (0, ""))
    return {"label": f"{version} (RHI community mirror)", "version": version,
            "url": f"https://github.com/RankFTW/rhi-repo/releases/download/{family}-{version}/{name}",
            "raw": False, "member": FILE_OF[family], "size": size, "sha256": raw_digest,
            "archive_size": archive_size, "archive_sha256": digest,
            "source": "RankFTW/rhi-repo community mirror"}


def _entry(family: str, version: str, size: int, digest: str, repo: str, commit: str, folder: str,
           blob: str = "", requires: dict | None = None) -> dict:
    entry = {"label": f"{version} ({repo.split('/')[0]} SDK)", "version": version,
             "url": f"https://raw.githubusercontent.com/{repo}/{commit}/{folder}{FILE_OF[family]}",
             "sha256": digest, "size": size, "raw": True,
             "source": f"{repo}@{commit}", "member": FILE_OF[family]}
    if blob:
        entry["blob"] = blob
    if requires:
        entry["requires"] = requires
    return entry


def _pinned() -> dict:
    out = {family: [] for family in FILE_OF}
    pins = _PINS + _PINS_LATEST
    loaders = {commit: version for family, version, _s, _d, _r, commit, _f in pins if family == "fsr_loader"}
    for family, version, size, digest, repo, commit, folder in pins:
        # Split AMD runtimes need the loader built with them
        needs = {FILE_OF["fsr_loader"]: loaders[commit]} if family in ("fsr4", "fsr4_fg") else None
        out[family].append(_entry(family, version, size, digest, repo, commit, folder,
                                  _BLOBS.get((family, version), ""), needs))
    for family, size, digest in _RHI_PINS:
        out[family].insert(0, _rhi_build(family, "310.9.16", size, digest))
    for rows in out.values():
        rows.sort(key=_order, reverse=True)
    return out


def _refresh_family(family: str, items: list) -> dict | None:
    candidates = [item for item in items if isinstance(item, dict)
                  and _VERSION.fullmatch(str(item.get("version", "")))]
    if not candidates:
        return None
    best = max(candidates, key=lambda item: _version(item["version"]))
    version = best["version"]
    expected = _rhi_build(family, version, 0, "")
    if best.get("url") != expected["url"]:
        raise ValueError(f"{family}: unexpected runtime source URL")
    release = net.json_get(RHI_API + family + "-" + version)
    hits = [asset for asset in release.get("assets", [])
            if asset.get("browser_download_url") == expected["url"]]
    if len(hits) != 1:
        raise ValueError(f"{family}: missing or ambiguous release asset")
    asset = hits[0]
    digest = str(asset.get("digest", "")).removeprefix("sha256:")
    size = asset.get("size", 0)
    if not _SHA.fullmatch(digest) or not isinstance(size, int) or not 0 < size <= MAX_ARCHIVE:
        raise ValueError(f"{family}: release has no usable SHA256/size")
    return _rhi_build(family, version, size, digest)


def catalog(refresh: bool = False) -> dict:
    """Return detached catalog entries; a failed refresh preserves known pins."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = _pinned()
    if refresh:
        _refresh_publishers()
        try:
            feed = net.json_get(RHI_FEED)
            if not isinstance(feed, dict):
                raise ValueError("RHI runtime feed is not an object")
            with ThreadPoolExecutor(max_workers=3) as pool:
                jobs = {family: pool.submit(_refresh_family, family, feed.get(family, []))
                        for family in ("dlss", "dlssg", "dlssd")}
                for family, job in jobs.items():
                    try:
                        entry = job.result()
                        if entry:
                            rows = _CATALOG[family]
                            rows = [row for row in rows if row["label"] != entry["label"]]
                            _CATALOG[family] = sorted(rows + [entry], key=_order, reverse=True)
                    except Exception as exc:
                        log.write(f"runtime catalog {family}: {exc}; keeping verified pins", "warn")
        except Exception as exc:
            log.write(f"runtime catalog refresh: {exc}; keeping verified pins", "warn")
    return copy.deepcopy(_CATALOG)


def _verify(path: Path, digest: str = "", size: int = 0, version: str = "") -> None:
    if not 0 < path.stat().st_size <= MAX_FILE or (size and path.stat().st_size != size):
        raise ValueError("Runtime size differs from the verified source")
    if digest and net.sha256(path) != digest:
        raise ValueError("Runtime SHA256 differs from the verified source")
    if pe.exe_bitness(path) != 64:
        raise ValueError("Runtime is not an x64 Windows binary")
    with path.open("rb") as stream:
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset + 22)
        flags, magic = struct.unpack("<HH", stream.read(4))
    if not flags & 0x2000 or magic != 0x20B:
        raise ValueError("Runtime is not a Windows x64 DLL")
    # A mirror's release label does not establish the version of its payload.
    if version and os.name == "nt":
        actual = pe.file_version(path)
        if not actual or _version(actual) != _version(version):
            raise ValueError(f"Runtime FileVersion {actual or 'missing'} differs from {version}")


def _extract(archive: Path, name: str, dest: Path) -> None:
    # Authenticate the archive first; no member path is ever used as a write path.
    with zipfile.ZipFile(archive) as zipped:
        infos = zipped.infolist()
        if len(infos) > 128 or sum(info.file_size for info in infos) > MAX_FILE:
            raise ValueError("Runtime archive is too large")
        seen, matches = set(), []
        for info in infos:
            path = PurePosixPath(info.filename.replace("\\", "/"))
            key = str(path).casefold()
            if (path.is_absolute() or ".." in path.parts or ":" in str(path)
                    or key in seen or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError("Unsafe or duplicate runtime archive member")
            seen.add(key)
            if (info.file_size > MAX_FILE or info.flag_bits & 1
                    or info.file_size > max(1, info.compress_size) * 200):
                raise ValueError("Unsafe runtime archive size or encryption")
            if info.is_dir():
                continue
            if path.name.casefold() == name.casefold():
                matches.append(info)
            elif path.suffix.casefold() not in (".txt", ".md", ".rst", ".pdf"):
                raise ValueError("Unexpected payload in runtime archive")
        if len(matches) != 1:
            raise ValueError(f"Runtime archive must contain exactly one {name}")
        with zipped.open(matches[0]) as source, dest.open("wb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)


def _signature(path: Path) -> dict:
    """Ask Windows to verify Authenticode; the filename is data, never shell code."""
    if os.name != "nt":
        raise ValueError("New mirror runtimes require Windows publisher-signature verification")
    import ctypes
    import subprocess
    from . import child, selfupdate
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if not 0 < length < len(buffer):
        raise ValueError("Cannot locate Windows signature-verification tools")
    executable = Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    script = """$ErrorActionPreference='Stop'
$env:PSModulePath=Join-Path $PSHOME 'Modules'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$signature=Get-AuthenticodeSignature -LiteralPath $env:DLSS5_AIO_VERIFY_PATH
$signer=''
if ($signature.SignerCertificate) { $signer=$signature.SignerCertificate.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::SimpleName,$false) }
$product=(Get-Item -LiteralPath $env:DLSS5_AIO_VERIFY_PATH).VersionInfo.ProductName
@{status=[string]$signature.Status;signer=$signer;product=$product}|ConvertTo-Json -Compress
"""
    environment = selfupdate.clean_env()
    environment["DLSS5_AIO_VERIFY_PATH"] = str(path.resolve())
    result = child.run([str(executable), "-NoLogo", "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", base64.b64encode(script.encode("utf-16le")).decode("ascii")],
                       env=environment, capture_output=True, encoding="utf8", timeout=45,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError("Windows could not verify the runtime's publisher signature")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise ValueError("Windows returned an invalid publisher-verification result") from error


def _verify_publisher(path: Path, family: str) -> None:
    """A mirror's or a repository's own hash cannot prove a DLL came from its publisher."""
    signature = _signature(path)
    signers = _SIGNERS.get(family)
    if (not signers or not isinstance(signature, dict)
            or signature.get("status") != "Valid" or signature.get("signer") not in signers):
        raise ValueError("New runtime has no valid publisher signature")
    # Signed SR, RR and FG can share a version; a renamed DLL is still the wrong ABI.
    products = {"dlss": "NVIDIA Deep Learning SuperSampling",
                "dlssg": "NVIDIA DLSS-G MFGLW",
                "dlssd": "NVIDIA DLSS Ray Reconstruction"}
    if family in products and signature.get("product") != products[family]:
        raise ValueError("New runtime's signed product identity differs from its family")


def _git_blob_id(path: Path) -> str:
    """The id Git gives a file's bytes, which GitHub lists for every file in a tree."""
    import hashlib
    h = hashlib.sha1(b"blob %d\0" % path.stat().st_size)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _take_publisher_build(repo: str, commit: str, family: str, item: dict | None) -> None:
    """Add the publisher's current file for `family` if the catalog does not have it yet."""
    if not item:
        return
    blob, size = str(item.get("sha", "")), item.get("size")
    if not _SHA1.fullmatch(blob) or not isinstance(size, int) or not 0 < size <= MAX_FILE:
        raise ValueError("the repository listing is unusable")
    if any(row.get("blob") == blob for row in _CATALOG[family]):
        return
    url = f"https://raw.githubusercontent.com/{repo}/{commit}/{item['path']}"
    with _CACHE_LOCK, net.cache_locked():
        got = net.download(url, f"publisher-{family}-{blob}.dll", max_bytes=size)
        try:
            if got.stat().st_size != size or _git_blob_id(got) != blob:
                raise ValueError("download does not match the repository's own file id")
            _verify(got, "", size)
            _verify_publisher(got, family)
            version = pe.file_version(got) or ""
            if not _VERSION.fullmatch(version):
                raise ValueError(f"unreadable FileVersion {version!r}")
            digest = net.sha256(got)
            dest = net.cache_dir() / f"runtime-{family}-{digest}.dll"
            got.replace(dest)
        except Exception:
            got.unlink(missing_ok=True)
            raise
    folder = item["path"][:-len(FILE_OF[family])]
    entry = _entry(family, version, size, digest, repo, commit, folder, blob)
    if family in ("fsr4", "fsr4_fg"):
        loader = max((row for row in _CATALOG["fsr_loader"] if row.get("source", "").endswith(commit)),
                     key=lambda row: _version(row["version"]), default=None)
        if loader:
            entry["requires"] = {FILE_OF["fsr_loader"]: loader["version"]}
    rows = [row for row in _CATALOG[family] if row["version"] != version]
    _CATALOG[family] = sorted(rows + [entry], key=_order, reverse=True)
    log.write(f"runtime catalog {family}: {version} from {repo}@{commit[:10]}")


def _refresh_publishers() -> None:
    """Newest signed builds straight from NVIDIA's, AMD's and Intel's own repositories.

    A repository is read only when its head is not a commit already known, and a file is
    downloaded only when GitHub lists a blob the catalog does not have. Each download must
    match the blob id GitHub lists, be a valid x64 DLL, carry the publisher's signature and
    a readable FileVersion. Any failure keeps the pins already verified.
    """
    repos: dict[str, dict] = {}
    for family, _v, _s, _d, repo, commit, folder in _PINS + _PINS_LATEST:
        info = repos.setdefault(repo, {"folders": {}, "known": set()})
        info["folders"][family] = folder
        info["known"].add(commit)
    for repo, info in repos.items():
        try:
            head = str(net.json_get(f"https://api.github.com/repos/{repo}/commits/HEAD").get("sha", ""))
            if not _SHA1.fullmatch(head):
                raise ValueError("no usable head commit")
            if head in info["known"] or any(row.get("source", "").endswith(head)
                                            for rows in _CATALOG.values() for row in rows):
                continue
            tree = net.json_get(f"https://api.github.com/repos/{repo}/git/trees/{head}?recursive=1")
            if not isinstance(tree, dict) or tree.get("truncated"):
                raise ValueError("repository listing is incomplete")
            files = {t.get("path"): t for t in tree.get("tree", []) if t.get("type") == "blob"}
        except Exception as exc:
            log.write(f"runtime catalog {repo}: {exc}; keeping verified pins", "warn")
            continue
        # loaders first: an upscaler's `requires` names the loader of its own commit
        for family in sorted(info["folders"], key=lambda f: f != "fsr_loader"):
            try:
                _take_publisher_build(repo, head, family, files.get(info["folders"][family] + FILE_OF[family]))
            except Exception as exc:
                log.write(f"runtime catalog {family}: {exc}; keeping verified pins", "warn")


def resolve(build: dict, family: str, progress=None) -> Path:
    """Download and validate a catalog build before the updater touches a game."""
    # Different games share digest-addressed downloads and their partial files.
    with _CACHE_LOCK, net.cache_locked():
        return _resolve(build, family, progress)


def _resolve(build: dict, family: str, progress=None) -> Path:
    if family not in FILE_OF or build.get("member") != FILE_OF[family]:
        raise ValueError("Runtime family/filename does not match")
    url = str(build.get("url", ""))
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ("raw.githubusercontent.com", "github.com")
            or parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment):
        raise ValueError("Unexpected runtime download host")
    raw = build.get("raw") is True
    digest = build.get("sha256" if raw else "archive_sha256", "")
    if not isinstance(digest, str) or not _SHA.fullmatch(digest):
        raise ValueError("Runtime download has no expected SHA256")
    size = build.get("size" if raw else "archive_size", 0)
    if not isinstance(size, int) or not 0 < size <= MAX_ARCHIVE:
        raise ValueError("Runtime download has no expected size")
    dest = net.cache_dir() / f"runtime-{family}-{digest}.dll"
    if _SHA.fullmatch(str(build.get("sha256", ""))) and dest.is_file():
        try:
            _verify(dest, build["sha256"], int(build.get("size") or 0), build.get("version", ""))
            return dest
        except (ValueError, OSError, pe.PEError, struct.error):
            dest.unlink(missing_ok=True)
    suffix = ".dll" if raw else ".zip"
    got = net.download(url, f"runtime-{family}-{digest}{suffix}", progress=progress, max_bytes=size)
    try:
        if got.stat().st_size != size or net.sha256(got) != digest:
            raise ValueError("Runtime download failed its source SHA256/size check")
        if raw:
            _verify(got, digest, size, build.get("version", ""))
            return got
        with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".dll", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            _extract(got, FILE_OF[family], temporary)
            _verify(temporary, build.get("sha256", ""), int(build.get("size") or 0), build.get("version", ""))
            if not build.get("sha256"):
                _verify_publisher(temporary, family)
            temporary.replace(dest)
        finally:
            temporary.unlink(missing_ok=True)
        return dest
    except Exception:
        # A bad cached download must not poison every subsequent retry.
        got.unlink(missing_ok=True)
        raise
