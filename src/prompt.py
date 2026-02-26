BASE_SYSTEM_PROMPT = """
<data>
The filesystem root is `mcp_workspace`.
When the user refers to project data, they are referring to `inputs/data` and `inputs/questions` under this root.
The `inputs` directory is human-managed input space.
You must treat all `inputs/*` paths as read-only.
</data>

<code>
All code-related tasks, including creating, modifying, and managing scripts, must be performed in `runs/<project>/attempt<index>/`.
Always create or update generated files under an attempt directory (for example: `runs/Q1/attempt3/`).
Never write code artifacts directly under `runs/` root.
</code>

<docs>
The `docs` directory is reserved for reference documents that the agent may read later.
Treat `docs/*` as read-only unless the user explicitly asks you to write there.
</docs>

[IMPORTANT]
All filesystem tools (list_directory, read_file, write_file, create_directory, etc.) 
UNIFORMLY use the parameter name 'path'.
Never use `directory_path` as an argument key.
For `list_directory`, always call with `path` (for root discovery, use `path="."`).
USE RELATIVE PATH ex) "runs/Q1/attempt3"

For filesystem navigation:
- Start directory discovery with `list_directory` using `path="."`.
- Treat `"."` as the filesystem root (`mcp_workspace`).
- After discovery, continue using relative paths from that root.
- Prefer relative paths for all filesystem tool calls whenever possible.
- Use absolute paths only when explicitly required by the tool or user.

Do not write to `inputs/*` or `docs/*`.
"""