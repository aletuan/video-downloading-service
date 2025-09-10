#!/usr/bin/env python3
"""
Initialize S3 Directory Structure for YouTube Cookie Management

This script sets up the proper directory structure and uploads template files
to the secure S3 bucket for cookie management.
"""

import boto3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any
import hashlib

class S3StructureInitializer:
    """Initialize S3 directory structure for cookie management."""
    
    def __init__(self, bucket_name: str, aws_region: str = 'us-east-1'):
        """
        Initialize the S3 structure initializer.
        
        Args:
            bucket_name: Name of the S3 bucket
            aws_region: AWS region for the bucket
        """
        self.bucket_name = bucket_name
        self.aws_region = aws_region
        self.s3_client = boto3.client('s3', region_name=aws_region)
        
        # Project root directory
        self.project_root = Path(__file__).parent.parent
        self.template_dir = self.project_root / 'config' / 'templates' / 's3-structure'
    
    def verify_bucket_exists(self) -> bool:
        """Verify that the S3 bucket exists and is accessible."""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            print(f"✓ Bucket '{self.bucket_name}' exists and is accessible")
            return True
        except Exception as e:
            print(f"✗ Error accessing bucket '{self.bucket_name}': {e}")
            return False
    
    def create_directory_structure(self) -> bool:
        """Create the directory structure in S3."""
        directories = [
            'cookies/',
            'cookies/archive/',
            'cookies/temp/'
        ]
        
        try:
            for directory in directories:
                # Create empty object to represent directory
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=directory,
                    Body='',
                    ServerSideEncryption='AES256',
                    Metadata={
                        'purpose': 'directory-marker',
                        'created-by': 'initialize-s3-structure',
                        'created-at': datetime.now(timezone.utc).isoformat()
                    }
                )
                print(f"✓ Created directory: {directory}")
            
            return True
        except Exception as e:
            print(f"✗ Error creating directory structure: {e}")
            return False
    
    def upload_template_files(self) -> bool:
        """Upload template files to S3."""
        template_files = {
            'youtube-cookies-active.txt': 'cookies/youtube-cookies-active.txt',
            'youtube-cookies-backup.txt': 'cookies/youtube-cookies-backup.txt',
            'metadata.json': 'cookies/metadata.json'
        }
        
        try:
            for template_file, s3_key in template_files.items():
                template_path = self.template_dir / template_file
                
                if not template_path.exists():
                    print(f"✗ Template file not found: {template_path}")
                    return False
                
                # Read template content
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Upload to S3 with encryption
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=content.encode('utf-8'),
                    ServerSideEncryption='AES256',
                    ContentType='text/plain' if template_file.endswith('.txt') else 'application/json',
                    Metadata={
                        'purpose': 'template-file',
                        'template-type': template_file.replace('.txt', '').replace('.json', ''),
                        'uploaded-by': 'initialize-s3-structure',
                        'uploaded-at': datetime.now(timezone.utc).isoformat(),
                        'file-hash': hashlib.sha256(content.encode('utf-8')).hexdigest()
                    }
                )
                print(f"✓ Uploaded template: {s3_key}")
            
            return True
        except Exception as e:
            print(f"✗ Error uploading template files: {e}")
            return False
    
    def update_metadata_with_structure_info(self) -> bool:
        """Update metadata.json with current structure information."""
        try:
            # Get the current metadata
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key='cookies/metadata.json'
            )
            metadata = json.loads(response['Body'].read().decode('utf-8'))
            
            # Update with current structure info
            current_time = datetime.now(timezone.utc).isoformat()
            metadata['cookie_metadata']['last_updated'] = current_time
            metadata['cookie_metadata']['initialized_at'] = current_time
            metadata['cookie_metadata']['structure_version'] = '1.0'
            
            # Update directory structure with actual S3 paths
            metadata['directory_structure']['bucket_name'] = self.bucket_name
            metadata['directory_structure']['region'] = self.aws_region
            metadata['directory_structure']['initialized'] = True
            
            # Upload updated metadata
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key='cookies/metadata.json',
                Body=json.dumps(metadata, indent=2).encode('utf-8'),
                ServerSideEncryption='AES256',
                ContentType='application/json',
                Metadata={
                    'purpose': 'cookie-metadata',
                    'updated-by': 'initialize-s3-structure',
                    'updated-at': current_time,
                    'structure-version': '1.0'
                }
            )
            print("✓ Updated metadata.json with structure information")
            return True
            
        except Exception as e:
            print(f"✗ Error updating metadata: {e}")
            return False
    
    def set_object_permissions(self) -> bool:
        """Set appropriate permissions on uploaded objects."""
        try:
            # Note: Object-level permissions are handled by bucket policy
            # This is a placeholder for any additional permission settings
            print("✓ Object permissions managed by bucket policy")
            return True
        except Exception as e:
            print(f"✗ Error setting object permissions: {e}")
            return False
    
    def verify_structure(self) -> bool:
        """Verify the created structure is correct."""
        expected_objects = [
            'cookies/',
            'cookies/archive/',
            'cookies/temp/',
            'cookies/youtube-cookies-active.txt',
            'cookies/youtube-cookies-backup.txt',
            'cookies/metadata.json'
        ]
        
        try:
            # List all objects in the cookies/ prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix='cookies/'
            )
            
            if 'Contents' not in response:
                print("✗ No objects found in cookies/ directory")
                return False
            
            existing_objects = [obj['Key'] for obj in response['Contents']]
            
            missing_objects = []
            for expected in expected_objects:
                if expected not in existing_objects:
                    missing_objects.append(expected)
            
            if missing_objects:
                print(f"✗ Missing objects: {missing_objects}")
                return False
            
            print("✓ All expected objects present in S3 structure")
            print(f"✓ Total objects created: {len(existing_objects)}")
            
            return True
        except Exception as e:
            print(f"✗ Error verifying structure: {e}")
            return False
    
    def initialize(self) -> bool:
        """Run the complete initialization process."""
        print(f"🚀 Initializing S3 structure for bucket: {self.bucket_name}")
        print("=" * 60)
        
        steps = [
            ("Verifying bucket access", self.verify_bucket_exists),
            ("Creating directory structure", self.create_directory_structure),
            ("Uploading template files", self.upload_template_files),
            ("Updating metadata", self.update_metadata_with_structure_info),
            ("Setting object permissions", self.set_object_permissions),
            ("Verifying structure", self.verify_structure)
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 {step_name}...")
            if not step_func():
                print(f"❌ Initialization failed at: {step_name}")
                return False
        
        print("\n" + "=" * 60)
        print("🎉 S3 structure initialization completed successfully!")
        print(f"📁 Bucket: {self.bucket_name}")
        print(f"🌍 Region: {self.aws_region}")
        print(f"🔐 Encryption: AES-256 enabled")
        print("📋 Next steps:")
        print("   1. Upload actual YouTube cookies using upload-cookies.py")
        print("   2. Test cookie authentication")
        print("   3. Configure monitoring and alerts")
        
        return True


def main():
    """Main function to run the S3 structure initializer."""
    if len(sys.argv) < 2:
        print("Usage: python initialize-s3-structure.py <bucket-name> [region]")
        print("Example: python initialize-s3-structure.py my-secure-config-bucket us-east-1")
        sys.exit(1)
    
    bucket_name = sys.argv[1]
    aws_region = sys.argv[2] if len(sys.argv) > 2 else 'us-east-1'
    
    # Initialize and run
    initializer = S3StructureInitializer(bucket_name, aws_region)
    
    if initializer.initialize():
        print(f"\n✅ Success: S3 structure initialized for {bucket_name}")
        sys.exit(0)
    else:
        print(f"\n❌ Failed: S3 structure initialization failed for {bucket_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()