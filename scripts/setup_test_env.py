#!/usr/bin/env python3
"""
Automated Docker test environment setup script.

This script ensures that the Docker testing environment is properly configured
and all dependencies are installed for running tests.
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

# Colors for output
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def print_status(message: str) -> None:
    """Print status message."""
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def print_success(message: str) -> None:
    """Print success message."""
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {message}")


def print_warning(message: str) -> None:
    """Print warning message."""
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def run_command(cmd: List[str], cwd: Optional[str] = None, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print_status(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, 
            cwd=cwd, 
            capture_output=capture_output,
            text=True,
            check=False
        )
        return result
    except Exception as e:
        print_error(f"Failed to run command: {e}")
        return subprocess.CompletedProcess(cmd, 1, "", str(e))


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def check_docker_availability() -> bool:
    """Check if Docker and docker-compose are available."""
    print_status("Checking Docker availability...")
    
    # Check Docker
    docker_result = run_command(["docker", "--version"], capture_output=True)
    if docker_result.returncode != 0:
        print_error("Docker is not installed or not accessible")
        return False
    
    # Check docker-compose
    compose_result = run_command(["docker-compose", "--version"], capture_output=True)
    if compose_result.returncode != 0:
        print_error("docker-compose is not installed or not accessible")
        return False
    
    print_success("Docker and docker-compose are available")
    return True


def get_running_services() -> List[str]:
    """Get list of currently running Docker Compose services."""
    result = run_command([
        "docker-compose", "ps", "--services", "--filter", "status=running"
    ], capture_output=True)
    
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split('\n')
    return []


def start_docker_services(use_dev_compose: bool = True) -> bool:
    """Start Docker services for testing."""
    project_root = get_project_root()
    
    print_status("Starting Docker services...")
    
    # Build command
    cmd = ["docker-compose"]
    if use_dev_compose:
        cmd.extend(["-f", "docker-compose.yml", "-f", "docker-compose.dev.yml"])
    
    cmd.extend(["up", "-d"])
    
    result = run_command(cmd, cwd=str(project_root))
    if result.returncode != 0:
        print_error("Failed to start Docker services")
        return False
    
    print_success("Docker services started")
    
    # Wait for services to be ready
    print_status("Waiting for services to be ready...")
    time.sleep(15)  # Give services time to start
    
    return True


def install_dev_dependencies() -> bool:
    """Install development dependencies in the app container."""
    print_status("Installing development dependencies...")
    
    project_root = get_project_root()
    
    # Check if dependencies are already installed
    check_cmd = [
        "docker-compose", "exec", "-T", "app",
        "python", "-c", "import pytest; print('Dependencies available')"
    ]
    
    result = run_command(check_cmd, cwd=str(project_root), capture_output=True)
    if result.returncode == 0:
        print_success("Development dependencies already installed")
        return True
    
    # Install dependencies
    install_cmd = [
        "docker-compose", "exec", "-T", "app",
        "pip", "install", "--user", "-r", "requirements-dev.txt"
    ]
    
    result = run_command(install_cmd, cwd=str(project_root))
    if result.returncode != 0:
        print_error("Failed to install development dependencies")
        return False
    
    print_success("Development dependencies installed")
    return True


def verify_test_files_mounted() -> bool:
    """Verify that test files are properly mounted in the container."""
    print_status("Verifying test file mounts...")
    
    project_root = get_project_root()
    
    # Check if test files are accessible
    check_cmd = [
        "docker-compose", "exec", "-T", "app",
        "ls", "-la", "/app/tests/"
    ]
    
    result = run_command(check_cmd, cwd=str(project_root), capture_output=True)
    if result.returncode != 0:
        print_error("Test files not properly mounted")
        return False
    
    # Check for pytest.ini
    check_pytest_cmd = [
        "docker-compose", "exec", "-T", "app",
        "test", "-f", "/app/pytest.ini"
    ]
    
    result = run_command(check_pytest_cmd, cwd=str(project_root), capture_output=True)
    if result.returncode != 0:
        print_warning("pytest.ini not found in container")
        return False
    
    print_success("Test files properly mounted")
    return True


def run_test_verification() -> bool:
    """Run a simple test to verify the environment is working."""
    print_status("Running test verification...")
    
    project_root = get_project_root()
    
    # Run a simple test collection
    test_cmd = [
        "docker-compose", "exec", "-T", "app",
        "python", "-m", "pytest", "--collect-only", "tests/unit", "-q"
    ]
    
    result = run_command(test_cmd, cwd=str(project_root))
    if result.returncode != 0:
        print_error("Test verification failed")
        return False
    
    print_success("Test environment verified")
    return True


def show_environment_info() -> None:
    """Display information about the test environment."""
    project_root = get_project_root()
    
    print("\n" + "=" * 60)
    print_success("Docker Test Environment Setup Complete!")
    print("=" * 60)
    
    print("\n📋 Environment Information:")
    print(f"  Project Root: {project_root}")
    print(f"  Docker Compose Files: docker-compose.yml + docker-compose.dev.yml")
    
    print("\n🐳 Running Services:")
    services = get_running_services()
    for service in services:
        print(f"  ✅ {service}")
    
    print("\n🧪 Test Commands:")
    print("  # Run all unit tests")
    print("  docker-compose exec app python -m pytest tests/unit")
    print("  ")
    print("  # Run with coverage")
    print("  docker-compose exec app python -m pytest tests/unit --cov=app --cov-report=html")
    print("  ")
    print("  # Use test scripts")
    print("  ./scripts/test.sh unit --html")
    print("  python scripts/test_runner.py --docker")
    
    print("\n📊 Coverage Reports:")
    print("  HTML Report: ./htmlcov/index.html")
    print("  XML Report: ./coverage.xml")
    
    print("\n" + "=" * 60)


def cleanup_environment() -> bool:
    """Clean up the Docker environment."""
    print_status("Cleaning up Docker environment...")
    
    project_root = get_project_root()
    
    # Stop services
    stop_cmd = ["docker-compose", "down"]
    result = run_command(stop_cmd, cwd=str(project_root))
    
    if result.returncode == 0:
        print_success("Docker environment cleaned up")
        return True
    else:
        print_error("Failed to clean up Docker environment")
        return False


def main():
    """Main setup function."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Setup Docker test environment for YouTube Download Service"
    )
    
    parser.add_argument("--clean", action="store_true", help="Clean up Docker environment")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing environment")
    parser.add_argument("--no-dev-compose", action="store_true", help="Don't use development compose file")
    
    args = parser.parse_args()
    
    # Handle cleanup
    if args.clean:
        success = cleanup_environment()
        sys.exit(0 if success else 1)
    
    print_status("Setting up Docker test environment...")
    
    # Step 1: Check Docker availability
    if not check_docker_availability():
        print_error("Docker is not available. Please install Docker and docker-compose.")
        sys.exit(1)
    
    # Step 2: Check if services are already running
    running_services = get_running_services()
    
    if not args.verify_only and ("app" not in running_services):
        # Step 3: Start Docker services
        if not start_docker_services(use_dev_compose=not args.no_dev_compose):
            print_error("Failed to start Docker services")
            sys.exit(1)
    
    # Step 4: Install development dependencies
    if not install_dev_dependencies():
        print_error("Failed to install development dependencies")
        sys.exit(1)
    
    # Step 5: Verify test file mounts
    if not verify_test_files_mounted():
        print_error("Test files not properly mounted")
        sys.exit(1)
    
    # Step 6: Run test verification
    if not run_test_verification():
        print_error("Test environment verification failed")
        sys.exit(1)
    
    # Step 7: Show environment information
    show_environment_info()
    
    print_success("Docker test environment is ready!")


if __name__ == "__main__":
    main()