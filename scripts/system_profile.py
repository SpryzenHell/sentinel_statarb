import json
import os
import platform
from pathlib import Path

def read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding='utf-8').strip()
    except (OSError, UnicodeDecodeError):
        return None

def main() -> None:
    cpuinfo = read('/proc/cpuinfo') or ''
    model = next((line.split(':', 1)[1].strip() for line in cpuinfo.splitlines() if line.lower().startswith('model name')), platform.processor())
    result = {
        'platform': platform.platform(),
        'kernel': platform.release(),
        'machine': platform.machine(),
        'cpu_model': model,
        'logical_cpus': os.cpu_count(),
        'affinity_cpus': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        'transparent_hugepage': read('/sys/kernel/mm/transparent_hugepage/enabled'),
        'transparent_hugepage_defrag': read('/sys/kernel/mm/transparent_hugepage/defrag'),
        'hugepages_total': read('/proc/sys/vm/nr_hugepages'),
        'cpu_governor': read('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'),
    }
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()