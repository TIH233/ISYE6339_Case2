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

The coder is an **executor**, not a planner. The plan lives in `Doc/Task.md` — written
by a planner upstream. The coder reads that plan, pulls the matching reference methodology,
and implements exactly what was specified.

---

## Bundled scripts

Two deterministic workflows are packaged as shell scripts in `scripts/` so they run
identically every time regardless of who (or what) invokes the coder.

| Script | Purpose | When to run |
|--------|---------|-------------|
| `scripts/preflight.sh` | Pull task status, reference methodology, and data schemas | **Before** writing any code (Step 0) |
| `scripts/gate.sh` | Commit or rollback at the end of a subtask | **After** sanity checks (Step 6) |

Both scripts live at `.claude/skills/coder/scripts/` and are self-documented via `--help`
or by reading the header comments.

---

## Step 0 — Preflight: retrieve task context

**Do not write a single line of code before completing this step.**

Run the preflight script from the project root. It invokes the retriever patterns
(the same `awk` extractions defined in the `retriever` skill) against all three
knowledge bases in one shot:

```bash
.claude/skills/coder/scripts/preflight.sh <TASK_NUMBER> [data_file1 data_file2 ...]
```

Example for Task 3, which depends on `raw.parquet`:
```bash
.claude/skills/coder/scripts/preflight.sh 3 raw.parquet
```

The script prints three blocks:

1. **Task Status & Plan** — the full task block from `Doc/Task.md`, including the
   status tag and any methodology already documented by the planner.
2. **Data Schemas** — column names, types, and context for every input file you listed.

### Status tags and their meaning

Tags come in two flavors — **top-level task** tags and **subtask** tags.

**Top-level task tags** (apply to `### Task N` headers):

| Tag | Meaning |
|-----|---------|
| `[not started]` | No plan or code yet. Nothing to build on. |
| `[in process]` | Currently active task — code is being written. |
| `[complete]` | Fully implemented, reviewed, and outputs committed. |

**Subtask tags** (apply to `#### Task N.M` and `##### Task N.M.P` headers):

| Tag | Meaning |
|-----|---------|
| `[planning]` | Step-by-step plan written in `Doc/Task.md`; no code yet. |
| `[editing]` | Plan exists and code is actively being written in the notebook. |
| `[complete]` | Subtask code written, sanity checks passed, outputs committed. |

### Decision after preflight

| Status tag | Action |
|------------|--------|
| `[not started]` | No plan exists. Do not implement — ask the planner to document the plan in `Doc/Task.md` first. |
| `[planning]` | Plan exists in `Doc/Task.md`. Read it fully, then proceed to Step 0.5. |
| `[editing]` | In-progress subtask. Open the notebook, read existing cells, then continue from where it stopped. |
| `[in process]` | Active top-level task. Check each subtask tag to find the next `[planning]` subtask. |
| `[complete]` | Nothing to do unless the user explicitly asks for changes. |

---

## Step 0.5 — Scope Lock

The user's message tells you **exactly** what to implement. Parse it literally.

1. **Read the plan** from `Doc/Task.md` for the targeted subtask. Use the retriever awk pattern:
   ```bash
   awk '/^##### .*QUERY/{flag=1; print; next} /^##/{if(flag) exit} flag' Doc/Task.md
   ```
   If the subtask tag is `[planning]`, the full step list is there — implement it exactly as written.
   If the subtask tag is `[editing]`, open the notebook and read existing cells before continuing.

2. **Extract scope** from the user's request — which task, which subtask(s), what specifically to build.
3. **Print a scope declaration** before writing any code:

```
SCOPE LOCK
──────────────────────────────────
Task:      Task 3 — Region Clustering
Subtasks:  K-means clustering + contiguity post-processing
Create:    Task3/task3_notebook.ipynb, Data/Task3/
Modify:    (none)
Will NOT touch: anything else
──────────────────────────────────
Confirm? (y/n)
```

3. Wait for explicit `y` before proceeding to Step 1.

**Rules:**
- If the request is ambiguous (e.g. "work on Task 5" when Task 5 has multiple parts),
  ask which part in conversation before printing the scope declaration.
- Never expand scope mid-implementation. No "while I'm here" additions.
- If you discover a prerequisite is missing during coding (e.g. Task 4 needs Task 3
  output that doesn't exist), stop and report — do not silently implement the prerequisite.

---

## Step1 Developer Suggestions: Architecture & Workflow

### subStep 1.1 — Task Tracking
When starting a new task, I suggest updating the subtask's status tag in `Doc/Task.md` from `[planning]` to `[editing]` directly in the header. This signals that implementation is active and helps prevent redundant work if multiple agents are involved.

### subStep 1.2 — Modular Design (The Calling Chain)
Rather than writing an entire monolithic script inside a single notebook, consider adopting a modular design. Treat the `.ipynb` files as the presentation and orchestration layer, while keeping the complex implementation logic in separate `.py` modules (e.g., inside a `lib/` or `src/` directory).

### subStep 1.3 — Notebook Orchestration
Each task can still live in its own notebook (`Task<N>/task<N>_notebook.ipynb`), but the notebook should primarily be used to import, execute, and validate the code.

Try to use this cell-level pattern throughout the notebook to bridge theory and code:

* `[Markdown cell]` ← Theory: LaTeX equations, mathematical constraints, variable definitions.
* `[Code cell]` ← Import & Execute: Import the relevant function from your `.py` module and call it.
* `[Code cell]` ← Sanity check: Assert bounds, check shapes, or print summary stats.

**Example Implementation:**
Write the governing equation in Markdown before executing the imported function:

```markdown
## 3.2 — Demand-weighted centroid
The cluster centroid $c_k$ is the tonnage-weighted mean of county centroids:
$$c_k = \frac{\sum_{i \in C_k} d_i \cdot \mathbf{x}_i}{\sum_{i \in C_k} d_i}$$
where $d_i$ is the 2025 truck tonnage for county $i$ and $\mathbf{x}_i = (\text{lon}_i, \text{lat}_i)$.
```
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
Use the gate script for the mechanical parts; keep the decision with the user.

### On success — present to user:

```
Subtask complete: [description]
Outputs saved: [list of files]
Sanity checks passed: [key metrics]

Proceed with commit? (y/n)
```

Wait for explicit `y` before committing. Then:
1. Update the subtask's status tag in `Doc/Task.md` from `[editing]` to `[complete]` (edit the header line directly).
2. If all subtasks under a top-level task are `[complete]`, update the top-level task tag to `[complete]` as well.
3. Run:
```bash
.claude/skills/coder/scripts/gate.sh commit "Task N — [subtask description]"
```

### On sanity check failure — do NOT try to patch it forward:

First inspect what changed:
```bash
.claude/skills/coder/scripts/gate.sh status
```

Then rollback:
```bash
.claude/skills/coder/scripts/gate.sh rollback
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
