"""
Unit tests for the failure classifier.

Each test feeds a ParsedLog with pre-populated signals and checks
that the correct FailureCategory and confidence are produced.
"""
from __future__ import annotations

import pytest

from app.db.models.investigation import FailureCategory
from app.services.investigation.classifier import classify_failure
from app.services.investigation.log_parser import ParsedLog


def _parsed(**kwargs) -> ParsedLog:
    """Helper: build a ParsedLog from keyword overrides."""
    base = ParsedLog(raw_text="")
    for k, v in kwargs.items():
        setattr(base, k, v)
    return base


class TestClassifier:
    def test_dependency_error_takes_priority(self) -> None:
        p = _parsed(
            raw_text="ModuleNotFoundError: No module named 'requests'",
            has_dependency_error=True,
            failing_tests=["tests/test_main.py::test_import"],
        )
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.DEPENDENCY_ERROR
        assert result.confidence >= 0.85

    def test_syntax_error_detected(self) -> None:
        p = _parsed(raw_text="SyntaxError: invalid syntax at line 42")
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.SYNTAX_ERROR

    def test_type_error_detected(self) -> None:
        p = _parsed(
            raw_text="src/index.ts(10,3): error TS2345: string not assignable",
            has_type_error=True,
        )
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.TYPE_ERROR

    def test_lint_failure_detected(self) -> None:
        p = _parsed(
            raw_text="ESLint: 3 errors found in src/app.js",
            has_lint_error=True,
        )
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.LINT_FAILURE

    def test_unit_test_failure(self) -> None:
        p = _parsed(
            raw_text="FAILED tests/test_calc.py::test_add - AssertionError",
            failing_tests=["tests/test_calc.py::test_add"],
        )
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.UNIT_TEST_FAILURE
        assert "tests/test_calc.py::test_add" in result.failing_tests

    def test_integration_test_failure(self) -> None:
        p = _parsed(
            raw_text="ECONNREFUSED 127.0.0.1:5432",
            failing_tests=["tests/integration/test_db.py::test_connect"],
        )
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.INTEGRATION_TEST_FAILURE

    def test_unknown_failure_low_confidence(self) -> None:
        p = _parsed(raw_text="Something weird happened but no clear pattern")
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.UNKNOWN
        assert result.confidence < 0.5

    def test_file_references_boost_confidence(self) -> None:
        p = _parsed(
            raw_text="FAILED tests/test_calc.py::test_add",
            failing_tests=["tests/test_calc.py::test_add"],
            referenced_files=["src/calc.py"],
        )
        result = classify_failure(p)
        assert result.failure_category == FailureCategory.UNIT_TEST_FAILURE
        # With file references, confidence should be boosted
        assert result.confidence > 0.85

    def test_result_serializable(self) -> None:
        p = _parsed(raw_text="SyntaxError: unexpected token")
        result = classify_failure(p)
        d = result.to_dict()
        assert "failure_category" in d
        assert "confidence" in d
        assert "recommended_action" in d
        assert isinstance(d["suspected_files"], list)

    def test_recommended_action_all_categories(self) -> None:
        """Every category must have a non-empty recommended action."""
        for category in FailureCategory:
            pattern_map = {
                FailureCategory.DEPENDENCY_ERROR: "ModuleNotFoundError: No module named 'x'",
                FailureCategory.SYNTAX_ERROR: "SyntaxError: invalid syntax",
                FailureCategory.TYPE_ERROR: "TS2345: error",
                FailureCategory.LINT_FAILURE: "ESLint: errors found",
                FailureCategory.UNIT_TEST_FAILURE: "FAILED tests/test.py::test_x",
                FailureCategory.INTEGRATION_TEST_FAILURE: "",
                FailureCategory.COMPILATION_ERROR: "compilation failed",
                FailureCategory.CONFIGURATION_ERROR: "configuration error",
                FailureCategory.ENVIRONMENT_FAILURE: "ENOMEM out of memory",
                FailureCategory.UNKNOWN: "",
            }
            p = ParsedLog(raw_text=pattern_map.get(category, ""))
            if category == FailureCategory.UNIT_TEST_FAILURE:
                p.failing_tests = ["tests/test.py::test_x"]
            result = classify_failure(p)
            assert result.recommended_action, f"No action for {category}"
