"""
Failure classifier.

Maps parsed log signals to a FailureCategory and produces a structured
InvestigationResult.

Uses rule-based classification first (fast, no LLM cost).
The AI phase (Phase 4) can override the category if it disagrees.

Priority order (most specific first):
1. DEPENDENCY_ERROR
2. SYNTAX_ERROR
3. TYPE_ERROR
4. LINT_FAILURE
5. UNIT_TEST_FAILURE
6. INTEGRATION_TEST_FAILURE
7. COMPILATION_ERROR
8. CONFIGURATION_ERROR
9. ENVIRONMENT_FAILURE
10. UNKNOWN
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.db.models.investigation import FailureCategory
from app.services.investigation.log_parser import ParsedLog

if TYPE_CHECKING:
    pass


@dataclass
class InvestigationResult:
    """Structured result of classifying a workflow failure."""

    failure_category: FailureCategory
    error_summary: str
    relevant_excerpt: str
    suspected_files: list[str]
    failing_tests: list[str]
    error_lines: list[str]
    confidence: float
    recommended_action: str

    def to_dict(self) -> dict:
        return {
            "failure_category": self.failure_category.value,
            "error_summary": self.error_summary,
            "relevant_excerpt": self.relevant_excerpt[:4000],  # DB size guard
            "suspected_files": self.suspected_files,
            "failing_tests": self.failing_tests,
            "error_lines": self.error_lines[:20],
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
        }


# ------------------------------------------------------------------ #
# Rule patterns for category detection
# ------------------------------------------------------------------ #
_SYNTAX_PATTERNS = re.compile(
    r"SyntaxError|IndentationError|unexpected token|Unexpected token"
    r"|parse error|ParseError|invalid syntax",
    re.IGNORECASE,
)
_DEP_PATTERNS = re.compile(
    r"ModuleNotFoundError|Cannot find module|npm ERR!|pip.*ERROR"
    r"|Could not install|Package.*not found|Dependency.*not.*found"
    r"|No module named|UNMET DEPENDENCY",
    re.IGNORECASE,
)
_TYPE_PATTERNS = re.compile(
    r"TS\d{4}:|TypeError:|type.*error|incompatible type"
    r"|Property.*does not exist|is not assignable to type",
    re.IGNORECASE,
)
_LINT_PATTERNS = re.compile(
    r"ESLint|eslint|pylint|flake8|ruff.*error|mypy.*error"
    r"|Lint.*failed|lint.*error",
    re.IGNORECASE,
)
_TEST_PATTERNS = re.compile(
    r"FAILED\s+.*::.*|Tests:.*\d+ failed|test.*failed|assertion.*failed"
    r"|AssertionError|expect\(.*\)\.to",
    re.IGNORECASE,
)
_INTEGRATION_HINTS = re.compile(
    r"connection refused|ECONNREFUSED|database.*error|redis.*error"
    r"|timeout.*connect|service.*unavailable",
    re.IGNORECASE,
)
_COMPILE_PATTERNS = re.compile(
    r"compilation failed|build.*failed|error.*compil"
    r"|javac|tsc.*error|gcc.*error",
    re.IGNORECASE,
)
_CONFIG_PATTERNS = re.compile(
    r"configuration.*error|config.*not found|missing.*config"
    r"|invalid.*yaml|yaml.*error|\.env.*missing",
    re.IGNORECASE,
)
_ENV_PATTERNS = re.compile(
    r"ENOMEM|out of memory|killed|OOMKilled|disk.*full"
    r"|permission denied|EACCES|EPERM|environment.*error",
    re.IGNORECASE,
)


def classify_failure(parsed: ParsedLog) -> InvestigationResult:
    """
    Classify a parsed log into a FailureCategory.

    :param parsed: structured output from log_parser.parse_log()
    :returns: InvestigationResult with category, summary and confidence
    """
    text = parsed.raw_text

    # ------------------------------------------------------------------ #
    # Check signals in priority order
    # ------------------------------------------------------------------ #
    category: FailureCategory
    confidence: float
    summary: str

    if parsed.has_dependency_error or _DEP_PATTERNS.search(text):
        category = FailureCategory.DEPENDENCY_ERROR
        confidence = 0.90
        match = _DEP_PATTERNS.search(text)
        summary = _first_match_line(text, _DEP_PATTERNS) or "Dependency installation failed"

    elif parsed.has_syntax_error or _SYNTAX_PATTERNS.search(text):
        category = FailureCategory.SYNTAX_ERROR
        confidence = 0.92
        summary = _first_match_line(text, _SYNTAX_PATTERNS) or "Syntax error detected"

    elif parsed.has_type_error or _TYPE_PATTERNS.search(text):
        category = FailureCategory.TYPE_ERROR
        confidence = 0.88
        summary = _first_match_line(text, _TYPE_PATTERNS) or "Type error detected"

    elif parsed.has_lint_error or _LINT_PATTERNS.search(text):
        category = FailureCategory.LINT_FAILURE
        confidence = 0.90
        summary = _first_match_line(text, _LINT_PATTERNS) or "Lint check failed"

    elif _INTEGRATION_HINTS.search(text) and parsed.failing_tests:
        category = FailureCategory.INTEGRATION_TEST_FAILURE
        confidence = 0.75
        summary = "Integration test failure (connectivity issues detected)"

    elif parsed.failing_tests or _TEST_PATTERNS.search(text):
        category = FailureCategory.UNIT_TEST_FAILURE
        confidence = 0.85
        if parsed.failing_tests:
            summary = f"Test failures: {', '.join(parsed.failing_tests[:3])}"
        else:
            summary = _first_match_line(text, _TEST_PATTERNS) or "Tests failed"

    elif _COMPILE_PATTERNS.search(text):
        category = FailureCategory.COMPILATION_ERROR
        confidence = 0.85
        summary = _first_match_line(text, _COMPILE_PATTERNS) or "Build/compilation failed"

    elif _CONFIG_PATTERNS.search(text):
        category = FailureCategory.CONFIGURATION_ERROR
        confidence = 0.78
        summary = _first_match_line(text, _CONFIG_PATTERNS) or "Configuration error"

    elif _ENV_PATTERNS.search(text):
        category = FailureCategory.ENVIRONMENT_FAILURE
        confidence = 0.80
        summary = _first_match_line(text, _ENV_PATTERNS) or "Environment-level failure"

    else:
        category = FailureCategory.UNKNOWN
        confidence = 0.30
        # Use the last error annotation or first error line
        if parsed.error_annotations:
            summary = parsed.error_annotations[0][:200]
        elif parsed.error_lines:
            summary = parsed.error_lines[0][:200]
        else:
            summary = "Failure reason could not be determined from logs"

    # Boost confidence if we also have specific file references
    if parsed.referenced_files and category != FailureCategory.UNKNOWN:
        confidence = min(confidence + 0.05, 0.98)

    recommended_action = _recommend_action(category)

    return InvestigationResult(
        failure_category=category,
        error_summary=summary[:500],
        relevant_excerpt=parsed.relevant_excerpt,
        suspected_files=parsed.referenced_files[:10],
        failing_tests=parsed.failing_tests[:10],
        error_lines=parsed.error_lines[:15],
        confidence=round(confidence, 2),
        recommended_action=recommended_action,
    )


def _first_match_line(text: str, pattern: re.Pattern) -> str | None:
    """Return the full line containing the first regex match, truncated."""
    m = pattern.search(text)
    if not m:
        return None
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.end())
    if end == -1:
        end = len(text)
    return text[start:end].strip()[:300]


def _recommend_action(category: FailureCategory) -> str:
    mapping = {
        FailureCategory.DEPENDENCY_ERROR: "Update or add the missing dependency in the package manifest",
        FailureCategory.SYNTAX_ERROR: "Fix the syntax error in the referenced file",
        FailureCategory.TYPE_ERROR: "Resolve the type mismatch in the referenced file",
        FailureCategory.LINT_FAILURE: "Fix the lint violation in the referenced file",
        FailureCategory.UNIT_TEST_FAILURE: "Fix the failing unit test or the code under test",
        FailureCategory.INTEGRATION_TEST_FAILURE: "Investigate service connectivity and fix the integration point",
        FailureCategory.COMPILATION_ERROR: "Resolve the compilation error in the referenced file",
        FailureCategory.CONFIGURATION_ERROR: "Fix or add the missing configuration value",
        FailureCategory.ENVIRONMENT_FAILURE: "Investigate the execution environment (resources, permissions)",
        FailureCategory.UNKNOWN: "Manual investigation required — no clear pattern detected",
    }
    return mapping.get(category, "Manual investigation required")
