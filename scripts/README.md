# Scripts Directory

This directory contains utility scripts for the YouTube Download Service project.

## Available Scripts

- ✅ `create_admin_key.py` - **IMPLEMENTED** - Create initial admin API key for authentication
- ✅ `setup_dev.py` - **IMPLEMENTED** - Complete development environment setup with cleanup

## Planned Scripts (To Be Implemented)

- `seed_data.py` - Database seeding script for development testing
- `migration_helper.py` - Database migration utilities and helpers
- `deploy.sh` - Deployment automation and helper script
- `test_auth.py` - Test authentication system functionality

## Current Status

This directory is prepared for future utility scripts. Scripts will be added as needed during development and deployment phases.

## Usage

Run scripts from the project root directory:

### setup_dev.py

Complete development environment setup with optional cleanup:

```bash
# Basic setup (recommended for first time)
python scripts/setup_dev.py

# Full reset - clean everything and setup fresh
python scripts/setup_dev.py --clean-all

# Clean containers only (keeps Docker images for faster rebuilds)
python scripts/setup_dev.py --clean-containers

# Quick start without rebuilding (if containers already exist)
python scripts/setup_dev.py --no-build

# Setup without creating admin API key
python scripts/setup_dev.py --skip-key

# Custom admin key name
python scripts/setup_dev.py --admin-key-name "My Development Admin"

# Show all options
python scripts/setup_dev.py --help
```

### create_admin_key.py

Create an initial admin API key for authentication:

```bash
# Basic usage - create admin key with default settings
python scripts/create_admin_key.py

# Create key with custom name and description
python scripts/create_admin_key.py --name "Production Admin" --description "Main admin key"

# Create key that expires in 365 days
python scripts/create_admin_key.py --expires 365

# Run in Docker environment
python scripts/create_admin_key.py --docker

# Show help and all options
python scripts/create_admin_key.py --help
```

### General Script Usage

```bash
# Python scripts
python scripts/script_name.py

# Shell scripts  
bash scripts/script_name.sh
```

## Contributing

When adding new scripts:
1. Follow the project's coding standards
2. Include proper documentation and help messages
3. Update this README with script descriptions
4. Test scripts in both local and Docker environments