# Runtime sources and verified versions

Runtime snapshot rechecked October 30, 2026 against the publishers' own repositories (NVIDIA/DLSS v310.9.16, AMD FidelityFX SDK 2.4.0, intel/xess v3.0.2); download and recovery boundaries re-audited October 15 for v2.0.1. Since 2.2.0 the app also asks the publishers itself, see "Live refresh" below. Runtime maintenance and DLSS 5 neural rendering are separate workflows: replacing a DLL updates an existing compatible integration; it cannot create one.

## What is available

[NVIDIA's October 13 announcement](https://www.nvidia.com/en-us/geforce/news/dlss-5-faster-ai-model-hogwarts-legacy-rtx-spark-laptops/) schedules the faster DLSS 5 neural-rendering model for October 16. It does not establish a released October 14 NR DLL. The October 13 Frame Generation Preset C beta is a separate performance change; SR/RR/FG build 310.9.16 must not be described as the upcoming faster NR model.

| Existing runtime filename | Verified FileVersion | Source |
| --- | --- | --- |
| `nvngx_dlss.dll`, `nvngx_dlssg.dll`, `nvngx_dlssd.dll` | 310.9.16 | NVIDIA/DLSS SDK 310.9.16 (`9981c6350dc58c0ce21f024fd65e31e851c31689`), NVIDIA signature Valid; the RHI community mirror carries the same version as an alternative |
| `libxess.dll`, `libxess_dx11.dll` | 2.0.2.68 | Intel XeSS SDK 3.0.2 |
| `libxess_fg.dll` | 1.3.1.78 | Intel XeSS SDK 3.0.2 |
| `libxell.dll` | 1.3.2.10 | Intel XeSS SDK 3.0.2 |
| `amd_fidelityfx_dx12.dll`, `amd_fidelityfx_vk.dll` | 1.0.1.41314 | AMD FidelityFX SDK 1.1.4; combined FSR 3.1 layout |
| `amd_fidelityfx_loader_dx12.dll` | 2.3.0.4555 | AMD FidelityFX SDK 2.4.0 (`7539ae8b6568ad29ed78a753404351daf3b5cca7`); split layout, AMD signature Valid |
| `amd_fidelityfx_upscaler_dx12.dll` | 4.1.2.4555 | AMD FidelityFX SDK 2.4.0; split layout |
| `amd_fidelityfx_framegeneration_dx12.dll` | 4.0.2.4555 | AMD FidelityFX SDK 2.4.0; split layout |

SDK release numbers, DLL FileVersions and product names are different identifiers. In particular, XeSS SDK 3.0.2 contains SR DLL 2.0.2.68. A legacy combined AMD DLL's FileVersion does not turn it into FSR 4. The split AMD effects require an existing compatible loader of the same SDK (2.3.0.4555 for the 2.4.0 builds) or newer in the same directory; AIO does not rename them over combined or `ffx_fsr3*` DLLs.

## Immutable provenance

The catalog in [`app/core/runtimecatalog.py`](https://github.com/SenjuWoo/dlss5-aio/blob/main/app/core/runtimecatalog.py) records exact filenames, byte sizes and SHA256 values. Official raw binaries use commit URLs, not mutable branch URLs:

- [NVIDIA/DLSS at `374959484e79a640feaba44c93ac8cfb0a03f5b5`](https://github.com/NVIDIA/DLSS/tree/374959484e79a640feaba44c93ac8cfb0a03f5b5/lib/Windows_x86_64/rel): SDK 310.9.1 fallbacks for SR/RR/FG. This official SDK tree contains no NR DLL.
- [Intel XeSS at `8fe81bdbbaf00b3c1b733fd0d830c333dc84e6f0`](https://github.com/intel/xess/tree/8fe81bdbbaf00b3c1b733fd0d830c333dc84e6f0/bin): SR, DX11 bridge, FG and XeLL.
- [AMD FidelityFX at `60f4ea81909200d8542eca14dccb2628b763a9a3`](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK/tree/60f4ea81909200d8542eca14dccb2628b763a9a3/Kits/FidelityFX/signedbin): current split loader/effects.
- [AMD FidelityFX at `c6efa6bf7f2027b3ec94f28578bb5965eabb9e55`](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK/tree/c6efa6bf7f2027b3ec94f28578bb5965eabb9e55/PrebuiltSignedDLL): legacy combined DX12/Vulkan binaries.

The newer NVIDIA mirror records originate in the [RHI manifest snapshot at `b0570336431bfce265e0f6dc19156ea751e404f7`](https://raw.githubusercontent.com/RankFTW/RHI/b0570336431bfce265e0f6dc19156ea751e404f7/dlss_manifest.json). The manifest has no checksums. AIO resolves each exact URL against its GitHub release asset and requires that asset's SHA256 digest and size. The bundled snapshot additionally pins the independently extracted DLL digest and size:

| RHI asset | Archive SHA256 | DLL SHA256 |
| --- | --- | --- |
| [SR 310.9.16](https://github.com/RankFTW/rhi-repo/releases/tag/dlss-310.9.16) | `1823ec911c77482e6731447dfb0db3def8aa710e092f59f58c4c4c55285d492d` | `858ccff96360c3098db9264cd6f13d04a027e09b6ce7ad5bbc297570e824b4f2` |
| [FG 310.9.16](https://github.com/RankFTW/rhi-repo/releases/tag/dlssg-310.9.16) | `20f967c689e73803769df30a63b9d70fa6339257c1612d687b7414aabf847766` | `cadee1aa6db3907babdc3285da2aebc4553d92b89c38ba3eae8abd8bba1bea72` |
| [RR 310.9.16](https://github.com/RankFTW/rhi-repo/releases/tag/dlssd-310.9.16) | `33470176d595838fb8751023c56e1e2b56e0da8d19c5c140b1bb325a53984ff2` | `7006c3a729276e876e06a97c6262672a1be96a58d69b0e85877f911146b98fbe` |

RHI is a community host. A GitHub digest authenticates the retrieved asset bytes; it does not make that repository an NVIDIA publisher. The original audit verified all 12 snapshot families against their expected digest/size, x64 DLL format and actual Windows FileVersion, then checked Windows Authenticode: 12/12 Valid, with NVIDIA, Intel or AMD publishers. This evidence applies to those exact bytes.

In v2.0.1, refreshed NVIDIA mirror entries without a bundled extracted-DLL SHA256 also require fresh Windows Authenticode verification: status `Valid` and signer `NVIDIA Corporation`, plus matching runtime-family product metadata. Verification fails closed if Windows cannot establish that result. Known extracted-DLL pins remain usable offline by checking the exact previously audited SHA256/size, format and FileVersion. The release asset digest, safe archive layout and matching filename are required in both cases. No runtime DLL is loaded or executed during validation.

## Refresh and compatibility limits

## Live refresh

The first runtime lookup of every run, and every **Check again**, asks the publishers: for NVIDIA/DLSS, GPUOpen FidelityFX-SDK and intel/xess the app reads the repository's head commit and file listing from the GitHub API. Only when the head commit is new and a listed file's Git blob id is one the catalog does not already hold is that file downloaded, from its commit-addressed URL. The bytes must match the blob id GitHub lists, be an x64 DLL, carry a valid Authenticode signature from the publisher (NVIDIA Corporation, Advanced Micro Devices, or Intel Corporation; the NVIDIA product name must also match the family), and expose a readable FileVersion, which becomes the build's version. The community RHI feed is still consulted for NVIDIA. A failed lookup, a mismatch or a missing signature retains the verified pins below; offline use is unaffected. The FSR 3.1 DLLs are no longer in the AMD repository's head and stay pinned.

The shipped pins are the offline snapshot. A failed feed or asset lookup retains verified entries. Changing a remote asset cannot silently change a bundled pin's bytes: downloads and cached files must still match the expected digest.

Archives must contain exactly one expected DLL basename and optional documentation. Traversal, duplicate names, symlinks, encryption, unrelated executable payloads and excessive expansion are refused. Downloads stay in AIO's cache until the updater rechecks the game's current bytes, preserves its original, and stages a verified replacement.

Runtime resolution serializes shared cache writes across threads and uses an operating-system cache lock across AIO processes. Another process holding that lock is refused safely; retry after it finishes. Downloads bind their cache entries to the exact source URL. A failed refresh preserves the earlier completed cache entry instead of replacing it with partial bytes.

The expected archive/file size is capped at 256 MiB. Runtime downloads pass that exact expected size as the transport's `max_bytes`; declared and streamed response sizes are bounded, then exact size and SHA256 are checked before extraction or placement. Small API/HTML responses and extractor subprocess output have separate bounds. Archive inspection precedes extraction, and extractor timeouts terminate and reap the owned child process.

Installation and runtime restoration use durable recovery records and staged, byte-verified copies. Later personal edits are preserved separately. Historical install, emulator or ASI-loader backups without ownership hashes are retained for review rather than silently treated as verified originals. Other applications do not share AIO's game/profile/cache locks; close them before modifying the same files.

NR selection belongs to the neural-rendering installer. The inspected community feed lists SF-v2 (310.8.2, RTX 20/30/40/50) separately from Lecram (310.8.3, RTX 50 only). Picking the first NR entry globally would be wrong for an RTX 4080. Neither entry proves availability of the October 16 model. Proxy/cost-scaler installations also require preserving their renamed real NR DLL and ownership records; generic runtime refresh does not overwrite that layout.

Publisher license conditions still apply. AIO downloads runtime binaries when needed rather than bundling proprietary runtime payloads in its application ZIP. NVIDIA's SDK, current AMD binary terms and Intel's binary license are distinct; community hosting is not a redistribution grant.
