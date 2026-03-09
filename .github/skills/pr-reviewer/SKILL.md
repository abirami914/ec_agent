---
name: pr-reviewer
description: "Reviews a GitHub Pull Request by summarising all changes and identifying potential bugs, security issues, and code-quality problems. Returns a structured Markdown report with severity-rated findings and suggested fixes."
argument-hint: "Paste a GitHub PR URL, e.g. https://github.com/owner/repo/pull/42"
user-invokable: true
---

# PR Reviewer Skill

## Purpose

This skill fetches a GitHub Pull Request, analyses its unified diff, and
produces a comprehensive review report. The report covers:

1. A plain-English **summary** of what changed and why.
2. A **bug and issue list** with severity ratings, exact locations, and
   suggested remediations.

---

## Instructions

When this skill is invoked, follow the steps below in order.

### Step 1 — Gather PR context

Fetch the following information from the GitHub API:

- **PR metadata**: title, description (`body`), base branch, head branch, author, creation date.
- **File list**: every file that was added, modified, renamed, or deleted,
  together with its `+additions` and `-deletions` counts.
- **Unified diff**: the raw patch for each changed file (via the
  `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` endpoint).

If the diff exceeds `max_diff_chars`, truncate from the bottom and append
`[diff truncated – showing first N characters]`. Never silently drop context.

---

### Step 2 — Summarise the changes

Produce a **Change Summary** section with:

- **PR Overview** (1–2 sentences): the intent of the PR based on the title
  and description.
- **Files Changed** table:

  | File | Status | +Lines | −Lines |
  |------|--------|--------|--------|
  | `path/to/file.py` | modified | 42 | 7 |

- **Key Changes** — a bullet list grouped by logical area (e.g.
  *Database layer*, *API endpoints*, *UI*, *Tests*). Each bullet should
  describe **what** changed and **why** it matters.

---

### Step 3 — Identify bugs and issues

Scan every changed hunk and flag items under the following categories.
For each finding use this structure:

```
### [SEVERITY] Short title

- **File**: `path/to/file.py` (line ~N)
- **Problem**: Describe the bug, regression, security flaw, or quality issue.
- **Suggested Fix**: Concrete code or approach to resolve it.
```

**Severity levels**

| Level | Criteria |
|-------|----------|
| 🔴 High | Data loss, security vulnerability (injection, auth bypass, secrets exposure), crash, or incorrect business logic affecting core functionality. |
| 🟡 Medium | Unhandled exceptions, missing input validation, race conditions, deprecated API usage, performance regressions. |
| 🟢 Low | Style inconsistencies, dead code, missing docstrings, suboptimal algorithms that don't affect correctness. |

**Checklist — things to look for**

- [ ] Null / None dereferences on values that could be absent.
- [ ] Missing error handling around I/O, network calls, and DB queries.
- [ ] SQL constructed via string concatenation (SQL injection risk).
- [ ] Secrets, API keys, or credentials hard-coded in source files.
- [ ] Off-by-one errors in loops, slices, or pagination logic.
- [ ] Mutated function arguments or shared mutable state.
- [ ] Logic that diverges between the happy path and error/edge cases.
- [ ] Breaking changes to public interfaces with no migration path.
- [ ] Tests that were removed or weakened alongside the functional change.
- [ ] Dependencies added without pinned versions.

---

### Step 4 — Overall assessment

End the report with a one-line verdict and rationale:

| Decision | When to use |
|----------|-------------|
| ✅ **Approve** | No High findings; Medium/Low items are minor or already acknowledged. |
| 🔁 **Request Changes** | One or more High findings, or multiple unresolved Medium findings. |
| 💬 **Needs Discussion** | Architectural changes, ambiguous requirements, or trade-offs that require human judgement. |

---

## Output Format

Return the full report as a single Markdown document with the following
top-level sections (in order):

```
# PR Review: <PR Title>

> <PR URL>  |  Base: `<base>` ← Head: `<head>`

## Change Summary
...

## Bugs & Issues
...

## Overall Assessment
...
```

If no bugs or issues are found, the **Bugs & Issues** section must still
appear and state: *"No issues identified in the analysed diff."*

---

## Examples

### Example invocation

```json
{
  "pr_url": "https://github.com/abirami914/credit-union-analytics-platform/pull/7",
  "max_diff_chars": 20000
}
```

### Example finding

```
### 🔴 Hard-coded Snowflake credentials

- **File**: `scripts/embed_data.py` (line ~95)
- **Problem**: The Snowflake password is embedded directly in source code and
  will be committed to version history. Any user with read access to the
  repository can extract it.
- **Suggested Fix**: Load credentials from environment variables or a secrets
  manager (e.g. `os.getenv("SNOWFLAKE_PASSWORD")`). Add the file to
  `.gitignore` if it must contain secrets locally.
```

---

## Notes

- When the diff is truncated, acknowledge it explicitly and note that findings
  are limited to the visible portion.
- Do not invent bugs that are not visible in the diff. If context is
  insufficient to be certain, phrase findings as *"Potential issue — verify
  that …"*.
- Always cite the file name and approximate line number for every finding.
- For PRs that touch SQL, also check for missing `WHERE` clauses on `UPDATE`/
  `DELETE` statements and unguarded schema changes.
