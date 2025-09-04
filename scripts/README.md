# Scripts Directory

This directory contains utility scripts for the YouTube Download Service project.

## Scripts

- `test_runner.py` - Comprehensive test runner with Docker support and coverage reporting
- `test.sh` - Simple shell wrapper with Docker auto-detection for common test commands
- `setup_test_env.py` - Automated Docker test environment setup and verification script
- `setup_dev.py` - Development environment setup script  
- `seed_data.py` - Database seeding script for development
- `migration_helper.py` - Database migration utilities
- `deploy.sh` - Deployment helper script

## Test Scripts

### test.sh (Recommended)

Smart shell script with Docker auto-detection for common test operations:

```bash
# Run all tests (auto-detects Docker vs local environment)
./scripts/test.sh

# Run unit tests with HTML coverage
./scripts/test.sh unit --html

# Run integration tests  
./scripts/test.sh integration

# Run fast tests (exclude slow/external)
./scripts/test.sh fast --parallel

# Force Docker execution with setup
./scripts/test.sh unit --docker --setup

# Generate coverage report from existing data
./scripts/test.sh coverage

# Clean coverage data
./scripts/test.sh clean

# Watch for changes and re-run tests
./scripts/test.sh watch

# Show help with Docker integration info
./scripts/test.sh help
```

**Docker Integration**: The script automatically detects your environment:
- Uses Docker if available and no local pytest found
- Prefers Docker for development consistency
- Falls back to local execution when Docker unavailable

### test_runner.py (Advanced)

Comprehensive Python test runner with many options:

```bash
# Run all tests with coverage
python scripts/test_runner.py

# Run specific test directory
python scripts/test_runner.py tests/unit/models

# Run with specific markers
python scripts/test_runner.py --markers "unit"

# Run in parallel with HTML coverage
python scripts/test_runner.py --parallel --html

# Run failed tests first
python scripts/test_runner.py --failed-first

# Show all options
python scripts/test_runner.py --help
```

### setup_test_env.py (Docker Setup)

Automated Docker test environment setup and verification:

```bash
# One-time setup - configure Docker test environment
python scripts/setup_test_env.py

# Verify existing environment without changes
python scripts/setup_test_env.py --verify-only

# Clean up Docker test environment
python scripts/setup_test_env.py --clean

# Setup without development compose file
python scripts/setup_test_env.py --no-dev-compose
```

**What it does**:
- ✅ Checks Docker availability
- 🐳 Starts Docker services with development configuration
- 📦 Installs test dependencies in containers
- 🔍 Verifies test file mounts and pytest configuration
- 🧪 Runs test verification to ensure environment works
- 📊 Shows environment status and available commands

## Coverage Reports

The test scripts generate coverage reports in multiple formats:

- **Terminal**: Shows coverage percentage and missing lines
- **HTML**: Interactive report in `htmlcov/index.html`
- **XML**: Machine-readable report in `coverage.xml`

Coverage is configured to require 85% minimum coverage and will fail if not met.

## Usage

Run scripts from the project root directory:

```bash
python scripts/script_name.py
./scripts/script_name.sh
```