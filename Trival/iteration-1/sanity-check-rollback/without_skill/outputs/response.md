# Negative Travel Times in the Task 5 Distance Matrix — Do Not Clip

## Short answer: No, do not clip to zero and move on.

Negative travel times are physically impossible and indicate a data integrity failure upstream of the optimization. Silently patching them with `np.clip(..., 0, None)` or equivalent does not fix the problem — it hides it, corrupts your hub network, and invalidates every downstream result (Task 6 area clustering, Task 7 multi-tier integration, Task 8 flow assignment). The optimization solver may technically complete, but the selected hubs and link costs will be wrong.

---

## What you should do instead

### 1. Stop and roll back the working state

Before touching anything, preserve your current state and roll back to the last clean commit so you have a known-good baseline to compare against:

```bash
git status                  # verify what has changed
git stash                   # stash any uncommitted edits if you want to keep them
git reset --hard HEAD       # or: git checkout <last-clean-commit-sha>
```

If you have not been committing incrementally during Task 5, at minimum make a checkpoint commit of the broken state right now so you can diff against it:

```bash
git add -p                  # stage only your Task 5 code files
git commit -m "wip: Task 5 broken state — negative travel times in distance matrix"
```

### 2. File an issue report before investigating

Document the failure in a structured way before you start changing code. Use the following schema (save as `Issue_Report.md` in your Task 5 folder or a `/Doc/issues/` directory):

```
Issue:           Negative travel times in regional hub distance matrix
Timestamp:       <ISO 8601 timestamp of when you observed this>
Failure Point:   Distance matrix construction step in Task 5 hub selection
Expected Bound:  All pairwise travel times >= 0 hours (hard physical constraint;
                 regional hub connectivity constraint is <= 5.5h per §2.3)
Actual Output:   Some off-diagonal matrix entries contain negative float values
Action Taken:    <fill in as you investigate>
```

### 3. Diagnose the root cause — do not guess

Negative travel times almost always trace back to one of these sources. Work through them in order:

**a) Coordinate/projection error in the distance or time calculation**

If you computed travel time from a road-network API or haversine distance:
- Verify hub coordinates are in the correct CRS (WGS84 lon/lat if using haversine or OSRM; projected meters if using a planar formula).
- Check for swapped latitude/longitude. A hub placed in the ocean or at a nonsensical location can produce bogus routing results.
- If you used a speed assumption to convert distance to time (e.g., `distance_km / avg_speed_kmh`), verify the speed constant is positive and in consistent units.

**b) Subtraction or arithmetic sign error**

If your matrix was built with any formula like `time_ij = something - something_else`, check whether the subtracted term can exceed the first. This is a common bug when normalizing or adjusting raw API results.

**c) Data source contamination**

If the distance matrix was loaded from a pre-computed file (e.g., a cached `.csv` or `.parquet`), the source file itself may be corrupt. Re-examine it:

```python
import pandas as pd
dm = pd.read_parquet("path/to/distance_matrix.parquet")
print((dm < 0).sum().sum())          # how many negatives?
print(dm[dm < 0].stack().head(20))   # which hub pairs are affected?
```

Compare the geographic spread of affected pairs — if negatives cluster around specific hubs, those hubs have bad coordinates.

**d) Diagonal entries or self-loops**

If even diagonal entries are negative (same-hub travel time), the bug is earlier than pairwise calculation — likely a misaligned index or a hub dataframe that got shuffled before matrix construction.

### 4. Verify the fix with a sanity check before re-running optimization

Once you identify and fix the root cause, add a hard assertion before the optimization runs:

```python
assert (distance_matrix >= 0).all().all(), \
    "Distance matrix contains negative values — check coordinate CRS and computation logic"
assert (distance_matrix.diagonal() == 0).all(), \
    "Self-loop travel times must be zero"
```

Also verify against the project's connectivity constraint from §2.3 of the methodology: no neighboring hub pair should exceed 5.5 hours. Flag (but do not silently drop) any pairs that violate this as a separate warning — those are candidates for hub repositioning, not data errors.

### 5. Only then re-run the optimization

Once the matrix passes all sanity checks, re-run the set-cover or heuristic hub selection. Do not carry forward any results from the run with the corrupted matrix.

---

## Why clipping is wrong here

Clipping negative values to zero tells the optimizer that some hub pairs have zero travel time between them — effectively treating them as co-located. This will:

- Artificially inflate connectivity of certain hub pairs, causing the optimizer to favor them even if they are geographically distant.
- Produce a hub selection that does not satisfy the ≤ 5.5h neighboring-hub constraint from §2.3.
- Cascade errors into Task 7 (multi-tier integration uses these hub links) and Task 8 (flow assignment costs depend on them).

A few minutes of investigation now saves invalidating all downstream tasks.
