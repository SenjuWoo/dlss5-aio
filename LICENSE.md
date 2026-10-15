# Licensing

DLSS 5 AIO's original assembly, documentation and changes are MIT-licensed: [LICENSE](LICENSE). The adapted Autopilot source retains [its MIT notice](app/UPSTREAM-LICENSE.txt), with provenance in [app/UPSTREAM.md](app/UPSTREAM.md).

The portable application includes the Python/Tcl/Tk runtime needed to run it; their license notices are included in the release. PyInstaller's bootloader exception permits distribution of the frozen application under its own license.

NVIDIA, AMD and Intel DLLs, ReShade add-ons, Feeder, OptiScaler, DXVK, motion-vector providers and other route components are **not bundled in the new portable release**. They are fetched from their recorded publishers or explicitly identified community sources when needed, and retain their respective licenses. AIO's MIT license does not relicense these components or their assets.

Folders 01–06 and the v1.4.8 archive are legacy references. Their component-specific licenses remain applicable; the root legacy SHA256 manifest does not establish redistribution permission or publisher provenance. Prefer upstream sources for current downloads.
