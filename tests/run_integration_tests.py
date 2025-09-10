"""
Integration test runner script for cookie management functionality.

This script runs integration tests with proper configuration and reporting.
"""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_integration_tests():
    """Run all integration tests with comprehensive reporting."""
    
    # Test configuration
    test_args = [
        # Test discovery
        "tests/integration/",
        
        # Verbosity and output
        "-v",                    # Verbose output
        "--tb=short",           # Short traceback format
        "--strict-markers",     # Strict marker validation
        
        # Coverage reporting (optional for integration)
        # "--cov=app",            # Coverage for app package
        # "--cov-report=term-missing",  # Terminal report with missing lines
        
        # Test execution
        "--maxfail=3",          # Stop after 3 failures
        "-x",                   # Stop on first failure (can be removed)
        
        # Markers
        "-m", "integration",    # Run only integration tests
        
        # Output formatting
        "--color=yes",          # Colored output
        
        # Asyncio mode
        "--asyncio-mode=auto",  # Handle async tests automatically
    ]
    
    print("Running Integration Tests for Cookie Management")
    print("=" * 55)
    print(f"Python version: {sys.version}")
    print(f"Test directory: {project_root}/tests/integration/")
    print(f"Project root: {project_root}")
    print("=" * 55)
    
    # Run tests
    exit_code = pytest.main(test_args)
    
    print("\n" + "=" * 55)
    if exit_code == 0:
        print("✅ All integration tests passed!")
    else:
        print("❌ Some integration tests failed!")
        print(f"Exit code: {exit_code}")
    print("=" * 55)
    
    return exit_code


def run_specific_integration_suite(suite_name):
    """Run a specific integration test suite."""
    
    suite_mapping = {
        "youtube_integration": "tests/integration/test_youtube_downloader_integration.py",
        "end_to_end": "tests/integration/test_end_to_end_workflow.py",
        "fallback": "tests/integration/test_cookie_fallback_scenarios.py",
        "s3_connectivity": "tests/integration/test_s3_connectivity.py",
        "ecs_container": "tests/integration/test_ecs_container_integration.py",
        "cookie_rotation": "tests/integration/test_cookie_rotation_procedures.py",
    }
    
    if suite_name not in suite_mapping:
        print(f"Unknown integration test suite: {suite_name}")
        print(f"Available suites: {', '.join(suite_mapping.keys())}")
        return 1
    
    test_file = suite_mapping[suite_name]
    
    test_args = [
        test_file,
        "-v",
        "--tb=short",
        "--color=yes",
        "--asyncio-mode=auto",
        "-m", "integration",
    ]
    
    print(f"Running {suite_name} integration test suite")
    print(f"Test file: {test_file}")
    print("=" * 55)
    
    return pytest.main(test_args)


def run_integration_tests_with_network():
    """Run integration tests including network-dependent tests."""
    
    test_args = [
        "tests/integration/",
        "-v",
        "--tb=short",
        "--strict-markers",
        "--maxfail=5",
        "--color=yes",
        "--asyncio-mode=auto",
        "-m", "integration",
        "--network",  # Enable network tests
    ]
    
    print("Running Integration Tests with Network Access")
    print("=" * 55)
    print("⚠️  Network-dependent tests enabled")
    print("=" * 55)
    
    return pytest.main(test_args)


def run_slow_integration_tests():
    """Run slow integration tests."""
    
    test_args = [
        "tests/integration/",
        "-v",
        "--tb=long",
        "--strict-markers", 
        "--maxfail=2",
        "--color=yes",
        "--asyncio-mode=auto",
        "-m", "integration and slow_integration",
        "--integration-slow",
    ]
    
    print("Running Slow Integration Tests")
    print("=" * 55)
    print("⏰ This may take several minutes...")
    print("=" * 55)
    
    return pytest.main(test_args)


def generate_integration_test_report():
    """Generate comprehensive integration test report."""
    
    test_args = [
        "tests/integration/",
        "-v",
        "--tb=short",
        "--strict-markers",
        "-m", "integration",
        "--color=yes",
        "--asyncio-mode=auto",
        
        # Comprehensive reporting
        "--junitxml=reports/integration_tests.xml",
        "--html=reports/integration_tests.html",
        "--self-contained-html",
        
        # Coverage for integration components
        "--cov=app.services.downloader",
        "--cov=app.core.cookie_manager", 
        "--cov-report=html:reports/integration_coverage",
        "--cov-report=term-missing",
    ]
    
    # Create reports directory
    reports_dir = project_root / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    print("Generating Comprehensive Integration Test Report")
    print("=" * 55)
    print(f"Reports will be saved to: {reports_dir}")
    print("=" * 55)
    
    exit_code = pytest.main(test_args)
    
    print("\n" + "=" * 55)
    if exit_code == 0:
        print("✅ Integration test report generated successfully!")
        print(f"📊 HTML Report: {reports_dir}/integration_tests.html")
        print(f"📋 JUnit XML: {reports_dir}/integration_tests.xml")
        print(f"📊 Coverage Report: {reports_dir}/integration_coverage/index.html")
    else:
        print("❌ Integration test report generation failed!")
    print("=" * 55)
    
    return exit_code


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run integration tests for cookie management")
    parser.add_argument("--suite", type=str, help="Run specific test suite")
    parser.add_argument("--network", action="store_true", help="Enable network-dependent tests")
    parser.add_argument("--slow", action="store_true", help="Run slow integration tests")
    parser.add_argument("--report", action="store_true", help="Generate comprehensive test report")
    
    args = parser.parse_args()
    
    if args.suite:
        exit_code = run_specific_integration_suite(args.suite)
    elif args.network:
        exit_code = run_integration_tests_with_network()
    elif args.slow:
        exit_code = run_slow_integration_tests()
    elif args.report:
        exit_code = generate_integration_test_report()
    else:
        exit_code = run_integration_tests()
    
    sys.exit(exit_code)