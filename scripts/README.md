# Scripts Directory

This directory contains utility scripts for the YouTube Download Service project.

## Available Scripts

- ✅ `create_admin_key.py` - **IMPLEMENTED** - Create initial admin API key for authentication

## Planned Scripts (To Be Implemented)

- `setup_dev.py` - Development environment setup script (automate full environment setup)
- `seed_data.py` - Database seeding script for development testing
- `migration_helper.py` - Database migration utilities and helpers
- `deploy.sh` - Deployment automation and helper script
- `test_auth.py` - Test authentication system functionality

## Current Status

This directory is prepared for future utility scripts. Scripts will be added as needed during development and deployment phases.

## Usage

Run scripts from the project root directory:

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