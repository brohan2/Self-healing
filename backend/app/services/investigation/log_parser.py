"""
CI log parser.

Extracts structured signals from raw GitHub Actions log text:
- Error messages
- Stack traces
- Failing test names
- Failing commands (exit codes)
- File references

Security note: log text comes from external sources and is treated
as untrusted. The parser never executes any content from logs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------ #
# Regex patterns — ordered from most-specific to most-generic
# ------------------------------------------------------------------ #

# Python tracebacks
_PYTHON_TRACEBACK = re.compile(
    r"Traceback \(most recent call last\):.*?(?=\n\n|\Z)",
    re.DOTALL,
)
_PYTHON_ERROR_LINE = re.compile(
    r"^([\w.]+Error|[\w.]+Exception|[\w.]+Warning):\s*(.+)$",
    re.MULTILINE,
)

# Node.js / Jest errors
_NODE_ERROR = re.compile(
    r"(Error|TypeError|ReferenceError|SyntaxError|AssertionError):\s*(.+)",
)
_JEST_FAIL = re.compile(
    r"● (.+?) › (.+?)\n.*?expect\(",
    re.DOTALL,
)
_JEST_SUMMARY = re.compile(
    r"Tests:\s+(\d+) failed",
)

# Pytest
_PYTEST_FAIL = re.compile(
    r"FAILED\s+([\w/.\-]+\.py(?:::\w+)+)",
)
_PYTEST_ERROR = re.compile(
    r"(ERROR|FAILED)\s+([\w/.\-]+\.py)",
)
_PYTEST_SHORT_SUMMARY = re.compile(
    r"=+ short test summary info =+\n(.*?)(?==|\Z)",
    re.DOTALL,
)

# TypeScript / tsc
_TS_ERROR = re.compile(
    r"([\w/.\-]+\.tsx?)\((\d+),(\d+)\):\s+error\s+(TS\d+):\s+(.+)",
)

# ESLint
_ESLINT_ERROR = re.compile(
    r"([\w/.\-]+\.(?:js|ts|jsx|tsx))\s+\d+:\d+\s+error\s+(.+)",
)

# npm / pip install failures
_DEP_FAILURE = re.compile(
    r"(npm ERR!|pip.*ERROR|Could not install|ModuleNotFoundError|Cannot find module)\s*(.+)",
)

# Exit codes
_EXIT_CODE = re.compile(r"Process completed with exit code (\d+)")
_ERROR_EXIT = re.compile(r"##\[error\](.+)")

# File references in error output
_FILE_REF = re.compile(
    r"(?:File\s+[\"']?|at\s+[\w.<>]+\s+\(|in\s+)([\w/.\-]+\.(?:py|js|ts|jsx|tsx|java|go|rb|cs))"
)


@dataclass
class ParsedLog:
    """Structured output of log parsing."""

    raw_text: str = ""
    error_lines: list[str] = field(default_factory=list)
    stack_traces: list[str] = field(default_factory=list)
    failing_tests: list[str] = field(default_factory=list)
    referenced_files: list[str] = field(default_factory=list)
    exit_codes: list[int] = field(default_factory=list)
    error_annotations: list[str] = field(default_factory=list)
    has_dependency_error: bool = False
    has_type_error: bool = False
    has_lint_error: bool = False
    has_syntax_error: bool = False

    # A concise excerpt for the AI (bounded length)
    relevant_excerpt: str = ""


def parse_log(log_text: str, max_excerpt_chars: int = 8000) -> ParsedLog:
    """
    Parse raw CI log text into structured signals.

    :param log_text: raw log string from GitHub Actions
    :param max_excerpt_chars: maximum characters to include in the excerpt
    """
    result = ParsedLog(raw_text=log_text)

    # ------------------------------------------------------------------ #
    # 1. Exit codes
    # ------------------------------------------------------------------ #
    for m in _EXIT_CODE.finditer(log_text):
        code = int(m.group(1))
        if code != 0:
            result.exit_codes.append(code)

    # ------------------------------------------------------------------ #
    # 2. GitHub Actions error annotations
    # ------------------------------------------------------------------ #
    for m in _ERROR_EXIT.finditer(log_text):
        result.error_annotations.append(m.group(1).strip())

    # ------------------------------------------------------------------ #
    # 3. Python tracebacks
    # ------------------------------------------------------------------ #
    for m in _PYTHON_TRACEBACK.finditer(log_text):
        result.stack_traces.append(m.group(0)[:2000])

    for m in _PYTHON_ERROR_LINE.finditer(log_text):
        result.error_lines.append(f"{m.group(1)}: {m.group(2).strip()}")

    # ------------------------------------------------------------------ #
    # 4. pytest failures
    # ------------------------------------------------------------------ #
    for m in _PYTEST_FAIL.finditer(log_text):
        result.failing_tests.append(m.group(1))

    # ------------------------------------------------------------------ #
    # 5. TypeScript errors
    # ------------------------------------------------------------------ #
    ts_errors = _TS_ERROR.findall(log_text)
    if ts_errors:
        result.has_type_error = True
        for file, line, col, code, msg in ts_errors[:20]:
            result.error_lines.append(f"{file}:{line}:{col} {code}: {msg}")
            result.referenced_files.append(file)

    # ------------------------------------------------------------------ #
    # 6. ESLint
    # ------------------------------------------------------------------ #
    eslint_errors = _ESLINT_ERROR.findall(log_text)
    if eslint_errors:
        result.has_lint_error = True
        for file, msg in eslint_errors[:20]:
            result.error_lines.append(f"lint: {file}: {msg}")
            result.referenced_files.append(file)

    # ------------------------------------------------------------------ #
    # 7. Node / Jest
    # ------------------------------------------------------------------ #
    for m in _NODE_ERROR.finditer(log_text):
        result.error_lines.append(f"{m.group(1)}: {m.group(2)}")
        if m.group(1) == "SyntaxError":
            result.has_syntax_error = True

    # ------------------------------------------------------------------ #
    # 8. Dependency failures
    # ------------------------------------------------------------------ #
    if _DEP_FAILURE.search(log_text):
        result.has_dependency_error = True
        for m in _DEP_FAILURE.finditer(log_text):
            result.error_lines.append(f"dep: {m.group(1)} {m.group(2).strip()[:200]}")

    # ------------------------------------------------------------------ #
    # 9. File references
    # ------------------------------------------------------------------ #
    all_files = _FILE_REF.findall(log_text)
    seen: set[str] = set(result.referenced_files)
    for f in all_files:
        if f not in seen:
            result.referenced_files.append(f)
            seen.add(f)

    # ------------------------------------------------------------------ #
    # 10. Build a concise excerpt for the AI
    #     Prefer lines near errors rather than dumping the whole log
    # ------------------------------------------------------------------ #
    result.relevant_excerpt = _build_excerpt(log_text, result, max_excerpt_chars)

    # Deduplicate
    result.error_lines = list(dict.fromkeys(result.error_lines))[:50]
    result.failing_tests = list(dict.fromkeys(result.failing_tests))[:20]
    result.referenced_files = list(dict.fromkeys(result.referenced_files))[:20]

    return result


def _build_excerpt(
    text: str,
    result: ParsedLog,
    max_chars: int,
) -> str:
    """
    Extract the most relevant lines from the log.

    Strategy:
    1. Keep lines that contain error keywords
    2. Keep lines adjacent to those (±3 lines of context)
    3. Truncate to max_chars
    """
    lines = text.splitlines()
    total = len(lines)
    _ERROR_KEYWORDS = re.compile(
        r"error|Error|ERROR|failed|FAILED|exception|Exception|traceback|Traceback"
        r"|assert|ASSERT|cannot|Cannot|not found|Not Found",
        re.IGNORECASE,
    )

    hot_indices: set[int] = set()
    for i, line in enumerate(lines):
        if _ERROR_KEYWORDS.search(line):
            for j in range(max(0, i - 3), min(total, i + 4)):
                hot_indices.add(j)

    excerpt_lines = [lines[i] for i in sorted(hot_indices)]

    # Fall back to the last 200 lines if nothing matched
    if not excerpt_lines:
        excerpt_lines = lines[-200:]

    excerpt = "\n".join(excerpt_lines)
    if len(excerpt) > max_chars:
        # Keep the tail — errors usually appear at the end
        excerpt = "...\n" + excerpt[-max_chars:]
    return excerpt
