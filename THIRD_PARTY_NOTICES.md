# Third-party notices

Sentinel uses or references the following upstream projects. Their code remains subject to their respective licenses.

| Project | Usage in Sentinel | License/source |
|---|---|---|
| [bmoscon/cryptofeed](https://github.com/bmoscon/cryptofeed) | Optional live L2 feed adapter | AGPL-3.0-or-later; see upstream repository |
| [cantaro86/Financial-Models-Numerical-Methods](https://github.com/cantaro86/Financial-Models-Numerical-Methods) | Research reference for Kalman/numerical methods | AGPL-3.0; see upstream repository |
| [rigtorp/SPSCQueue](https://github.com/rigtorp/SPSCQueue) | Vendored queue implementation on the C++ execution boundary | MIT; license text retained at vendor/rigtorp/LICENSE.txt |

The active Sentinel-specific implementation is separated under `sentinel/`, `python/sentinel_statarb/`, and `scripts/`. The older automated merge trees remain under `sentCryptofeed/`, `sentSrc/`, and `sentTests/` as historical provenance and are not imported by the active build.

For redistribution or deployment, review the current upstream license text and the exact files shipped in the repository.
