"""
Clear stale SA caches computed with old activity-throughput metric.
Run this script before re-running task3_2_clustering.ipynb from section 3.2.4.
"""

from pathlib import Path

CACHE_DIR = Path("../Data/Task3/cache")

cache_files_to_clear = [
    CACHE_DIR / "sa_best_assignment.npy",
    CACHE_DIR / "sa_best_fips.parquet",
    CACHE_DIR / "init_assignment.npy",
    CACHE_DIR / "init_assignment_fips.parquet",
]

print("Clearing stale SA caches (computed with activity throughput instead of external demand)...")
cleared_count = 0

for cache_file in cache_files_to_clear:
    if cache_file.exists():
        cache_file.unlink()
        print(f"  ✓ Deleted: {cache_file.name}")
        cleared_count += 1

if cleared_count > 0:
    print(f"\n{cleared_count} stale cache file(s) cleared.")
    print("Re-run task3_2_clustering.ipynb from section 3.2.4 to regenerate with external demand weights.")
else:
    print("No stale caches found.")
