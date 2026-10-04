import argparse
import platform
import subprocess
import sys
from pathlib import Path


def run_checked(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that a Sentinel checkout is usable.")
    parser.add_argument("--build-dir", type=Path, default=Path("build"))
    args = parser.parse_args()

    if sys.version_info < (3, 12):
        raise SystemExit("Python 3.12 or newer is required")

    try:
        import duckdb  # noqa: F401
        import numpy  # noqa: F401
        import zmq  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Python dependencies are missing. Run: pip install -e '.[full]'"
        ) from exc

    required = [
        args.build_dir / "sentinel" / "sentinel_engine_smoke",
        args.build_dir / "sentinel" / "sentinel_spsc_bench",
        args.build_dir / "sentinel" / "sentinel_exec",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(
            "Required build outputs are missing:\n  " + "\n  ".join(missing)
            + "\nRun: cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --parallel"
        )

    run_checked([str(required[0])])
    run_checked([str(required[2]), "--help"])

    print(f"platform={platform.platform()}")
    print(f"python={platform.python_version()}")
    print("sentinel_installation=OK")


if __name__ == "__main__":
    main()
