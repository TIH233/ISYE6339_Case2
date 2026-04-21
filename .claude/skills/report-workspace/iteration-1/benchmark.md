# Iteration 1 Benchmark Summary

## Eval Status

| Eval | With Skill | Baseline |
|------|-----------|---------|
| eval-0 Task 2 interface nodes | ❌ File not saved (permission prompt) | ❌ Stub only |
| eval-1 Task 5 hub MIP | ❌ File not saved (permission prompt) | ✅ Full content |
| eval-2 Task 3 clustering | ✅ Full content | ❌ Stub only |

**Root cause**: Background subagents run in their own restricted permission context and require user approval for Write/Bash. Both with-skill agents described their full output in natural language but could not save the file.

## Grading Results (available files)

### eval-2 WITH SKILL — task3.tex

| Assertion | Result | Detail |
|-----------|--------|--------|
| no_first_person | ✅ PASS | 0 real matches (false positives from math `i,j` and I-95 highway names — assertion regex refined) |
| has_section_header | ✅ PASS | 1 `\section{}` |
| has_subsections | ✅ PASS | 3 `\subsection{}` + 9 `\subsubsection{}` |
| has_math_environment | ✅ PASS | 5 equation/align environments |
| no_preamble | ✅ PASS | No `\documentclass` |
| no_intro_section | ✅ PASS | |
| has_sa_formulation | ✅ PASS | 4 SA mentions + full 3-term objective in align |
| covers_both_subtasks | ✅ PASS | Demand surface (3.1) + SA clustering (3.2) both present |
| mentions_region_count | ✅ PASS | 4 occurrences of "50" |

**Score: 9/9 assertions passed**

### eval-1 BASELINE — task5.tex (no skill)

| Assertion | Result | Detail |
|-----------|--------|--------|
| no_first_person | ✅ PASS | 0 matches |
| has_section_header | ✅ PASS | 1 `\section{}` |
| has_subsections | ✅ PASS | 4 `\subsection{}` |
| has_math_environment | ✅ PASS | 4 environments |
| no_preamble | ✅ PASS | |
| has_mip_formulation | ✅ PASS | `\min` present |
| has_constraints | ✅ PASS | `\text{s.t.}` present |

**Score: 7/7 assertions passed**

## Analyst Observations

**1. Baseline priming effect**: eval-1 prompt explicitly said "include the formulation" — this primed the baseline to produce structured math. A fairer baseline test would use a generic "write the report" prompt. The with-skill prompt did NOT say this; the skill alone induced the formulation.

**2. Subsubsection granularity**: The with-skill eval-2 output used 9 `\subsubsection{}` entries under 3 `\subsection{}`. This is more granular than the skill specifies (2–4 subsections). However, Task 3 has many distinct sub-components, and the output reads coherently. May be acceptable — worth user judgment.

**3. Assertion false positives**: The `no_first_person` regex `\bI\b` matches math index variables and highway names (I-95). The refined check (exclude `I-\d+` patterns) clears this correctly.

**4. Content quality (with-skill eval-2)**: The Task 3 output is notably strong — the SA objective $J$ is written as a 3-term weighted sum with each term fully defined, the demand metric distinction (activity vs. external throughput) is explained with clear rationale, and the post-assignment demand correction is flagged as a key design choice. This matches the skill's intent to narrate logic, not just list steps.

**5. With-skill timing**: With-skill agents consistently used fewer tokens (77–79k) vs. the baseline (81k) while producing richer content, suggesting the structured workflow reduced exploratory tool calls.

## Assertion Fix Needed

The `no_first_person` check should be:
```bash
grep -nE '\bI\b|\bWe\b|\bOur\b' file | grep -vE 'I-[0-9]|\$' | grep -v '^%'
```
(Exclude highway names `I-\d+` and lines containing inline math `$`)
