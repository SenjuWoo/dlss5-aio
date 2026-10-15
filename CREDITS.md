# Credits

DLSS 5 AIO is maintained by **SenjuWoo**.

- Game installer, route selection, discovery, diagnostics and interface: adapted from [DLSS5-Autopilot](https://github.com/Kizzuwatnaa/DLSS5-Autopilot), MIT. Exact commit and modifications: [app/UPSTREAM.md](app/UPSTREAM.md); retained license: [app/UPSTREAM-LICENSE.txt](app/UPSTREAM-LICENSE.txt).
- NVIDIA DLSS and Streamline: NVIDIA; proprietary SDK/component licenses. Current maintenance build provenance: [runtime sources](docs/RUNTIME-SOURCES.md).
- AMD FidelityFX: [GPUOpen](https://github.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK), component licenses.
- Intel XeSS and XeLL: [Intel](https://github.com/intel/xess), SDK license.
- Runtime mirror metadata and community components: [RHI](https://github.com/RankFTW/RHI) and [rhi-repo](https://github.com/RankFTW/rhi-repo). Community-hosted files are distinguished from publisher SDK releases.
- ReShade: [crosire](https://github.com/crosire/reshade), BSD-3-Clause.
- Feeder/helper: [DLSS5-Feeder](https://github.com/jlrouzies-fr/DLSS5-Feeder); bridge: [NIGos](https://github.com/NIGos/dlss5-bridge); upstream pass: [neural-upstream](https://github.com/matiasLombo/neural-upstream); standalone: [DLSS5-Reshade-AIO](https://github.com/kibblerz/DLSS5-Reshade-AIO).
- OptiScaler and its NR forks retain their authors' GPL/component licenses. They are downloaded for the selected route, not included in the portable application.
- DXVK: [doitsujin](https://github.com/doitsujin/dxvk), zlib/libpng.
- Motion-vector shaders retain their own licenses. Restricted providers are fetched from their publishers for the selected installation and are not redistributed in the release payload.

The application does not claim ownership of upstream components. It is not affiliated with NVIDIA, AMD or Intel. See [LICENSE.md](LICENSE.md) for the distinction between AIO source, the portable payload and legacy pack components.
