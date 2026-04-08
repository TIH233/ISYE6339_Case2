---
name: coder
description: >
  Use this skill whenever the user asks to implement, code, build, or work on any
  computational task (Task 3 through Task 9) in this freight network optimization project.
  Trigger on phrases like "implement Task 3", "let's build the clustering notebook",
  "code up the hub selection", "start Task 5", "work on flow assignment", or any request
  to write Python code in a Jupyter notebook for this project. Always invoke this skill
  before writing any notebook cell — it defines the coding standards, data conventions,
  and commit/rollback gates that keep the pipeline consistent and reproducible.
user-invocable: true
---

# Coder — Notebook Implementation Guide

This skill governs how every computational task (Tasks 3–9) is built in this project.
The goal is a pipeline that is mathematically transparent, computationally efficient,
fault-tolerant, and cleanly version-controlled. Follow the sections below in order.

---

## Step 0 — Load context before writing a single line

Run the `retriever` skill to fetch the relevant Task.md block and any data schemas you'll
touch. This is not optional — writing code against a schema you haven't confirmed wastes
a full debug cycle.

```bash
# Get the task description
awk '/^### Task N/{flag=1; print; next} /^###/{if(flag) exit} flag' Doc/Task.md

# Get schemas for each input file you'll load
awk '/^## .*FILENAME/{flag=1; print; next} /^#/{if(flag) exit} flag' Doc/Data.md
```

Confirm: task objective, expected outputs, input file paths and column names.
Do not proceed until you can answer: *what does this subtask produce and how do I verify it?*

---

## Step 1 — Notebook structure

Each task lives in its own notebook: `Task<N>/task<N>_notebook.ipynb`

Open the notebook (or create it) and use this cell-level pattern throughout:

```
[Markdown cell]  ← Theory: LaTeX equations, constraints, variable definitions
[Code cell]      ← Implementation: one logical operation
[Code cell]      ← Sanity check: assert bounds, print shape/stats
```

The Markdown cell bridges theory to code. Write the governing equation or constraint
before you implement it, e.g.:

```markdown
## 3.2 — Demand-weighted centroid
The cluster centroid $c_k$ is the tonnage-weighted mean of county centroids:
$$c_k = \frac{\sum_{i \in C_k} d_i \cdot \mathbf{x}_i}{\sum_{i \in C_k} d_i}$$
where $d_i$ is the 2025 truck tonnage for county $i$ and $\mathbf{x}_i = (\text{lon}_i, \text{lat}_i)$.
```

This discipline keeps the notebook a living document, not just a script.

---

## Step 2 — Data layer rules

The two layers must never mix in the same active data structure:

| Layer | Tool | When |
|-------|------|------|
| **Computation** | `numpy` | Distance matrices, solver inputs, matrix ops, graph algorithms |
| **Snapshots** | `pandas` | Reading raw CSVs/parquet, writing outputs, human-readable checkpoints |

**Boundaries** are the only places you convert between them:

```python
# Loading (pandas → numpy)
df = pd.read_parquet("Data/Task1/raw.parquet")
demand = df["tons_2025"].to_numpy()          # enter compute layer

# ... numpy operations ...

# Outputting (numpy → pandas)
result_df = pd.DataFrame({"region_id": ids, "centroid_lon": cx, "centroid_lat": cy})
result_df.to_csv("Data/Task3/region_centroids.csv", index=False)
```

Why this matters: numpy arrays are the natural input for scipy optimizers, distance
computations, and graph libraries. Keeping them numpy avoids silent type-coercion bugs
and keeps matrix operations readable and fast.

---

## Step 3 — Object-oriented design

Design classes around physical network components, not programming abstractions.
A reviewer should be able to read the class and immediately picture the real-world object.

**Recommended classes by task:**

| Task | Classes |
|------|---------|
| 3 | `Region` (counties, centroid, total_demand) |
| 4–5 | `Node` (fac_id, coords, area_sqft, demand), `Link` (origin, dest, travel_time_h, flow) |
| 5–7 | `NetworkManager` (nodes, links, add_node, shortest_path, coverage_check) |
| 6 | `Area` (counties, gateway_node) |
| 8 | `FlowAssignment` (od_matrix, paths, assigned_volumes) |

Keep attributes domain-meaningful. Prefer `node.demand_ton` over `node.d`.
Avoid deep inheritance chains — a flat structure with clear attributes is more readable
than a clever hierarchy.

---

## Step 4 — Pipeline state management

Any computation that takes more than a few seconds to run must be serialized immediately
after it completes. This prevents re-running expensive steps on every kernel restart.

**Save pattern:**
```python
from pathlib import Path
import numpy as np
import joblib

CACHE_DIR = Path("Data/Task3")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

dist_path = CACHE_DIR / "distance_matrix.npy"
if dist_path.exists():
    dist_matrix = np.load(dist_path)
else:
    dist_matrix = compute_distance_matrix(coords)   # expensive
    np.save(dist_path, dist_matrix)
```

**Format guide:**
- Raw numpy arrays → `.npy` via `np.save` / `np.load`
- Class instances, solver states, fitted models → `.pkl` via `joblib.dump` / `joblib.load`
- Final results for human review → `.csv` or `.parquet` via pandas

This also doubles as a checkpoint system: if the kernel dies mid-run, you pick up from
the last saved state, not from scratch.

---

## Step 5 — Sanity checks

Define your expected bounds *before* running the computation, drawing from Task.md.
A sanity check is not just an assert — it should print what it found so you can see
the actual values at a glance.

```python
# Example: region clustering (Task 3)
assert len(regions) == expected_n_regions, \
    f"Expected ~50 regions, got {len(regions)}"
assert all(r.total_demand > 0 for r in regions), \
    "One or more regions have zero or negative demand — check county filter"

# Travel time constraint
max_travel_h = max(link.travel_time_h for link in network.links)
assert max_travel_h <= 5.5, \
    f"Regional hub travel time {max_travel_h:.2f}h exceeds 5.5h constraint"

print(f"✓ {len(regions)} regions | demand range: "
      f"[{min(r.total_demand for r in regions):,.0f}, "
      f"{max(r.total_demand for r in regions):,.0f}] tons")
```

Use the kernel interpreter: `~/.venvs/general/bin/python3`

---

## Step 6 — Milestone gate: commit or rollback

At the end of each logical subtask (after sanity checks pass), stop and present a summary.

**On success** — present to user:
```
Subtask complete: [description]
Outputs saved: [list of files]
Sanity checks passed: [key metrics]

Proceed with commit? (y/n)
```

Wait for explicit `y` before committing. Then:
```bash
./git_tools.sh sync "Task N — [subtask description]"
```

**On sanity check failure** — do NOT try to patch it forward:

1. Run the rollback:
```bash
git reset --hard HEAD
```

2. Write `Issue_Report.md` in the project root:
```yaml
Issue: Task N — [subtask name]
Timestamp: [ISO 8601 datetime]
Failure Point: [Notebook cell / function name]
Expected Bound: [Constraint from Task.md, e.g., "all flows >= 0"]
Actual Output: [What the code produced, e.g., "min flow = -320 tons"]
Action Taken: Rolled back to last stable commit. Awaiting human review.
```

3. Stop and report to the user. Do not attempt the same computation again without
   understanding the root cause.

Why a hard stop? Network optimization can silently produce infeasible solutions —
negative flows, disconnected components, violated capacity. Catching these early,
before they propagate downstream, is far cheaper than debugging a corrupted pipeline
three tasks later.

---

## Quick reference

```python
# Interpreter
~/.venvs/general/bin/python3

# Data paths
Data/Task1/raw.parquet          # O-D matrix
Data/Task2/*.csv                # Interface nodes
Data/Task<N>/                   # Task N outputs

# Serialization
np.save("path.npy", arr)        # arrays
joblib.dump(obj, "path.pkl")    # objects
df.to_csv("path.csv")           # summaries

# Version control
./git_tools.sh sync "Task N — step description"
./git_tools.sh status
```

---

## Cell order template

Use this as a scaffold for any new notebook section:

```
[Markdown] ## N.M — Subtask title
           Theory: objective, governing equation (LaTeX)

[Code]     # Load or fetch from cache
           Load inputs via pandas → convert to numpy at boundary

[Code]     # Core computation
           numpy / scipy / networkx operations

[Code]     # Serialize result
           np.save(...) or joblib.dump(...)

[Code]     # Sanity checks
           assert bounds, print summary stats

[Markdown] ## Milestone — N.M complete
           Summary of outputs, key metrics

[Code]     # Convert to pandas → save CSV/parquet output
           result_df.to_csv(...)
```
