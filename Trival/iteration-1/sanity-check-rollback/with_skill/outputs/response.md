# Response: Negative Travel Times in Task 5 Distance Matrix

**Do not clip the values to zero and move on.** Negative travel times are a hard sanity-check failure, and the correct protocol is to stop, roll back, and investigate the root cause before proceeding.

---

## Why clipping is the wrong move

Clipping negative values to zero would silently corrupt the distance matrix fed into the hub selection optimizer. The optimizer would treat zero-travel-time links as costless connections, which would bias hub placement — likely collapsing multiple hubs onto the same location or producing infeasible coverage assignments. Worse, this corruption would propagate silently into Tasks 6, 7, and 8 (area delineation, flow assignment), making those results unreliable in ways that are very hard to diagnose later.

The constraint from `Task.md` is unambiguous: all `Link.travel_time_h` values must be non-negative. A negative value is not a rounding artifact — it signals a real defect upstream.

---

## What to do right now

### 1. Roll back to the last stable commit

```bash
git reset --hard HEAD
```

This puts the repository back in its last known-good state. Do not save or commit any notebook output that contains the corrupted distance matrix.

### 2. Write an Issue Report

Create `Issue_Report.md` in the project root with the following content (fill in actual values):

```yaml
Issue: Task 5 — Hub selection distance matrix
Timestamp: <ISO 8601 datetime, e.g. 2026-04-08T10:00:00>
Failure Point: Distance matrix computation cell / Link construction
Expected Bound: All link travel_time_h >= 0
Actual Output: min(travel_time_h) = <value, e.g. -0.34>
Action Taken: Rolled back to last stable commit. Awaiting root cause investigation.
```

### 3. Investigate the root cause before rerunning

Do not rerun the distance matrix computation until you understand why negatives appeared. Common causes for this failure in the Task 5 pipeline:

**Coordinate or unit error**
- Are coordinates in (lon, lat) order consistently? A lat/lon swap can produce nonsensical Haversine distances that, after a speed-division step, might produce negatives if a sign error crept in.
- Are you dividing by average speed in the right units? If speed is in km/h but distance is in miles (or vice versa), the result can be wrong in sign or magnitude.

**Subtraction in a derived travel-time formula**
- If travel time is computed as a difference (e.g., `arrival_time - departure_time` from a routing API response), check whether any timestamps are malformed or out-of-order.
- If you applied a road-network correction factor (e.g., a circuity factor subtracted from something), check whether that term can exceed the base value.

**Pandas-to-numpy boundary bug**
- If the distance matrix was assembled from a pandas DataFrame with mixed dtypes before conversion to numpy, a silent coercion could have introduced NaN values that later became negative via arithmetic (e.g., `0 - NaN` interpreted as a large negative in a masked array context).

**Wrong node pair indexing**
- If the matrix is built with a manual index loop and the node list was reordered or filtered between building the coordinate array and building the matrix, off-by-one index mismatches can produce cross-subtracted values.

---

## How to rebuild safely (once the root cause is identified)

Follow the Step 3–5 cell pattern from the coder skill:

```
[Markdown]  ## 5.x — Travel-time matrix
            Formula: t_{ij} = d_{ij} / v_avg
            where d_{ij} is Haversine distance in km, v_avg = 65 km/h

[Code]      # Load node coordinates (pandas → numpy boundary)
            coords = node_df[["lon", "lat"]].to_numpy()

[Code]      # Compute distance matrix (pure numpy)
            dist_matrix = haversine_matrix(coords)   # shape (N, N), km

[Code]      # Sanity check: distances
            assert dist_matrix.min() >= 0, f"Negative distance: {dist_matrix.min():.4f} km"
            assert np.diag(dist_matrix).max() == 0, "Diagonal should be zero"

[Code]      # Compute travel-time matrix
            AVG_SPEED_KMH = 65.0
            time_matrix = dist_matrix / AVG_SPEED_KMH   # hours

[Code]      # Sanity check: travel times
            assert time_matrix.min() >= 0, \
                f"Negative travel time detected: {time_matrix.min():.4f} h"
            print(f"Travel time range: [{time_matrix.min():.3f}, {time_matrix.max():.2f}] h")
            print(f"Max inter-hub time: {time_matrix.max():.2f}h (constraint: <= 5.5h)")

[Code]      # Serialize
            np.save("Data/Task5/travel_time_matrix.npy", time_matrix)
```

Place the sanity check *before* you pass the matrix to the optimizer — not after. If the assert fires, stop and do not proceed.

---

## Summary

| Step | Action |
|------|--------|
| Immediate | `git reset --hard HEAD` |
| Document | Write `Issue_Report.md` with actual failure values |
| Investigate | Identify root cause (coordinate order, unit mismatch, indexing bug) |
| Rebuild | Add pre-optimizer sanity check asserting `time_matrix.min() >= 0` |
| Commit | Only after sanity checks pass and you have confirmed the fix |

Negative travel times are a pipeline-integrity signal, not a data-cleaning problem. Fix the source, not the symptom.
