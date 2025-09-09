"""
Unit test runner script for cookie management functionality.

This script runs all unit tests with proper configuration and reporting.
"""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_tests():
    """Run all unit tests with comprehensive reporting."""
    
    # Test configuration
    test_args = [
        # Test discovery
        "tests/unit/",
        
        # Verbosity and output
        "-v",                    # Verbose output
        "--tb=short",           # Short traceback format
        "--strict-markers",     # Strict marker validation
        
        # Coverage reporting
        "--cov=app",            # Coverage for app package
        "--cov-report=term-missing",  # Terminal report with missing lines
        "--cov-report=html:htmlcov",  # HTML coverage report
        
        # Test execution
        "--maxfail=5",          # Stop after 5 failures
        "-x",                   # Stop on first failure (can be removed)
        
        # Markers
        "-m", "not slow",       # Skip slow tests by default
        
        # Output formatting
        "--color=yes",          # Colored output
    ]
    
    print("Running Unit Tests for Cookie Management")
    print("=" * 50)
    print(f"Python version: {sys.version}")
    print(f"Test directory: {project_root}/tests/unit/")
    print(f"Project root: {project_root}")
    print("=" * 50)
    
    # Run tests
    exit_code = pytest.main(test_args)
    
    print("\n" + "=" * 50)
    if exit_code == 0:
        print("✅ All unit tests passed!")
        print(f"📊 Coverage report generated: {project_root}/htmlcov/index.html")
    else:
        print("❌ Some tests failed!")
        print(f"Exit code: {exit_code}")
    print("=" * 50)
    
    return exit_code


def run_specific_test_suite(suite_name):
    """Run a specific test suite."""
    
    suite_mapping = {
        "cookie_manager": "tests/unit/core/test_cookie_manager.py",
        "validation": "tests/unit/utils/test_cookie_validation.py", 
        "s3": "tests/unit/core/test_s3_integration.py",
        "encryption": "tests/unit/core/test_encryption.py",
        "errors": "tests/unit/core/test_error_handling.py",
        "cleanup": "tests/unit/core/test_file_cleanup.py",
    }
    
    if suite_name not in suite_mapping:
        print(f"Unknown test suite: {suite_name}")
        print(f"Available suites: {', '.join(suite_mapping.keys())}")
        return 1
    
    test_file = suite_mapping[suite_name]
    
    test_args = [
        test_file,
        "-v",
        "--tb=short",
        "--color=yes",
    ]
    
    print(f"Running {suite_name} test suite")
    print(f"Test file: {test_file}")
    print("=" * 50)
    
    return pytest.main(test_args)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific test suite
        suite_name = sys.argv[1]
        exit_code = run_specific_test_suite(suite_name)
    else:
        # Run all tests
        exit_code = run_tests()
    
    sys.exit(exit_code)