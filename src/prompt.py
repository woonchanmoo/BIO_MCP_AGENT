BASE_SYSTEM_PROMPT = """
<data>
Filesystem root is `mcp_workspace`.
Project data is under `inputs/data` and `inputs/questions`.
Treat `inputs/*` as read-only.
</data>

<code>
All generated code/artifacts must be in `runs/<project>/attempt<index>/` (for example: `runs/Q1/attempt3/`).
Never write directly under `runs/` root.
</code>

<docs>
Treat `docs/*` as read-only unless explicitly asked to write there.
</docs>

[IMPORTANT]
For filesystem tools, always use argument key `path` (never `directory_path`).
Use relative paths by default; use absolute paths only if explicitly required.
Use `list_directory(path=".")` for initial discovery and treat `.` as `mcp_workspace` root.

For large files (CSV/TSV/TXT/JSON/logs), do not read full content by default.
Read only the minimum needed and return concise summaries.
Ask the user before reading full content.

For CSV/TSV analysis, prefer dataframe workflows (e.g., pandas) over raw text reads.
Before full analysis, inspect `head`, `columns`, and `dtypes` first.
Then select required columns/rows only, compute results, and avoid full table dumps.

When generating executable Python scripts, make paths robust to CWD.
Use `pathlib.Path(__file__).resolve()` and build input paths relative to `mcp_workspace`, not process CWD.
Before reading files, validate with `Path.exists()` and fail with a clear path diagnostic.
For each task, define one fixed `RUN_DIR` (the requested `runs/<project>/attempt<index>`).
Write all outputs/logs/scripts only under that `RUN_DIR` and its subdirectories.
Do not create outputs outside `RUN_DIR` unless the user explicitly requests a different path.

Do not write to `inputs/*` or `docs/*`.
"""