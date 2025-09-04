#!/usr/bin/env python3
"""
Test runner script with coverage reporting for YouTube Download Service.

This script provides convenient commands for running tests with various options
including coverage reporting, parallel execution, and different test categories.
"""

import os
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional


def run_command(cmd: List[str], cwd: Optional[str] = None) -> int:
    """
    Run a command and return the exit code.
    
    Args:
        cmd: Command and arguments as a list
        cwd: Working directory for the command
        
    Returns:
        int: Exit code from the command
    """
    print(f"Running: {' '.join(cmd)}")
    if cwd:
        print(f"Working directory: {cwd}")
    
    try:
        result = subprocess.run(cmd, cwd=cwd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n⚠️  Test run interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return 1


def get_project_root() -> Path:
    """Get the project root directory."""
    current_dir = Path(__file__).parent
    # Go up one level to reach project root
    return current_dir.parent


def is_docker_available() -> bool:
    """Check if Docker is available."""
    return shutil.which("docker") is not None and shutil.which("docker-compose") is not None


def is_running_in_docker() -> bool:
    """Check if currently running inside a Docker container."""
    return os.path.exists("/.dockerenv") or os.environ.get("DOCKER_ENV") == "true"


def get_docker_compose_services() -> List[str]:
    """Get list of running Docker Compose services."""
    try:
        result = subprocess.run(
            ["docker-compose", "ps", "--services", "--filter", "status=running"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def ensure_docker_environment(force_setup: bool = False) -> bool:
    """
    Ensure Docker environment is ready for testing.
    
    Args:
        force_setup: Force setup even if services are running
        
    Returns:
        bool: True if Docker environment is ready
    """
    if not is_docker_available():
        print("❌ Docker or docker-compose not found. Please install Docker.")
        return False
    
    project_root = get_project_root()
    
    # Check if services are already running
    running_services = get_docker_compose_services()
    
    if "app" not in running_services or force_setup:
        print("🐳 Starting Docker services...")
        # Use development compose file for testing
        startup_cmd = [
            "docker-compose", 
            "-f", "docker-compose.yml", 
            "-f", "docker-compose.dev.yml", 
            "up", "-d"
        ]
        
        result = run_command(startup_cmd, str(project_root))
        if result != 0:
            print("❌ Failed to start Docker services")
            return False
        
        print("⏳ Waiting for services to be ready...")
        import time
        time.sleep(10)  # Give services time to start
    
    # Verify test dependencies are installed
    check_deps_cmd = [
        "docker-compose", "exec", "-T", "app", 
        "python", "-c", "import pytest; print('✅ Test dependencies available')"
    ]
    
    result = subprocess.run(check_deps_cmd, cwd=str(project_root), capture_output=True)
    if result.returncode != 0:
        print("⏳ Installing test dependencies in container...")
        install_cmd = [
            "docker-compose", "exec", "-T", "app",
            "pip", "install", "--user", "-r", "requirements-dev.txt"
        ]
        install_result = run_command(install_cmd, str(project_root))
        if install_result != 0:
            print("❌ Failed to install test dependencies")
            return False
    
    print("✅ Docker environment ready for testing")
    return True


def run_tests_in_docker(
    test_path: Optional[str] = None,
    coverage: bool = True,
    html_report: bool = False,
    xml_report: bool = False,
    parallel: bool = False,
    verbose: bool = False,
    markers: Optional[str] = None,
    failed_first: bool = False,
    stop_on_fail: bool = False,
    collect_only: bool = False
) -> int:
    """
    Run tests inside Docker container.
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    project_root = get_project_root()
    
    # Build pytest command
    pytest_cmd = ["python", "-m", "pytest"]
    
    # Add test path if specified
    if test_path:
        pytest_cmd.append(test_path)
    
    # Coverage options
    if coverage:
        pytest_cmd.extend(["--cov=app", "--cov-report=term-missing"])
        
        if html_report:
            pytest_cmd.append("--cov-report=html:htmlcov")
            
        if xml_report:
            pytest_cmd.append("--cov-report=xml:coverage.xml")
    
    # Parallel execution (if pytest-xdist is available)
    if parallel:
        pytest_cmd.extend(["-n", "auto"])
    
    # Verbose output
    if verbose:
        pytest_cmd.extend(["-v", "--tb=long"])
    else:
        pytest_cmd.extend(["--tb=short"])
    
    # Test markers
    if markers:
        pytest_cmd.extend(["-m", markers])
    
    # Failed first
    if failed_first:
        pytest_cmd.append("--lf")
    
    # Stop on first failure
    if stop_on_fail:
        pytest_cmd.append("-x")
    
    # Collect only
    if collect_only:
        pytest_cmd.append("--collect-only")
    
    # Execute in Docker container
    docker_cmd = ["docker-compose", "exec", "-T", "app"] + pytest_cmd
    
    print(f"🐳 Running tests in Docker: {' '.join(pytest_cmd)}")
    exit_code = run_command(docker_cmd, str(project_root))
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
        
        if coverage and html_report:
            html_path = project_root / "htmlcov" / "index.html"
            print(f"📊 HTML coverage report: {html_path}")
        
        if coverage and xml_report:
            xml_path = project_root / "coverage.xml"
            print(f"📄 XML coverage report: {xml_path}")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    return exit_code


def run_tests(
    test_path: Optional[str] = None,
    coverage: bool = True,
    html_report: bool = False,
    xml_report: bool = False,
    parallel: bool = False,
    verbose: bool = False,
    markers: Optional[str] = None,
    failed_first: bool = False,
    stop_on_fail: bool = False,
    collect_only: bool = False,
    use_docker: bool = False,
    setup_docker: bool = False
) -> int:
    """
    Run tests with specified options.
    
    Args:
        test_path: Specific test file or directory to run
        coverage: Enable coverage reporting
        html_report: Generate HTML coverage report
        xml_report: Generate XML coverage report  
        parallel: Run tests in parallel
        verbose: Enable verbose output
        markers: Pytest markers to filter tests (e.g., "unit", "integration")
        failed_first: Run failed tests first
        stop_on_fail: Stop on first failure
        collect_only: Only collect tests, don't run them
        use_docker: Force Docker execution
        setup_docker: Setup Docker environment before running
        
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    # Auto-detect or force Docker usage
    should_use_docker = use_docker or (
        is_docker_available() and 
        not is_running_in_docker() and
        not shutil.which("pytest")  # No local pytest available
    )
    
    if should_use_docker:
        print("🐳 Using Docker environment for testing")
        
        # Setup Docker environment if requested
        if setup_docker or not get_docker_compose_services():
            if not ensure_docker_environment(force_setup=setup_docker):
                return 1
        
        # Run tests in Docker
        return run_tests_in_docker(
            test_path=test_path,
            coverage=coverage,
            html_report=html_report,
            xml_report=xml_report,
            parallel=parallel,
            verbose=verbose,
            markers=markers,
            failed_first=failed_first,
            stop_on_fail=stop_on_fail,
            collect_only=collect_only
        )
    
    # Run tests locally
    print("🔧 Using local Python environment for testing")
    project_root = get_project_root()
    
    # Base pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test path if specified
    if test_path:
        cmd.append(test_path)
    
    # Coverage options
    if coverage:
        cmd.extend(["--cov=app", "--cov-report=term-missing"])
        
        if html_report:
            cmd.append("--cov-report=html:htmlcov")
            
        if xml_report:
            cmd.append("--cov-report=xml:coverage.xml")
    
    # Parallel execution
    if parallel:
        cmd.extend(["-n", "auto"])
    
    # Verbose output
    if verbose:
        cmd.extend(["-v", "--tb=long"])
    else:
        cmd.extend(["--tb=short"])
    
    # Test markers
    if markers:
        cmd.extend(["-m", markers])
    
    # Failed first
    if failed_first:
        cmd.append("--lf")
    
    # Stop on first failure
    if stop_on_fail:
        cmd.append("-x")
    
    # Collect only
    if collect_only:
        cmd.append("--collect-only")
    
    # Run the tests
    exit_code = run_command(cmd, str(project_root))
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
        
        if coverage and html_report:
            html_path = project_root / "htmlcov" / "index.html"
            if html_path.exists():
                print(f"📊 HTML coverage report: {html_path}")
        
        if coverage and xml_report:
            xml_path = project_root / "coverage.xml"
            if xml_path.exists():
                print(f"📄 XML coverage report: {xml_path}")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    return exit_code


def run_unit_tests(coverage: bool = True, html_report: bool = False, use_docker: bool = False, setup_docker: bool = False) -> int:
    """Run only unit tests."""
    print("🧪 Running unit tests...")
    return run_tests(
        test_path="tests/unit",
        coverage=coverage,
        html_report=html_report,
        markers="unit",
        use_docker=use_docker,
        setup_docker=setup_docker
    )


def run_integration_tests(coverage: bool = True, use_docker: bool = False, setup_docker: bool = False) -> int:
    """Run only integration tests."""
    print("🔗 Running integration tests...")
    return run_tests(
        test_path="tests/integration", 
        coverage=coverage,
        markers="integration",
        use_docker=use_docker,
        setup_docker=setup_docker
    )


def run_all_tests(coverage: bool = True, html_report: bool = False, use_docker: bool = False, setup_docker: bool = False) -> int:
    """Run all tests."""
    print("🚀 Running all tests...")
    return run_tests(
        coverage=coverage,
        html_report=html_report,
        xml_report=True,
        use_docker=use_docker,
        setup_docker=setup_docker
    )


def run_fast_tests(use_docker: bool = False, setup_docker: bool = False) -> int:
    """Run fast tests only (exclude slow and external tests)."""
    print("⚡ Running fast tests only...")
    return run_tests(
        coverage=True,
        markers="not slow and not external",
        parallel=True,
        use_docker=use_docker,
        setup_docker=setup_docker
    )


def run_coverage_only() -> int:
    """Generate coverage report without running tests again."""
    print("📊 Generating coverage report...")
    project_root = get_project_root()
    
    # Check if .coverage file exists
    coverage_file = project_root / ".coverage"
    if not coverage_file.exists():
        print("❌ No coverage data found. Run tests first with coverage enabled.")
        return 1
    
    # Generate HTML report
    cmd = ["python", "-m", "coverage", "html", "--directory=htmlcov"]
    html_exit = run_command(cmd, str(project_root))
    
    # Generate XML report  
    cmd = ["python", "-m", "coverage", "xml", "--output=coverage.xml"]
    xml_exit = run_command(cmd, str(project_root))
    
    # Show coverage report
    cmd = ["python", "-m", "coverage", "report", "--show-missing"]
    report_exit = run_command(cmd, str(project_root))
    
    if html_exit == 0:
        html_path = project_root / "htmlcov" / "index.html"
        print(f"📊 HTML coverage report: {html_path}")
    
    return max(html_exit, xml_exit, report_exit)


def watch_tests() -> int:
    """Watch for file changes and re-run tests."""
    print("👀 Watching for changes and running tests...")
    try:
        import pytest_watch
    except ImportError:
        print("❌ pytest-watch not installed. Install with: pip install pytest-watch")
        return 1
    
    project_root = get_project_root()
    cmd = ["python", "-m", "pytest_watch", "--", "--cov=app", "--cov-report=term-missing"]
    return run_command(cmd, str(project_root))


def clean_coverage() -> int:
    """Clean coverage data and reports."""
    print("🧹 Cleaning coverage data...")
    project_root = get_project_root()
    
    files_to_remove = [
        ".coverage",
        "coverage.xml",
        "htmlcov"
    ]
    
    for item in files_to_remove:
        path = project_root / item
        if path.exists():
            if path.is_file():
                path.unlink()
                print(f"Removed: {path}")
            elif path.is_dir():
                import shutil
                shutil.rmtree(path)
                print(f"Removed directory: {path}")
    
    print("✅ Coverage data cleaned")
    return 0


def main():
    """Main entry point for the test runner."""
    parser = argparse.ArgumentParser(
        description="YouTube Download Service Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_runner.py                    # Run all tests with coverage (auto-detect Docker)
  python scripts/test_runner.py --unit             # Run unit tests only
  python scripts/test_runner.py --integration      # Run integration tests only
  python scripts/test_runner.py --fast             # Run fast tests only
  python scripts/test_runner.py --docker           # Force Docker execution
  python scripts/test_runner.py --setup            # Setup Docker environment first
  python scripts/test_runner.py --html             # Generate HTML coverage report
  python scripts/test_runner.py --coverage-only    # Generate coverage report only
  python scripts/test_runner.py --clean            # Clean coverage data
  python scripts/test_runner.py --watch            # Watch and re-run tests
  python scripts/test_runner.py tests/unit/models  # Run specific test directory
  python scripts/test_runner.py --markers "unit"   # Run tests with specific markers
        """
    )
    
    # Test selection options
    test_group = parser.add_mutually_exclusive_group()
    test_group.add_argument("--unit", action="store_true", help="Run unit tests only")
    test_group.add_argument("--integration", action="store_true", help="Run integration tests only")
    test_group.add_argument("--fast", action="store_true", help="Run fast tests only (exclude slow/external)")
    test_group.add_argument("--all", action="store_true", help="Run all tests (default)")
    
    # Coverage options
    parser.add_argument("--no-coverage", action="store_true", help="Disable coverage reporting")
    parser.add_argument("--html", action="store_true", help="Generate HTML coverage report")
    parser.add_argument("--xml", action="store_true", help="Generate XML coverage report")
    parser.add_argument("--coverage-only", action="store_true", help="Generate coverage report only")
    
    # Test execution options
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--markers", type=str, help="Pytest markers to filter tests")
    parser.add_argument("--failed-first", action="store_true", help="Run failed tests first")
    parser.add_argument("-x", "--stop-on-fail", action="store_true", help="Stop on first failure")
    parser.add_argument("--collect-only", action="store_true", help="Only collect tests, don't run")
    
    # Docker options
    parser.add_argument("--docker", action="store_true", help="Force Docker execution")
    parser.add_argument("--setup", action="store_true", help="Setup Docker environment before running")
    
    # Utility options
    parser.add_argument("--watch", action="store_true", help="Watch for changes and re-run tests")
    parser.add_argument("--clean", action="store_true", help="Clean coverage data and reports")
    
    # Positional argument for specific test path
    parser.add_argument("test_path", nargs="?", help="Specific test file or directory to run")
    
    args = parser.parse_args()
    
    # Handle utility commands first
    if args.clean:
        return clean_coverage()
    
    if args.coverage_only:
        return run_coverage_only()
    
    if args.watch:
        return watch_tests()
    
    # Determine coverage settings
    coverage_enabled = not args.no_coverage
    
    # Run specific test categories
    if args.unit:
        return run_unit_tests(
            coverage=coverage_enabled, 
            html_report=args.html,
            use_docker=args.docker,
            setup_docker=args.setup
        )
    elif args.integration:
        return run_integration_tests(
            coverage=coverage_enabled,
            use_docker=args.docker,
            setup_docker=args.setup
        )
    elif args.fast:
        return run_fast_tests(
            use_docker=args.docker,
            setup_docker=args.setup
        )
    else:
        # Run all tests or specific path
        if args.test_path:
            return run_tests(
                test_path=args.test_path,
                coverage=coverage_enabled,
                html_report=args.html,
                xml_report=args.xml,
                parallel=args.parallel,
                verbose=args.verbose,
                markers=args.markers,
                failed_first=args.failed_first,
                stop_on_fail=args.stop_on_fail,
                collect_only=args.collect_only,
                use_docker=args.docker,
                setup_docker=args.setup
            )
        else:
            return run_all_tests(
                coverage=coverage_enabled, 
                html_report=args.html,
                use_docker=args.docker,
                setup_docker=args.setup
            )


if __name__ == "__main__":
    sys.exit(main())