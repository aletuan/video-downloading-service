"""
Unit tests for S3 integration functionality.

This module tests S3 operations including bucket access, file upload/download,
encryption, error handling, and various AWS-specific scenarios.
"""

import pytest
import boto3
import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from moto import mock_s3, mock_kms
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
from pathlib import Path

from app.core.cookie_manager import CookieManager


class TestS3Integration:
    """Test suite for S3 integration functionality."""
    
    @pytest.fixture
    def aws_credentials(self, mock_cookie_settings):
        """Mocked AWS Credentials for moto."""
        import os
        os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
        os.environ['AWS_SECURITY_TOKEN'] = 'testing'
        os.environ['AWS_SESSION_TOKEN'] = 'testing'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    
    @pytest.fixture
    def sample_cookie_content(self):
        """Sample cookie file content for testing."""
        return """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tFALSE\t1735689600\tVISITOR_INFO1_LIVE\tabc123
.google.com\tTRUE\t/\tFALSE\t1735689600\tAUTH_TOKEN\tdef456
"""
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample cookie metadata for testing."""
        return {
            "upload_date": datetime.now().isoformat(),
            "expiry_date": (datetime.now() + timedelta(days=30)).isoformat(),
            "cookie_count": 2,
            "domains": [".youtube.com", ".google.com"],
            "format": "netscape",
            "source": "manual_upload",
            "version": "1.0"
        }
    
    @mock_s3
    def test_s3_bucket_creation_and_access(self, aws_credentials):
        """Test S3 bucket creation and basic access."""
        # Create S3 client and bucket
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        
        # Create bucket
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Verify bucket exists
        buckets = s3_client.list_buckets()['Buckets']
        bucket_names = [bucket['Name'] for bucket in buckets]
        assert bucket_name in bucket_names
        
        # Test bucket access
        response = s3_client.head_bucket(Bucket=bucket_name)
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200
    
    @mock_s3
    def test_s3_file_upload_download_operations(self, aws_credentials, sample_cookie_content):
        """Test basic S3 file upload and download operations."""
        # Setup S3 client and bucket
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Test file upload
        key = 'cookies/test-cookies.txt'
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=sample_cookie_content,
            ServerSideEncryption='AES256'
        )
        
        # Verify file exists
        objects = s3_client.list_objects_v2(Bucket=bucket_name)
        assert 'Contents' in objects
        assert any(obj['Key'] == key for obj in objects['Contents'])
        
        # Test file download
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        downloaded_content = response['Body'].read().decode('utf-8')
        assert downloaded_content == sample_cookie_content
        
        # Verify encryption
        assert response['ServerSideEncryption'] == 'AES256'
    
    @mock_s3
    def test_s3_metadata_operations(self, aws_credentials, sample_metadata):
        """Test S3 metadata upload and retrieval operations."""
        # Setup S3 client and bucket
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Upload metadata as JSON
        metadata_key = 'cookies/metadata.json'
        metadata_json = json.dumps(sample_metadata, indent=2)
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=metadata_key,
            Body=metadata_json,
            ContentType='application/json',
            ServerSideEncryption='AES256'
        )
        
        # Download and verify metadata
        response = s3_client.get_object(Bucket=bucket_name, Key=metadata_key)
        downloaded_metadata = json.loads(response['Body'].read().decode('utf-8'))
        
        assert downloaded_metadata == sample_metadata
        assert response['ContentType'] == 'application/json'
        assert response['ServerSideEncryption'] == 'AES256'
    
    @mock_s3
    def test_s3_versioning_functionality(self, aws_credentials, sample_cookie_content):
        """Test S3 versioning for cookie file history."""
        # Setup S3 client and bucket with versioning
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Enable versioning
        s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        
        # Upload multiple versions of the same file
        key = 'cookies/active-cookies.txt'
        
        # Version 1
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=sample_cookie_content,
            ServerSideEncryption='AES256'
        )
        
        # Version 2 (modified content)
        modified_content = sample_cookie_content + "\n.googleapis.com\tTRUE\t/\tFALSE\t1735689600\tAPI_KEY\tghi789"
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=modified_content,
            ServerSideEncryption='AES256'
        )
        
        # List versions
        versions = s3_client.list_object_versions(Bucket=bucket_name, Prefix=key)
        assert 'Versions' in versions
        assert len(versions['Versions']) == 2
        
        # Download latest version
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        latest_content = response['Body'].read().decode('utf-8')
        assert latest_content == modified_content
        
        # Download specific version
        version_id = versions['Versions'][1]['VersionId']  # Older version
        response = s3_client.get_object(Bucket=bucket_name, Key=key, VersionId=version_id)
        version_content = response['Body'].read().decode('utf-8')
        assert version_content == sample_cookie_content
    
    @mock_s3
    def test_s3_error_handling_scenarios(self, aws_credentials):
        """Test various S3 error scenarios and handling."""
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        
        # Test accessing non-existent bucket
        with pytest.raises(ClientError) as exc_info:
            s3_client.get_object(Bucket=bucket_name, Key='cookies/test.txt')
        assert exc_info.value.response['Error']['Code'] == 'NoSuchBucket'
        
        # Create bucket for remaining tests
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Test accessing non-existent object
        with pytest.raises(ClientError) as exc_info:
            s3_client.get_object(Bucket=bucket_name, Key='cookies/nonexistent.txt')
        assert exc_info.value.response['Error']['Code'] == 'NoSuchKey'
        
        # Test invalid bucket operations
        with pytest.raises(ClientError) as exc_info:
            s3_client.create_bucket(Bucket='invalid..bucket..name')
        assert exc_info.value.response['Error']['Code'] == 'InvalidBucketName'
    
    @mock_s3
    def test_s3_large_file_handling(self, aws_credentials):
        """Test handling of large cookie files."""
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Generate large cookie content (10MB+)
        large_cookie_content = "# Netscape HTTP Cookie File\n"
        for i in range(50000):  # ~10MB of cookie data
            large_cookie_content += f".domain{i}.com\tTRUE\t/\tFALSE\t1735689600\tCOOKIE{i}\tvalue{'x' * 100}\n"
        
        # Upload large file
        key = 'cookies/large-cookies.txt'
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=large_cookie_content,
            ServerSideEncryption='AES256'
        )
        
        # Verify upload
        response = s3_client.head_object(Bucket=bucket_name, Key=key)
        assert response['ContentLength'] > 10 * 1024 * 1024  # > 10MB
        
        # Download and verify (streaming)
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        downloaded_size = 0
        for chunk in response['Body'].iter_chunks(chunk_size=1024):
            downloaded_size += len(chunk)
        
        assert downloaded_size == len(large_cookie_content.encode('utf-8'))
    
    @mock_s3
    @mock_kms
    def test_s3_kms_encryption_integration(self, aws_credentials, sample_cookie_content):
        """Test S3 integration with KMS encryption."""
        # Setup KMS client and create key
        kms_client = boto3.client('kms', region_name='us-east-1')
        key_response = kms_client.create_key(
            Description='Test key for cookie encryption',
            Usage='ENCRYPT_DECRYPT'
        )
        key_id = key_response['KeyMetadata']['KeyId']
        
        # Setup S3 client and bucket
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Upload with KMS encryption
        key = 'cookies/kms-encrypted-cookies.txt'
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=sample_cookie_content,
            ServerSideEncryption='aws:kms',
            SSEKMSKeyId=key_id
        )
        
        # Verify KMS encryption
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        assert response['ServerSideEncryption'] == 'aws:kms'
        assert response['SSEKMSKeyId'] == key_id
        
        # Verify content integrity
        downloaded_content = response['Body'].read().decode('utf-8')
        assert downloaded_content == sample_cookie_content
    
    @mock_s3
    def test_s3_lifecycle_policies_simulation(self, aws_credentials, sample_cookie_content):
        """Test S3 lifecycle policies for cookie file management."""
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Set up lifecycle policy
        lifecycle_config = {
            'Rules': [
                {
                    'ID': 'CookieBackupTransition',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': 'cookies/backup/'},
                    'Transitions': [
                        {
                            'Days': 30,
                            'StorageClass': 'STANDARD_IA'
                        },
                        {
                            'Days': 90,
                            'StorageClass': 'GLACIER'
                        }
                    ]
                },
                {
                    'ID': 'CookieHistoryExpiration',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': 'cookies/history/'},
                    'Expiration': {'Days': 365}
                }
            ]
        }
        
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_config
        )
        
        # Verify lifecycle policy
        response = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        assert len(response['Rules']) == 2
        assert response['Rules'][0]['ID'] == 'CookieBackupTransition'
        assert response['Rules'][1]['ID'] == 'CookieHistoryExpiration'
        
        # Upload test files to different prefixes
        prefixes = ['cookies/backup/', 'cookies/history/', 'cookies/active/']
        for prefix in prefixes:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'{prefix}test-cookies.txt',
                Body=sample_cookie_content,
                ServerSideEncryption='AES256'
            )
        
        # Verify files exist
        for prefix in prefixes:
            response = s3_client.get_object(Bucket=bucket_name, Key=f'{prefix}test-cookies.txt')
            assert response['Body'].read().decode('utf-8') == sample_cookie_content
    
    @mock_s3
    def test_s3_concurrent_access_patterns(self, aws_credentials, sample_cookie_content):
        """Test concurrent S3 access patterns for cookie management."""
        import threading
        import time
        
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Results tracking
        results = {'uploads': 0, 'downloads': 0, 'errors': 0}
        results_lock = threading.Lock()
        
        def upload_worker(worker_id):
            """Worker function for concurrent uploads."""
            try:
                key = f'cookies/worker-{worker_id}-cookies.txt'
                content = f"# Worker {worker_id} cookies\n{sample_cookie_content}"
                
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=key,
                    Body=content,
                    ServerSideEncryption='AES256'
                )
                
                with results_lock:
                    results['uploads'] += 1
                    
            except Exception:
                with results_lock:
                    results['errors'] += 1
        
        def download_worker(worker_id):
            """Worker function for concurrent downloads."""
            try:
                # Wait a bit for uploads to complete
                time.sleep(0.1)
                
                key = f'cookies/worker-{worker_id}-cookies.txt'
                response = s3_client.get_object(Bucket=bucket_name, Key=key)
                content = response['Body'].read().decode('utf-8')
                
                assert f"# Worker {worker_id} cookies" in content
                
                with results_lock:
                    results['downloads'] += 1
                    
            except Exception:
                with results_lock:
                    results['errors'] += 1
        
        # Create and start threads
        threads = []
        num_workers = 5
        
        # Upload threads
        for i in range(num_workers):
            thread = threading.Thread(target=upload_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Download threads
        for i in range(num_workers):
            thread = threading.Thread(target=download_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify results
        assert results['uploads'] == num_workers
        assert results['downloads'] == num_workers
        assert results['errors'] == 0
    
    @mock_s3
    def test_cookie_manager_s3_integration(self, aws_credentials, sample_cookie_content):
        """Test CookieManager integration with S3 operations."""
        # Setup S3 bucket
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Upload test cookie file
        s3_client.put_object(
            Bucket=bucket_name,
            Key='cookies/youtube-cookies-active.txt',
            Body=sample_cookie_content,
            ServerSideEncryption='AES256'
        )
        
        # Create CookieManager instance
        with patch('app.core.cookie_manager.boto3.client') as mock_boto:
            mock_boto.return_value = s3_client
            
            cookie_manager = CookieManager(
                bucket_name=bucket_name,
                encryption_key="test-key-1234567890123456789012345678"
            )
            
            # Test cookie retrieval through manager
            result = cookie_manager._download_cookies_from_s3('cookies/youtube-cookies-active.txt')
            
            assert result is not None
            assert isinstance(result, bytes)
            
            # Decrypt and verify content
            decrypted_content = cookie_manager._decrypt_cookie_data(result)
            assert decrypted_content == sample_cookie_content
    
    def test_s3_credentials_error_handling(self):
        """Test S3 operations with missing or invalid credentials."""
        # Clear AWS credentials
        import os
        for key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN']:
            if key in os.environ:
                del os.environ[key]
        
        # Test credential errors
        with pytest.raises((NoCredentialsError, ClientError)):
            s3_client = boto3.client('s3')
            s3_client.list_buckets()
    
    @mock_s3
    def test_s3_performance_benchmarks(self, aws_credentials, sample_cookie_content):
        """Test S3 performance benchmarks for cookie operations."""
        import time
        
        s3_client = boto3.client('s3', region_name='us-east-1')
        bucket_name = 'test-cookie-bucket'
        s3_client.create_bucket(Bucket=bucket_name)
        
        # Benchmark upload performance
        upload_times = []
        for i in range(10):
            start_time = time.time()
            
            s3_client.put_object(
                Bucket=bucket_name,
                Key=f'cookies/benchmark-{i}.txt',
                Body=sample_cookie_content,
                ServerSideEncryption='AES256'
            )
            
            upload_times.append(time.time() - start_time)
        
        # Benchmark download performance
        download_times = []
        for i in range(10):
            start_time = time.time()
            
            response = s3_client.get_object(Bucket=bucket_name, Key=f'cookies/benchmark-{i}.txt')
            content = response['Body'].read()
            
            download_times.append(time.time() - start_time)
        
        # Performance assertions (generous limits for testing)
        avg_upload_time = sum(upload_times) / len(upload_times)
        avg_download_time = sum(download_times) / len(download_times)
        
        assert avg_upload_time < 1.0  # Average upload under 1 second
        assert avg_download_time < 1.0  # Average download under 1 second
        
        # Verify content integrity
        for i in range(10):
            response = s3_client.get_object(Bucket=bucket_name, Key=f'cookies/benchmark-{i}.txt')
            content = response['Body'].read().decode('utf-8')
            assert content == sample_cookie_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])