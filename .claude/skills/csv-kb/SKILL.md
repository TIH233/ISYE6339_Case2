---
name: csv-kb
description: Smart CSV/Parquet loader and knowledge-base archiver for project data files. Use this skill whenever a .csv or .parquet file is mentioned, needs to be read, explored, or saved for future reference. Trigger on phrases like "archive this CSV", "kb this parquet", "add to knowledge base", "index this data", "load this file", "what's in this file", or when the user points to any .csv or .parquet path. Also handles .xlsx/.xls by rerouting to the xlsx skill. Always profile the file with Python first — never read raw rows into context for large files.
---

## Purpose

Two jobs, one lightweight workflow:
1. **Smart-load** — profile a CSV or Parquet file efficiently so the current session can use it without flooding context
2. **Archive** — write a compact, LLM-readable entry to `Doc/Data.md` for future conversations

---

## Step 0: File-type check

- `.xlsx` / `.xls` → redirect to xlsx skill, stop here.
- `.parquet` → use the **Parquet profile block** in Step 1.
- `.csv` → use the **CSV profile block** in Step 1.
- **2+ files in one request** → jump straight to [Batch mode](#batch-mode).

---

## Step 1: Profile the file

### CSV

```bash
~/.venvs/general/bin/python3 - <<'EOF'
import pandas as pd
path = "REPLACE_WITH_FILE_PATH"
total_rows = sum(1 for _ in open(path)) - 1
df = pd.read_csv(path, nrows=1000)
print(f"Rows: {total_rows} | Cols: {df.shape[1]}")
for c in df.columns:
    nn = df[c].notna().mean()
    if df[c].dtype.kind in 'iuf':
        print(f"  {c} [{df[c].dtype}] {nn:.0%} non-null | [{df[c].min():.4g}, {df[c].max():.4g}]")
    else:
        top = df[c].dropna().astype(str).value_counts().head(3).index.tolist()
        print(f"  {c} [{df[c].dtype}] {nn:.0%} non-null | e.g. {top}")
EOF
```

### Parquet

```bash
~/.venvs/general/bin/python3 - <<'EOF'
import pyarrow.parquet as pq
path = "REPLACE_WITH_FILE_PATH"
pf = pq.ParquetFile(path)
total_rows = pf.metadata.num_rows
print(f"Rows: {total_rows} | Cols: {len(pf.schema_arrow)}")
batch = next(pf.iter_batches(batch_size=1000))
df = batch.to_pandas()
for c in df.columns:
    nn = df[c].notna().mean()
    if df[c].dtype.kind in 'iuf':
        print(f"  {c} [{df[c].dtype}] {nn:.0%} non-null | [{df[c].min():.4g}, {df[c].max():.4g}]")
    else:
        top = df[c].dropna().astype(str).value_counts().head(3).index.tolist()
        print(f"  {c} [{df[c].dtype}] {nn:.0%} non-null | e.g. {top}")
EOF
```

`pf.metadata.num_rows` reads only the Parquet footer (no data scan), so this is fast even on large files. `iter_batches(batch_size=1000)` loads just the first 1 000 rows for column stats.

**Fallback (no Bash)**: use the `Read` tool for CSV (inspect headers + sample values from first lines). For Parquet, note it's binary — ask the user to provide a schema or run a quick notebook cell.

---

## Step 2: Size decision

- **CSV < 50 rows** → show the full dataframe with `pd.read_csv(path).to_string()`. Archive only if asked.
- **CSV ≥ 50 rows or any Parquet** → only the Step 1 schema output enters context. Proceed to Step 3.

---

## Step 3: Context mapping (≥ 50 rows / Parquet)

Work through these in order — stop when a column is resolved:

1. **Conversation context** — has the user described the file?
2. **Column name itself** — many are self-explanatory (`county_name`, `tonnage_2025`)
3. **Spot checks** — `.head(3)` or `.value_counts()` on ambiguous columns
4. **Grep docs** — search `.claude/Doc/Paper.md` and `.claude/Doc/Task.md` for the column name (2-line context). These docs often define field names like `dms_orig`, `sctgG5` directly.
5. **Ask** — only if all above fail. Be specific: *"Column `dms_orig` — is this the FAF origin zone code? Couldn't find it in Paper.md or Task.md."*

---

## Step 4: Archive to knowledge base

Trigger words: "archive", "kb this", "add to knowledge base", "save for later", "index this".

Append to `.claude/Doc/Data.md`. Use the format below — the inline metadata line and explicit **Meaning** column are intentional: they make this entry easy for a future LLM to scan and reason about without re-reading the file.

```markdown
## `<filename.ext>` — <one-line description>

> **path** · `<relative/path/to/file>` · **format** · <csv|parquet> · **shape** · <N rows × M cols>

| Column | Type | Non-null | Meaning |
|--------|------|----------|---------|
| col_a  | int64 | 100%   | what this column represents |
| col_b  | str   | 98%    | e.g. "Fairfax, VA" — county label |

**Context**: 1–2 sentences on what this dataset is, how it was produced, and how it connects to the project tasks.
```

Rules:
- Cap column table at 15 rows (add `+ N more cols` note if needed)
- Total section ≤ 25 lines
- **Meaning** must be explicit for every row — no blanks, no vague "values"
- Infer the description from conversation; ask only if truly unclear

---

## Step 5: Confirm

After archiving:
> "Archived `<filename>` to `Doc/Data.md`. <N rows × M cols> — <one-line highlight>."

If the conversation is already long, skip all intermediate output and return only this line.

---

## Batch mode

When the user names **2+ files** in one request, do this to avoid interleaving verbose output per file:

1. **Profile all files silently** — run each profile block in sequence; print only `✓ <filename>: N rows × M cols` per file
2. **Map context once** — use conversation context and doc-grep across all files; ask one consolidated question if anything is still unclear (not file-by-file)
3. **Build all archive entries**, then write to `Doc/Data.md` in a single Edit (append all sections at once)
4. **Return one summary table**:

```
Archived N files to Doc/Data.md:
| File                  | Format  | Shape         |
|-----------------------|---------|---------------|
| ne_state_summary.csv  | csv     | 14 × 6        |
| raw.parquet           | parquet | 450 000 × 12  |
```

---

## Compact mode

If the user says **"compact and jump to result"**: run Steps 1–4 silently, return only the Step 5 line (or the batch summary table).
