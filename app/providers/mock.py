"""The deterministic `mock` provider — the scored path. It implements the rule
table exactly: rules fire on ADDED lines only, one finding per matching line per
rule, `line` is the new-file line number. Injection strings are matched as inert
data (MOCK-INJ) and can never change how any other rule behaves — this module
does pure pattern matching with no interpretation of the content."""
from __future__ import annotations

import re

from ..diff_parser import AddedLine, FileDiff
from ..models import Finding

# --- Single-line rule patterns -------------------------------------------------

CRED_RE = re.compile(
    r"(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
    re.IGNORECASE,
)
SQL_KEYWORDS = ("SELECT", "INSERT", "UPDATE", "DELETE")
# A quoted string literal that contains a SQL keyword.
SQL_STRING_RE = re.compile(
    r"['\"][^'\"]*\b(?:SELECT|INSERT|UPDATE|DELETE)\b[^'\"]*['\"]",
    re.IGNORECASE,
)
NULL_CMP_RE = re.compile(r"[!=]=\s*null")
DEEP_CLONE = "JSON.parse(JSON.stringify("
INJECTION_PHRASES = (
    "ignore previous instructions",
    "disregard all prior",
    "you are now",
)

# Multi-line: catch(...) { ... } with an empty body.
CATCH_RE = re.compile(r"catch\s*(?:\([^)]*\))?\s*\{")


def _make(rule_id: str, severity: str, category: str, title: str,
          path: str, line: int, evidence: str) -> Finding:
    return Finding(
        ruleId=rule_id, severity=severity, category=category, title=title,
        path=path, line=line, evidence=evidence,
    )


def _scan_line(path: str, al: AddedLine) -> list[Finding]:
    """All single-line rules for one added line."""
    out: list[Finding] = []
    text = al.text
    ev = text                                   # evidence = the added line, verbatim

    if "eval(" in text:
        out.append(_make("MOCK-001", "critical", "security", "eval usage", path, al.line, ev))
    if CRED_RE.search(text):
        out.append(_make("MOCK-002", "critical", "security", "hardcoded credential", path, al.line, ev))
    if "+" in text and SQL_STRING_RE.search(text):
        out.append(_make("MOCK-003", "high", "security", "SQL string concatenation", path, al.line, ev))
    if NULL_CMP_RE.search(text):
        out.append(_make("MOCK-005", "medium", "correctness", "loose null comparison", path, al.line, ev))
    if DEEP_CLONE in text:
        out.append(_make("MOCK-006", "medium", "performance", "deep-clone via JSON", path, al.line, ev))
    if "console.log(" in text:
        out.append(_make("MOCK-007", "low", "style", "console.log left in", path, al.line, ev))
    if "TODO" in text or "FIXME" in text:
        out.append(_make("MOCK-008", "low", "style", "unresolved marker", path, al.line, ev))

    low = text.lower()
    if any(p in low for p in INJECTION_PHRASES):
        out.append(_make("MOCK-INJ", "critical", "security", "prompt-injection content", path, al.line, ev))
    return out


def _scan_empty_catch(path: str, added: list[AddedLine]) -> list[Finding]:
    """MOCK-004: empty catch block, possibly spanning lines. Reported on the
    `catch` line. We join the file's added lines (tracking which line each char
    belongs to) and look for `catch (...) {` whose body up to the next `}` is
    only whitespace."""
    if not added:
        return []
    # Build joined text + a char->line map.
    parts: list[str] = []
    char_line: list[int] = []
    for al in added:
        for ch in al.text:
            char_line.append(al.line)
        parts.append(al.text)
        char_line.append(al.line)               # for the '\n' we insert
    joined = "\n".join(parts)

    out: list[Finding] = []
    seen_lines: set[int] = set()
    for m in CATCH_RE.finditer(joined):
        brace = m.end() - 1                      # index of the '{'
        close = joined.find("}", brace + 1)
        if close == -1:
            continue
        body = joined[brace + 1:close]
        if body.strip() == "":
            catch_line = char_line[m.start()] if m.start() < len(char_line) else added[0].line
            if catch_line in seen_lines:
                continue
            seen_lines.add(catch_line)
            evidence = next((al.text for al in added if al.line == catch_line), joined[m.start():close + 1])
            out.append(_make("MOCK-004", "high", "correctness", "swallowed exception",
                             path, catch_line, evidence))
    return out


class MockProvider:
    name = "mock"

    async def review_chunk(self, files: list[FileDiff]) -> list[Finding]:
        findings: list[Finding] = []
        for fd in files:
            for al in fd.added:
                findings.extend(_scan_line(fd.path, al))
            findings.extend(_scan_empty_catch(fd.path, fd.added))
        return findings
