"""Unified-diff parser.

Splits a diff into per-file sections (the unit chunking works on) and, for each
file, extracts the *added* lines with their line number in the NEW file. Rules
run on added lines only, so this is the single source of truth for "what changed"
and "at what line".

Supports both `git diff` output (with `diff --git` headers) and plain `diff -u`
output (just `---`/`+++`/`@@`). Raises InvalidDiff when the text is not a parseable
unified diff so the route can map it to 422."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class InvalidDiff(Exception):
    pass


@dataclass
class AddedLine:
    line: int          # line number in the new file
    text: str          # content WITHOUT the leading '+'


@dataclass
class FileDiff:
    path: str
    raw: str                                   # exact diff text for this file
    added: list[AddedLine] = field(default_factory=list)

    @property
    def byte_size(self) -> int:
        return len(self.raw.encode("utf-8"))


def _looks_like_diff(text: str) -> bool:
    return any(
        line.startswith(("diff --git ", "--- ", "+++ ", "@@"))
        for line in text.splitlines()
    )


def _file_start_indices(lines: list[str]) -> list[int]:
    """Indices where each file's section begins."""
    git_starts = [i for i, ln in enumerate(lines) if ln.startswith("diff --git ")]
    if git_starts:
        return git_starts
    # Plain unified diff: a file begins at each '--- ' header line.
    return [i for i, ln in enumerate(lines) if ln.startswith("--- ")]


def _extract_path(section_lines: list[str]) -> str:
    """Prefer the new-file path from '+++ b/path'; fall back to 'diff --git'."""
    for ln in section_lines:
        if ln.startswith("+++ "):
            p = ln[4:].strip()
            if p == "/dev/null":
                continue
            # strip a leading a/ or b/ (git convention) and optional tab-suffix
            p = p.split("\t", 1)[0]
            if p.startswith(("a/", "b/")):
                p = p[2:]
            return p
    for ln in section_lines:
        if ln.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)", ln)
            if m:
                return m.group(2).strip()
    return "unknown"


def _extract_added(section_lines: list[str]) -> list[AddedLine]:
    added: list[AddedLine] = []
    new_line = 0
    in_hunk = False
    for ln in section_lines:
        m = HUNK_RE.match(ln)
        if m:
            new_line = int(m.group(1))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if ln.startswith("+++"):          # header, not an added line
            continue
        if ln.startswith("+"):
            added.append(AddedLine(line=new_line, text=ln[1:]))
            new_line += 1
        elif ln.startswith("-") and not ln.startswith("---"):
            pass                          # removed line: no new-file number
        elif ln.startswith("---"):
            continue
        elif ln.startswith("\\"):         # "\ No newline at end of file"
            continue
        else:                             # context line (starts with ' ' or empty)
            new_line += 1
    return added


def parse_diff(diff: str) -> list[FileDiff]:
    if not diff or not diff.strip():
        raise InvalidDiff("Diff is empty.")
    if not _looks_like_diff(diff):
        raise InvalidDiff("Payload is not a unified diff.")

    lines = diff.split("\n")
    starts = _file_start_indices(lines)
    if not starts:
        raise InvalidDiff("No file sections found in diff.")

    bounds = starts + [len(lines)]
    files: list[FileDiff] = []
    for i in range(len(starts)):
        section = lines[bounds[i]:bounds[i + 1]]
        raw = "\n".join(section)
        fd = FileDiff(
            path=_extract_path(section),
            raw=raw,
            added=_extract_added(section),
        )
        files.append(fd)

    if not any(HUNK_RE.match(ln) for ln in lines):
        raise InvalidDiff("Diff contains no hunks.")
    return files
