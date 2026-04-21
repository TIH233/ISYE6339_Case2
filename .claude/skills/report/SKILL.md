---
name: report
description: Write a LaTeX report (.tex) for a specific task in this network design project. Trigger this skill whenever the user asks to write, draft, generate, or produce a report for any task (e.g., "write report for Task 5", "draft the latex for Task 3", "generate the report", "write up Task 8"). Also trigger when the user says things like "can you write up what we did" or "turn this into a report section". This skill is the go-to for all report writing in this project — use it even if the user just says "report" without specifying format.
---

# Report Writing Skill

This skill produces a polished LaTeX report section for one or more tasks in the NE megaregion freight network project. The output is a `.tex` file saved to `Report/task{N}.tex` (e.g., `Report/task5.tex`).

## Step 1 — Gather Context

Do steps 1a–1c in parallel, then do 1d sequentially (it depends on what 1a–1c reveal).

**1a. Read `Doc/Task.md`** — Find the relevant task entry. Extract:
- What the task is trying to accomplish and why
- The key methodological decisions made
- Any formulations, models, or algorithms used
- The outputs produced and what they represent

**1b. Read the Handout** — Use the `pdf` skill to read `Handout.pdf`. Look for the section(s) describing the task being reported. The handout is intentionally high-level — use it only to:
- Understand what the deliverable is asking for
- Identify what the grader/reader expects to see
- Frame the skeleton of sections to cover

Do not let the handout constrain the depth or substance of the writing — the actual implementation goes well beyond it.

**1c. Read `Doc/Data.md`** — Skim for entries relevant to the task's outputs. This tells you what result files exist, their schema, and what each column means. Use it to know *where* to look in step 1d.

**1d. Retrieve live statistics from result files** — This is essential. Do not write made-up or approximated numbers. For each key output file identified in 1c, retrieve the actual statistics that will appear in the report:

- For small CSVs: read them directly with the Read tool (or `head` via Bash) to get row counts and representative values.
- For larger CSVs/parquets, or when you need computed summaries (mean, min, max, top-N, distribution): write and run a short Python snippet using `conda run -n General_env python -c "..."` or a temp script. Examples of useful retrievals:
  - Hub count, state breakdown, capacity range → `selected_hubs.csv`
  - Region demand stats (CV, min/max T_r) → `region_metrics.csv`
  - Gateway counts per region → `gateway_selected.csv`
  - Flow totals, link count, mean distance → `hub_link_flows.csv` or `task5_hub_network_links_flow_weighted.csv`
  - Throughput summaries → `hub_throughput.csv`, `gateway_throughput.csv`

If a statistic you need is not directly available in a column (e.g., "fraction of hubs within X miles of an interstate", or "number of regions with dual-hub assignments"), write a short EDA snippet to compute it from the raw file. The Python environment has pandas, geopandas, numpy available.

**What to retrieve for common report sections:**

| Section type | What to retrieve | Where |
|---|---|---|
| Candidate screening | Pool sizes before/after filters, threshold values | Task.md + run script on CSV |
| Optimization results | Objective value, solve time, gap %, decision variable counts | Task.md (or notebook output) |
| Hub/gateway selection | Count, state distribution, capacity range, any dual-assignments | `selected_hubs.csv`, `gateway_selected.csv` |
| Clustering | Objective J*, CV of demand, connectivity check | `region_metrics.csv` |
| Network links | Link count, mean/min/max distance, flow intensity range | `*_links*.csv` |
| Flow analysis | Total flow, top corridors, hub throughput range | `hub_throughput.csv`, `area_flow_matrix.parquet` |

Record all retrieved numbers in a scratch note before writing — they will populate tables and inline citations in the report.

## Step 2 — Plan the Structure

Before writing LaTeX, sketch the section plan mentally:

- One `\section{}` per task (e.g., `\section{Task 5 — Regional Hub Selection}`)
- `\subsection{}` for logical groupings of subtasks — condense where subtasks are closely related. The goal is 2–4 subsections per task, not one per subtask.
- No `\section{Introduction}`, no `\section{Executive Summary}`, no `\section{Conclusion}` unless specifically requested.

Think of the subsection groupings as narrative acts: what problem was being solved, how it was formulated, what the results look like.

## Step 3 — Write the Report

### What to include

**Logic and decisions**: Explain *why* each methodological choice was made, not just what was done. For instance, if a simulated annealing approach was chosen, explain what property of the problem made it suitable. If a particular threshold was set, explain the reasoning.

**Key formulations**: Include the math. If the task involved an optimization model, write out the objective and constraints in a proper `equation` or `align` environment. If a scoring or weighting formula was used, show it. Formulations are the backbone of a technical report.

**Results with tables**: Present key outputs in LaTeX tables when there are 4+ comparable values (e.g., node counts by tier, hub counts by state, flow statistics by tier). Use inline numbers for 1–3 values. Tables must use actual retrieved numbers from step 1d — never approximate or fabricate figures.

Good candidates for tables:
- Multi-tier node summaries (global/continental/national counts and throughput)
- Hub distribution by state
- Region demand statistics (min, mean, max, CV)
- Network link summary statistics
- Solver performance (obj, gap, time, variable counts)

**Reflections**: Each section should end with or include a brief reflection — what the results imply, any tradeoffs or limitations, or how this stage sets up downstream work.

### What to leave out

- Step-by-step description of code or data pipeline (avoid "first we loaded X, then we joined Y")
- Exhaustive listing of data preprocessing steps
- Implementation details that are obvious from context
- Repetition of what the handout says verbatim

### Tone and voice

Write in third-person or passive voice. Avoid "I", "we", "our team". Instead:
- "The formulation assigns each county to exactly one region..."
- "Hub candidates are screened by..."
- "The MIP objective minimizes..."

Keep the language direct and confident. Avoid hedging language like "we attempted to" or "we tried to implement". The work was done; write it as such.

The tone should feel like a well-written conference paper section — technically precise but readable. Not a bullet-point summary, not a textbook derivation.

### LaTeX conventions

- Use `\begin{equation}` for single numbered equations, `\begin{align}` for multi-line
- Use `\text{}` inside math for subscript labels (e.g., `T_{\text{region}}`)
- Do not include `\documentclass`, `\begin{document}`, or preamble — this is a section to be `\input{}` into a master document
- Do not include a `\bibliography` block unless asked

**Table format** — use `booktabs` style (cleaner than default LaTeX lines):
```latex
\begin{table}[h]
\centering
\caption{Caption describing what the table shows.}
\begin{tabular}{lrr}
\toprule
Column A & Column B & Column C \\
\midrule
Value    & 123      & 45.6     \\
Value    & 789      & 12.3     \\
\bottomrule
\end{tabular}
\label{tab:label}
\end{table}
```
Use `l` for text columns, `r` for numbers, `c` sparingly. Keep tables focused — 3–6 columns maximum. Every table must be referenced in the prose (`Table~\ref{tab:label}`).

### Figures

Figures are a first-class element of the report — use them to show maps, network diagrams, convergence plots, and spatial distributions that would take paragraphs to describe in prose.

**Step A — Identify available figures.**
List the figures directory for the task: `Data/Task{N}/figures/`. Each task produces specific figure types:

| Task | Typical figures |
|------|----------------|
| Task 3 | Freight demand choropleth, region cluster map, SA convergence plot |
| Task 4 | Candidate facility maps (HTML — not embeddable; skip or screenshot) |
| Task 5 | Hub location map, flow-weighted network map |
| Task 6 | Area cluster map, gateway location map |
| Task 7 | Full multi-tier network map |
| Task 8 | Hub throughput bar charts, flow heatmaps, corridor analysis plots |

Run `ls Data/Task{N}/figures/` to see exact filenames. Prefer PNG or PDF formats; skip HTML files (not LaTeX-embeddable).

**Step B — Copy selected figures to `Report/figures/`.**
Create a `Report/figures/` directory if needed, then copy the figures you will use:
```bash
mkdir -p Report/figures
cp Data/Task{N}/figures/fig_name.png Report/figures/taskN_fig_name.png
```
Use a `taskN_` prefix in the destination filename to avoid name collisions across tasks.

**Step C — Insert figures in the right place.**
Place each figure immediately after the paragraph that introduces or discusses it — not grouped at the end. Use this template:

```latex
\begin{figure}[h]
  \centering
  \includegraphics[width=0.85\textwidth]{figures/taskN_fig_name.png}
  \caption{One or two sentences describing what the figure shows and what the reader should notice. Point out the key spatial pattern, cluster, or result visible in the image.}
  \label{fig:taskN-descriptive-name}
\end{figure}
```

The path in `\includegraphics` should be relative to the `Report/` directory (where the `.tex` file lives), so `figures/taskN_fig_name.png` is correct — not the full `Data/...` path.

**Caption writing** — the part that appears under the figure — should:
- Start with a noun phrase describing the subject (e.g., "Selected regional hub locations across the 14-state Northeast megaregion.")
- Add one sentence pointing out the key thing to notice ("Hub density is highest along the I-95 corridor; the two dual-assigned hubs appear in the Mid-Atlantic cluster.")
- Do not caption with vague text like "Figure showing results."

**Cross-referencing** — every figure must be cited in the prose before it appears:
```latex
Figure~\ref{fig:taskN-descriptive-name} shows the final hub network overlaid on...
```

**Step D — Width guidance.**
- Full-width maps / network diagrams: `width=0.85\textwidth`
- Two figures side-by-side: use `minipage` at `0.48\textwidth` each
- Convergence/line plots: `width=0.65\textwidth` (they don't need full width)

## Step 4 — Save the Output

1. Create `Report/` and `Report/figures/` if they don't exist
2. Copy selected figures to `Report/figures/taskN_*.png` (Step B above)
3. Save the `.tex` file to `Report/task{N}.tex`
4. If writing multiple tasks, save separate files and note all paths

## Quality check before finishing

Read the draft once with fresh eyes and ask:
- Does each subsection tell a coherent story, or is it just a list of facts?
- Are the formulations correct and clearly labeled?
- Are all numbers in the report real (retrieved from actual files), not approximated?
- Does every table have a `\ref{}` in the prose and a `\label{}`?
- Does every figure have a descriptive `\caption{}`, a `\label{}`, and a `\ref{}` in the prose before it?
- Are all `\includegraphics` paths relative to `Report/` (not absolute paths to `Data/`)?
- Is any sentence starting with "I" or "We" (excluding highway names like I-95)?
- Is there any sentence that reads like a code comment ("Next, we load the file...")?

Fix any issues found before presenting to the user.
