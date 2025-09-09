#!/usr/bin/env python3

"""
Cookie Upload Utility for YouTube Download Service

This script provides a secure interface for administrators to upload and manage
YouTube cookie files to the secure S3 storage backend.

Features:
- Secure cookie file validation and format verification
- Automatic encryption before S3 upload
- Backup management and rotation
- Metadata generation and tracking
- Upload success verification and health checks
- Comprehensive error handling and logging

Usage:
    python upload-cookies.py [OPTIONS] <cookie-file-path>

Examples:
    # Upload new cookies with automatic backup
    python upload-cookies.py cookies.txt
    
    # Upload with custom metadata
    python upload-cookies.py --source "Firefox" --description "Updated cookies" cookies.txt
    
    # Force upload without validation (dangerous)
    python upload-cookies.py --force cookies.txt
    
    # Test validation only (no upload)
    python upload-cookies.py --validate-only cookies.txt
"""

import os
import sys
import json
import argparse
import logging
import hashlib
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import boto3
import asyncio
import aiofiles
from cryptography.fernet import Fernet

# Add the app directory to the Python path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.core.config import settings
from app.core.cookie_manager import CookieManager


class CookieUploadError(Exception):
    """Custom exception for cookie upload errors."""
    pass


class CookieUploadUtility:
    """Secure cookie upload and management utility."""
    
    def __init__(self, bucket_name: Optional[str] = None, aws_region: Optional[str] = None):
        """Initialize the cookie upload utility."""
        self.bucket_name = bucket_name or settings.cookie_s3_bucket or os.getenv('COOKIE_S3_BUCKET')
        self.aws_region = aws_region or os.getenv('AWS_REGION', 'us-east-1')
        self.encryption_key = settings.cookie_encryption_key or os.getenv('COOKIE_ENCRYPTION_KEY')
        
        if not self.bucket_name:
            raise CookieUploadError("COOKIE_S3_BUCKET environment variable or bucket name required")
        
        if not self.encryption_key:
            raise CookieUploadError("COOKIE_ENCRYPTION_KEY environment variable required")
        
        # Initialize encryption
        self.cipher_suite = Fernet(self._derive_key(self.encryption_key))
        
        # Initialize AWS clients
        self.s3_client = boto3.client('s3', region_name=self.aws_region)
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    def _derive_key(self, password: str) -> bytes:
        """Derive a Fernet key from password using PBKDF2."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64
        
        # Use a fixed salt for consistency (in production, this should be more secure)
        salt = b"youtube_cookie_salt_v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def validate_cookie_file(self, file_path: Path, strict: bool = True) -> Dict[str, Any]:
        """
        Validate cookie file format and content.
        
        Args:
            file_path: Path to the cookie file
            strict: If True, perform strict validation
            
        Returns:
            Dictionary with validation results and metadata
        """
        validation_result = {
            'valid': False,
            'format': None,
            'cookie_count': 0,
            'domains': [],
            'expires_earliest': None,
            'expires_latest': None,
            'issues': [],
            'warnings': [],
            'file_size': 0,
            'checksum': None
        }
        
        try:
            if not file_path.exists():
                validation_result['issues'].append("File does not exist")
                return validation_result
            
            # Check file size
            file_size = file_path.stat().st_size
            validation_result['file_size'] = file_size
            
            if file_size == 0:
                validation_result['issues'].append("File is empty")
                return validation_result
            
            if file_size > 10 * 1024 * 1024:  # 10MB limit
                validation_result['issues'].append("File too large (>10MB)")
                return validation_result
            
            # Calculate file checksum
            with open(file_path, 'rb') as f:
                file_content = f.read()
                validation_result['checksum'] = hashlib.sha256(file_content).hexdigest()
            
            # Read and parse cookies
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Detect format
            if any(line.startswith('# Netscape HTTP Cookie File') for line in lines[:5]):
                validation_result['format'] = 'netscape'
                return self._validate_netscape_format(lines, validation_result, strict)
            elif lines and lines[0].strip().startswith('{'):
                validation_result['format'] = 'json'
                return self._validate_json_format(''.join(lines), validation_result, strict)
            else:
                validation_result['format'] = 'unknown'
                validation_result['issues'].append("Unknown cookie format")
                return validation_result
                
        except Exception as e:
            validation_result['issues'].append(f"Validation error: {str(e)}")
            return validation_result
    
    def _validate_netscape_format(self, lines: List[str], result: Dict[str, Any], strict: bool) -> Dict[str, Any]:
        """Validate Netscape HTTP Cookie File format."""
        domains = set()
        expires_times = []
        cookie_count = 0
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            
            # Parse cookie line: domain, domain_specified, path, secure, expires, name, value
            parts = line.split('\t')
            
            if len(parts) != 7:
                if strict:
                    result['issues'].append(f"Line {line_num}: Invalid format (expected 7 tab-separated values)")
                else:
                    result['warnings'].append(f"Line {line_num}: Invalid format")
                continue
            
            domain, domain_specified, path, secure, expires, name, value = parts
            
            # Validate domain
            if not domain:
                result['warnings'].append(f"Line {line_num}: Empty domain")
            else:
                domains.add(domain.lstrip('.'))
            
            # Validate expires
            try:
                expires_timestamp = int(expires)
                if expires_timestamp > 0:  # 0 means session cookie
                    expires_dt = datetime.fromtimestamp(expires_timestamp)
                    expires_times.append(expires_dt)
                    
                    # Check if cookie is expired
                    if expires_dt < datetime.now():
                        result['warnings'].append(f"Line {line_num}: Cookie expired on {expires_dt}")
            except ValueError:
                result['warnings'].append(f"Line {line_num}: Invalid expires timestamp")
            
            # Validate name
            if not name:
                result['warnings'].append(f"Line {line_num}: Empty cookie name")
            
            cookie_count += 1
        
        result['cookie_count'] = cookie_count
        result['domains'] = sorted(list(domains))
        
        if expires_times:
            result['expires_earliest'] = min(expires_times).isoformat()
            result['expires_latest'] = max(expires_times).isoformat()
        
        # Check for YouTube domains
        youtube_domains = [d for d in domains if 'youtube.com' in d or 'google.com' in d]
        if not youtube_domains:
            result['warnings'].append("No YouTube/Google domains found in cookies")
        
        # Validation passed if no critical issues
        result['valid'] = len(result['issues']) == 0 and cookie_count > 0
        
        return result
    
    def _validate_json_format(self, content: str, result: Dict[str, Any], strict: bool) -> Dict[str, Any]:
        """Validate JSON cookie format."""
        try:
            cookies = json.loads(content)
            
            if not isinstance(cookies, list):
                result['issues'].append("JSON format: Expected array of cookie objects")
                return result
            
            domains = set()
            expires_times = []
            
            for i, cookie in enumerate(cookies):
                if not isinstance(cookie, dict):
                    result['warnings'].append(f"Cookie {i}: Not a dictionary object")
                    continue
                
                # Check required fields
                required_fields = ['domain', 'name']
                for field in required_fields:
                    if field not in cookie:
                        result['warnings'].append(f"Cookie {i}: Missing required field '{field}'")
                
                if 'domain' in cookie:
                    domains.add(cookie['domain'].lstrip('.'))
                
                if 'expires' in cookie:
                    try:
                        # Handle different expires formats
                        expires = cookie['expires']
                        if isinstance(expires, (int, float)):
                            expires_dt = datetime.fromtimestamp(expires)
                        elif isinstance(expires, str):
                            expires_dt = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                        else:
                            continue
                        
                        expires_times.append(expires_dt)
                        
                        if expires_dt < datetime.now():
                            result['warnings'].append(f"Cookie {i}: Expired on {expires_dt}")
                    except (ValueError, TypeError):
                        result['warnings'].append(f"Cookie {i}: Invalid expires format")
            
            result['cookie_count'] = len(cookies)
            result['domains'] = sorted(list(domains))
            
            if expires_times:
                result['expires_earliest'] = min(expires_times).isoformat()
                result['expires_latest'] = max(expires_times).isoformat()
            
            # Check for YouTube domains
            youtube_domains = [d for d in domains if 'youtube.com' in d or 'google.com' in d]
            if not youtube_domains:
                result['warnings'].append("No YouTube/Google domains found in cookies")
            
            result['valid'] = len(result['issues']) == 0 and len(cookies) > 0
            
        except json.JSONDecodeError as e:
            result['issues'].append(f"JSON format error: {str(e)}")
        
        return result
    
    def create_metadata(self, file_path: Path, validation_result: Dict[str, Any], 
                       source: str = "Unknown", description: str = "") -> Dict[str, Any]:
        """Create comprehensive metadata for the cookie upload."""
        return {
            'upload_timestamp': datetime.utcnow().isoformat(),
            'original_filename': file_path.name,
            'file_size': validation_result['file_size'],
            'checksum': validation_result['checksum'],
            'format': validation_result['format'],
            'cookie_count': validation_result['cookie_count'],
            'domains': validation_result['domains'],
            'expires_earliest': validation_result['expires_earliest'],
            'expires_latest': validation_result['expires_latest'],
            'source': source,
            'description': description,
            'uploader': os.getenv('USER', 'unknown'),
            'validation_passed': validation_result['valid'],
            'validation_warnings': validation_result['warnings'],
            'validation_issues': validation_result['issues'],
            'version': '1.0'
        }
    
    async def backup_existing_cookies(self) -> bool:
        """Create backup of existing active cookies before upload."""
        try:
            # Check if active cookies exist
            try:
                response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key='cookies/youtube-cookies-active.txt'
                )
            except self.s3_client.exceptions.NoSuchKey:
                self.logger.info("No existing active cookies to backup")
                return True
            
            # Create backup filename with timestamp
            backup_key = f"cookies/backups/youtube-cookies-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.txt"
            
            # Copy existing active cookies to backup location
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource={'Bucket': self.bucket_name, 'Key': 'cookies/youtube-cookies-active.txt'},
                Key=backup_key
            )
            
            self.logger.info(f"Created backup: {backup_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to backup existing cookies: {str(e)}")
            return False
    
    async def upload_cookies(self, file_path: Path, metadata: Dict[str, Any], 
                           create_backup: bool = True) -> bool:
        """Upload encrypted cookies to S3 with metadata."""
        try:
            # Create backup if requested
            if create_backup:
                if not await self.backup_existing_cookies():
                    self.logger.warning("Backup failed, but continuing with upload")
            
            # Read and encrypt cookie file
            with open(file_path, 'rb') as f:
                cookie_content = f.read()
            
            encrypted_content = self.cipher_suite.encrypt(cookie_content)
            
            # Upload encrypted cookies as active
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key='cookies/youtube-cookies-active.txt',
                Body=encrypted_content,
                ContentType='application/octet-stream',
                ServerSideEncryption='AES256',
                Metadata={
                    'uploaded-by': metadata['uploader'],
                    'upload-timestamp': metadata['upload_timestamp'],
                    'original-filename': metadata['original_filename'],
                    'checksum': metadata['checksum']
                }
            )
            
            # Upload metadata
            metadata_json = json.dumps(metadata, indent=2)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key='cookies/metadata.json',
                Body=metadata_json.encode(),
                ContentType='application/json',
                ServerSideEncryption='AES256'
            )
            
            self.logger.info("Successfully uploaded cookies and metadata")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to upload cookies: {str(e)}")
            return False
    
    async def verify_upload(self) -> Dict[str, Any]:
        """Verify the uploaded cookies can be retrieved and decrypted."""
        verification_result = {
            'success': False,
            'active_cookies_present': False,
            'metadata_present': False,
            'decryption_successful': False,
            'cookie_count': 0,
            'error': None
        }
        
        try:
            # Check if active cookies exist
            try:
                cookie_response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key='cookies/youtube-cookies-active.txt'
                )
                verification_result['active_cookies_present'] = True
                
                # Test decryption
                encrypted_content = cookie_response['Body'].read()
                decrypted_content = self.cipher_suite.decrypt(encrypted_content)
                verification_result['decryption_successful'] = True
                
                # Count cookies (rough estimate)
                content_str = decrypted_content.decode('utf-8', errors='ignore')
                if content_str.strip().startswith('['):
                    # JSON format
                    try:
                        cookies = json.loads(content_str)
                        verification_result['cookie_count'] = len(cookies)
                    except:
                        pass
                else:
                    # Netscape format - count non-comment lines
                    lines = [line for line in content_str.split('\n') 
                            if line.strip() and not line.strip().startswith('#')]
                    verification_result['cookie_count'] = len(lines)
                
            except self.s3_client.exceptions.NoSuchKey:
                verification_result['error'] = "Active cookies file not found"
                return verification_result
            
            # Check if metadata exists
            try:
                metadata_response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key='cookies/metadata.json'
                )
                verification_result['metadata_present'] = True
            except self.s3_client.exceptions.NoSuchKey:
                verification_result['error'] = "Metadata file not found"
            
            verification_result['success'] = (
                verification_result['active_cookies_present'] and
                verification_result['metadata_present'] and
                verification_result['decryption_successful'] and
                verification_result['cookie_count'] > 0
            )
            
        except Exception as e:
            verification_result['error'] = str(e)
        
        return verification_result
    
    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """Clean up old backup files, keeping only the most recent ones."""
        try:
            # List all backup files
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix='cookies/backups/'
            )
            
            if 'Contents' not in response:
                return 0
            
            # Sort by last modified (newest first)
            backups = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
            
            # Delete old backups beyond keep_count
            deleted_count = 0
            for backup in backups[keep_count:]:
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=backup['Key']
                )
                deleted_count += 1
                self.logger.info(f"Deleted old backup: {backup['Key']}")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old backups: {str(e)}")
            return 0
    
    def list_existing_cookies(self) -> Dict[str, Any]:
        """List information about existing cookies in S3."""
        info = {
            'active_cookies': None,
            'metadata': None,
            'backups': [],
            'total_backups': 0
        }
        
        try:
            # Check active cookies
            try:
                response = self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key='cookies/youtube-cookies-active.txt'
                )
                info['active_cookies'] = {
                    'last_modified': response['LastModified'].isoformat(),
                    'size': response['ContentLength'],
                    'metadata': response.get('Metadata', {})
                }
            except self.s3_client.exceptions.NoSuchKey:
                pass
            
            # Check metadata
            try:
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key='cookies/metadata.json'
                )
                content = response['Body'].read().decode()
                info['metadata'] = json.loads(content)
            except (self.s3_client.exceptions.NoSuchKey, json.JSONDecodeError):
                pass
            
            # List backups
            try:
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix='cookies/backups/'
                )
                
                if 'Contents' in response:
                    backups = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
                    info['backups'] = [
                        {
                            'key': backup['Key'],
                            'last_modified': backup['LastModified'].isoformat(),
                            'size': backup['Size']
                        }
                        for backup in backups[:5]  # Show only 5 most recent
                    ]
                    info['total_backups'] = len(backups)
            except Exception:
                pass
        
        except Exception as e:
            self.logger.error(f"Failed to list existing cookies: {str(e)}")
        
        return info


async def main():
    """Main entry point for the cookie upload utility."""
    parser = argparse.ArgumentParser(
        description="Secure Cookie Upload Utility for YouTube Download Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s cookies.txt
  %(prog)s --source "Firefox" --description "Updated cookies" cookies.txt
  %(prog)s --validate-only cookies.txt
  %(prog)s --list-existing
        """
    )
    
    parser.add_argument('cookie_file', nargs='?', help='Path to cookie file to upload')
    parser.add_argument('--source', default='Unknown', help='Source of the cookies (e.g., Firefox, Chrome)')
    parser.add_argument('--description', default='', help='Description of the cookie update')
    parser.add_argument('--force', action='store_true', help='Force upload without validation')
    parser.add_argument('--validate-only', action='store_true', help='Only validate, do not upload')
    parser.add_argument('--no-backup', action='store_true', help='Do not create backup of existing cookies')
    parser.add_argument('--list-existing', action='store_true', help='List existing cookies and exit')
    parser.add_argument('--cleanup-backups', type=int, metavar='N', help='Keep only N most recent backups')
    parser.add_argument('--bucket', help='S3 bucket name (overrides environment variable)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize utility
        utility = CookieUploadUtility(bucket_name=args.bucket)
        
        # Handle list existing cookies
        if args.list_existing:
            print("Existing Cookies Information:")
            print("=" * 50)
            
            info = utility.list_existing_cookies()
            
            if info['active_cookies']:
                print(f"Active Cookies:")
                print(f"  Last Modified: {info['active_cookies']['last_modified']}")
                print(f"  Size: {info['active_cookies']['size']} bytes")
                print()
            else:
                print("No active cookies found")
                print()
            
            if info['metadata']:
                print("Metadata:")
                print(f"  Upload Date: {info['metadata'].get('upload_timestamp', 'Unknown')}")
                print(f"  Cookie Count: {info['metadata'].get('cookie_count', 'Unknown')}")
                print(f"  Source: {info['metadata'].get('source', 'Unknown')}")
                print(f"  Uploader: {info['metadata'].get('uploader', 'Unknown')}")
                print()
            
            if info['backups']:
                print(f"Recent Backups ({len(info['backups'])} of {info['total_backups']}):")
                for backup in info['backups']:
                    print(f"  {backup['key']} - {backup['last_modified']} ({backup['size']} bytes)")
                print()
            
            return 0
        
        # Handle cleanup backups
        if args.cleanup_backups is not None:
            deleted = utility.cleanup_old_backups(args.cleanup_backups)
            print(f"Cleaned up {deleted} old backup files")
            return 0
        
        # Require cookie file for other operations
        if not args.cookie_file:
            parser.error("Cookie file is required unless using --list-existing or --cleanup-backups")
        
        cookie_file = Path(args.cookie_file)
        
        # Validate cookie file
        print(f"Validating cookie file: {cookie_file}")
        validation_result = utility.validate_cookie_file(cookie_file, strict=not args.force)
        
        print(f"Validation Results:")
        print(f"  Format: {validation_result['format']}")
        print(f"  Valid: {validation_result['valid']}")
        print(f"  Cookie Count: {validation_result['cookie_count']}")
        print(f"  File Size: {validation_result['file_size']} bytes")
        print(f"  Domains: {', '.join(validation_result['domains'][:5])}" + 
              (f" ... (+{len(validation_result['domains'])-5} more)" if len(validation_result['domains']) > 5 else ""))
        
        if validation_result['issues']:
            print(f"  Issues: {len(validation_result['issues'])}")
            for issue in validation_result['issues']:
                print(f"    - {issue}")
        
        if validation_result['warnings']:
            print(f"  Warnings: {len(validation_result['warnings'])}")
            for warning in validation_result['warnings'][:3]:  # Show first 3
                print(f"    - {warning}")
            if len(validation_result['warnings']) > 3:
                print(f"    ... and {len(validation_result['warnings'])-3} more warnings")
        
        print()
        
        if not validation_result['valid'] and not args.force:
            print("❌ Cookie file validation failed. Use --force to upload anyway.")
            return 1
        
        if args.validate_only:
            print("✅ Validation completed (upload skipped)")
            return 0
        
        # Create metadata
        metadata = utility.create_metadata(cookie_file, validation_result, args.source, args.description)
        
        # Upload cookies
        print("Uploading cookies...")
        success = await utility.upload_cookies(cookie_file, metadata, create_backup=not args.no_backup)
        
        if not success:
            print("❌ Cookie upload failed")
            return 1
        
        # Verify upload
        print("Verifying upload...")
        verification = await utility.verify_upload()
        
        print(f"Upload Verification:")
        print(f"  Success: {verification['success']}")
        print(f"  Active Cookies Present: {verification['active_cookies_present']}")
        print(f"  Metadata Present: {verification['metadata_present']}")
        print(f"  Decryption Successful: {verification['decryption_successful']}")
        print(f"  Cookie Count: {verification['cookie_count']}")
        
        if verification['error']:
            print(f"  Error: {verification['error']}")
        
        if verification['success']:
            print("✅ Cookie upload completed successfully!")
            
            # Cleanup old backups (keep 10 most recent)
            deleted = utility.cleanup_old_backups(10)
            if deleted > 0:
                print(f"🧹 Cleaned up {deleted} old backup files")
            
            return 0
        else:
            print("❌ Upload verification failed")
            return 1
    
    except CookieUploadError as e:
        print(f"❌ Cookie Upload Error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⚠️ Upload cancelled by user")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))