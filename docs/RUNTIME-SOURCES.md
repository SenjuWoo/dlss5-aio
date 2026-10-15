# Runtime sources and verified versions

Snapshot checked October 14, 2026. Runtime maintenance and DLSS 5 neural rendering are separate workflows: replacing a DLL updates an existing compatible integration; it cannot create one.

## What is available

[NVIDIA's October 13 announcement](https://www.nvidia.com/en-us/geforce/news/dlss-5-faster-ai-model-hogwarts-legacy-rtx-spark-laptops/) schedules the faster DLSS 5 neural-rendering model for October 16. It does not establish a released October 14 NR DLL. The October 13 Frame Generation Preset C beta is a separate performance change; SR/RR/FG build 310.9.16 must not be described as the upcoming faster NR model.

| Existing runtime filename | Verified FileVersion | Source |
| --- | --- | --- |
| `nvngx_dlss.dll`, `nvngx_dlssg.dll`, `nvngx_dlssd.dll` | 310.9.16 | RHI community mirror; NVIDIA signatures verified during this audit |
| `libxess.dll`, `libxess_dx11.dll` | 2.0.2.68 | Intel XeSS SDK 3.0.2 |
| `libxess_fg.dll` | 1.3.1.78 | Intel XeSS SDK 3.0.2 |
| `libxell.dll` | 1.3.2.10 | Intel XeSS SDK 3.0.2 |
| `amd_fidelityfx_dx12.dll`, `amd_fidelityfx_vk.dll` | 1.0.1.41314 | AMD FidelityFX SDK 1.1.4; combined FSR 3.1 layout |
| `amd_fidelityfx_loader_dx12.dll` | 2.3.0.2740 | AMD FidelityFX SDK 2.3.0; split layout |
| `amd_fidelityfx_upscaler_dx12.dll` | 4.1.1.2740 | AMD FidelityFX SDK 2.3.0; split layout |
| `amd_fidelityfx_framegeneration_dx12.dll` | 4.0.1.2740 | AMD FidelityFX SDK 2.3.0; split layout |

SDK release numbers, DLL FileVersions and product names are different identifiers. In particular, XeSS SDK 3.0.2 contains SR DLL 2.0.2.68. A legacy combined AMD DLL's FileVersion does not turn it into FSR 4. The split AMD effects require an existing compatible loader 2.3.0.2740 or newer in the same directory; AIO does not rename them over combined or `ffx_fsr3*` DLLs.

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

RHI is a community host. A GitHub digest authenticates the retrieved asset bytes; it does not make that repository an NVIDIA publisher. The audit verified all 12 current families against their expected digest/size, x64 DLL format and actual Windows FileVersion, then checked Windows Authenticode: 12/12 Valid, with NVIDIA, Intel or AMD publishers. This is evidence for these exact files. New refreshed mirror entries require the release digest, safe archive layout, x64 DLL format and matching Windows FileVersion; the downloader does not perform a fresh Authenticode check on every future candidate. No DLL is executed during validation.

## Refresh and compatibility limits

The shipped AMD and Intel entries are a verified dated snapshot. **Check again** dynamically refreshes NVIDIA SR/RR/FG through RHI; it does not claim to discover future AMD or Intel SDK releases automatically. A failed feed or asset lookup retains verified entries. Changing a remote asset cannot silently change a bundled pin's bytes: downloads and cached files must still match the expected digest.

Archives must contain exactly one expected DLL basename and optional documentation. Traversal, duplicate names, symlinks, encryption, unrelated executable payloads and excessive expansion are refused. Downloads stay in AIO's cache until the updater rechecks the game's current bytes, preserves its original, and stages a verified replacement.

Runtime resolution serializes shared cache writes across threads and uses an operating-system cache lock across AIO processes. Another process holding that lock is refused safely; retry after it finishes. The expected archive/file size is capped at 256 MiB and checked after download. The inherited transport does not enforce a streaming byte cap, so an unexpectedly oversized server response can consume extra temporary disk space before it is rejected.

NR selection belongs to the neural-rendering installer. The inspected community feed lists SF-v2 (310.8.2, RTX 20/30/40/50) separately from Lecram (310.8.3, RTX 50 only). Picking the first NR entry globally would be wrong for an RTX 4080. Neither entry proves availability of the October 16 model. Proxy/cost-scaler installations also require preserving their renamed real NR DLL and ownership records; generic runtime refresh does not overwrite that layout.

Publisher license conditions still apply. AIO downloads runtime binaries when needed rather than bundling proprietary runtime payloads in its application ZIP. NVIDIA's SDK, current AMD binary terms and Intel's binary license are distinct; community hosting is not a redistribution grant.
