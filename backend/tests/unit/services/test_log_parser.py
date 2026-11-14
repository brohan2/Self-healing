"""
Unit tests for the log parser.

All inputs are synthetic — no external services called.
"""
from __future__ import annotations

import pytest

from app.services.investigation.log_parser import parse_log


class TestLogParserPython:
    def test_extracts_python_traceback(self) -> None:
        log = """
Some output here
Traceback (most recent call last):
  File "src/app.py", line 42, in compute
    result = x / y
ZeroDivisionError: division by zero

More output after
"""
        result = parse_log(log)
        assert len(result.stack_traces) == 1
        assert "ZeroDivisionError" in result.stack_traces[0]

    def test_extracts_python_error_line(self) -> None:
        log = "AttributeError: 'NoneType' object has no attribute 'split'"
        result = parse_log(log)
        assert any("AttributeError" in e for e in result.error_lines)

    def test_extracts_module_not_found(self) -> None:
        log = "ModuleNotFoundError: No module named 'requests'"
        result = parse_log(log)
        assert result.has_dependency_error

    def test_extracts_pytest_failed_tests(self) -> None:
        log = """
FAILED tests/test_cart.py::test_add_to_cart - AssertionError
FAILED tests/test_cart.py::test_checkout - ValueError
"""
        result = parse_log(log)
        assert "tests/test_cart.py::test_add_to_cart" in result.failing_tests
        assert "tests/test_cart.py::test_checkout" in result.failing_tests

    def test_extracts_exit_code(self) -> None:
        log = "Process completed with exit code 1"
        result = parse_log(log)
        assert 1 in result.exit_codes

    def test_no_exit_code_on_success(self) -> None:
        log = "Process completed with exit code 0"
        result = parse_log(log)
        assert 0 not in result.exit_codes

    def test_extracts_file_references(self) -> None:
        log = 'File "src/utils.py", line 10, in helper'
        result = parse_log(log)
        assert "src/utils.py" in result.referenced_files

    def test_excerpt_bounded(self) -> None:
        # Create a very long log
        log = "error: something failed\n" + ("ok\n" * 10000)
        result = parse_log(log, max_excerpt_chars=1000)
        assert len(result.relevant_excerpt) <= 1010  # small tolerance for "...\n"


class TestLogParserTypeScript:
    def test_extracts_ts_errors(self) -> None:
        log = "src/cart.ts(42,15): error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'."
        result = parse_log(log)
        assert result.has_type_error
        assert "src/cart.ts" in result.referenced_files

    def test_extracts_eslint_errors(self) -> None:
        log = "src/utils.js  12:5  error  'foo' is defined but never used  no-unused-vars"
        result = parse_log(log)
        assert result.has_lint_error


class TestLogParserDependency:
    def test_npm_err(self) -> None:
        log = "npm ERR! code ERESOLVE\nnpm ERR! Could not resolve dependency"
        result = parse_log(log)
        assert result.has_dependency_error

    def test_pip_error(self) -> None:
        log = "pip ERROR: Could not install packages due to an OSError"
        result = parse_log(log)
        assert result.has_dependency_error


class TestLogParserEmpty:
    def test_empty_log(self) -> None:
        result = parse_log("")
        assert result.error_lines == []
        assert result.stack_traces == []
        assert result.failing_tests == []
        assert not result.has_dependency_error

    def test_clean_log_no_errors(self) -> None:
        log = "All tests passed!\nBuild successful.\nDone in 5.23s."
        result = parse_log(log)
        assert not result.has_dependency_error
        assert not result.has_type_error
        assert not result.has_lint_error
        assert result.exit_codes == []
