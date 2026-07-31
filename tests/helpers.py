"""Small helpers for building unified diffs in tests."""


def one_file_diff(path: str, added_lines: list[str]) -> str:
    """A diff that adds `added_lines` to a new file, numbered from line 1."""
    n = len(added_lines)
    header = (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -0,0 +1,{n} @@\n"
    )
    body = "".join(f"+{ln}\n" for ln in added_lines)
    return header + body
