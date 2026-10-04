# Sentinel StatArb provenance

The active project is a composition: a Sentinel-specific research/risk/execution layer is built around three upstream repositories named in INPUT_projects.json.

| Upstream | Pinned source | Role |
|---|---|---|
| bmoscon/cryptofeed | master @ 6cbd9b959f104fe970791d32444a2ef13ddacc2f | normalized public L2/L3/trade market-data callbacks and optional live-feed adapter |
| cantaro86/Financial-Models-Numerical-Methods | master @ 65a8124c4fdf80f8cf7de234be9f8393927b8488 | Kalman/regression and numerical-method research reference |
| rigtorp/SPSCQueue | master @ 1053918dbd251fbff69b24ef27fa5d51c29ec2af | wait-free/lock-free SPSC queue used at the execution boundary |

The exact intended repository mapping is preserved in INPUT_projects.json.

The previous automated merge remains in sentCryptofeed/, sentSrc/, and sentTests/ for provenance. Its global token renaming changed source syntax, so the active Sentinel implementation does not import those corrupted modules.
