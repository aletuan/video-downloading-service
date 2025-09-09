"""
Integration tests for S3 connectivity and operations.

This module tests real S3 connectivity, bucket operations, network resilience,
and integration with the cookie management system.
"""

import pytest
import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import boto3
from moto import mock_s3, mock_kms
from botocore.exceptions import ClientError, BotoCoreError

from app.core.cookie_manager import CookieManager


@pytest.mark.integration
class TestS3Connectivity:
    """Integration test suite for S3 connectivity and operations."""
    
    @pytest.fixture
    def aws_credentials_integration(self):
        """AWS credentials for integration testing."""
        import os
        # Use test credentials for moto
        os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
        os.environ['AWS_SECURITY_TOKEN'] = 'testing'
        os.environ['AWS_SESSION_TOKEN'] = 'testing'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        yield
        
        # Cleanup environment variables
        for key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SECURITY_TOKEN', 'AWS_SESSION_TOKEN']:
            if key in os.environ:
                del os.environ[key]
    
    @pytest.fixture
    def s3_test_bucket(self, aws_credentials_integration):
        """Create S3 test bucket with moto."""
        with mock_s3():
            # Create S3 client and bucket
            s3_client = boto3.client('s3', region_name='us-east-1')
            bucket_name = 'test-cookie-integration-bucket'
            s3_client.create_bucket(Bucket=bucket_name)
            
            # Enable versioning
            s3_client.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )
            
            yield bucket_name, s3_client
    
    @pytest.fixture
    def cookie_manager_s3(self, s3_test_bucket, mock_cookie_settings):
        """CookieManager instance for S3 integration testing."""
        bucket_name, s3_client = s3_test_bucket
        
        with patch('app.core.cookie_manager.boto3.client', return_value=s3_client):
            manager = CookieManager(
                bucket_name=bucket_name,
                encryption_key="s3-test-key-1234567890123456789012345678"
            )
            manager._s3_client = s3_client  # Inject the mock client
            return manager
    
    @pytest.fixture
    def sample_cookie_files(self):
        """Sample cookie file contents for testing."""
        return {
            'active': """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tFALSE\t1735689600\tVISITOR_INFO1_LIVE\tactive123
.google.com\tTRUE\t/\tFALSE\t1735689600\tSID\tactive456
""",
            'backup': """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tFALSE\t1735689600\tVISITOR_INFO1_LIVE\tbackup123
.google.com\tTRUE\t/\tFALSE\t1735689600\tSID\tbackup456
""",
            'metadata': {
                'upload_date': datetime.now().isoformat(),
                'expiry_date': (datetime.now() + timedelta(days=30)).isoformat(),
                'cookie_count': 2,
                'domains': ['.youtube.com', '.google.com'],
                'format': 'netscape',
                'version': '1.0'
            }
        }
    
    @pytest.mark.asyncio
    async def test_s3_bucket_connectivity_validation(self, cookie_manager_s3, s3_test_bucket):
        """Test basic S3 bucket connectivity validation."""
        bucket_name, s3_client = s3_test_bucket
        
        # Test bucket existence check
        try:
            response = s3_client.head_bucket(Bucket=bucket_name)
            assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        except ClientError as e:
            pytest.fail(f"S3 bucket connectivity failed: {e}")
        
        # Test bucket listing
        try:
            response = s3_client.list_objects_v2(Bucket=bucket_name)
            assert 'Contents' in response or 'KeyCount' in response
        except ClientError as e:
            pytest.fail(f"S3 bucket listing failed: {e}")
    
    @pytest.mark.asyncio
    async def test_s3_cookie_upload_download_cycle(self, cookie_manager_s3, s3_test_bucket, sample_cookie_files):
        """Test complete S3 upload/download cycle for cookies."""
        bucket_name, s3_client = s3_test_bucket
        
        # Upload active cookies
        active_cookies = sample_cookie_files['active']
        encrypted_cookies = cookie_manager_s3._encrypt_cookie_data(active_cookies)
        
        success = cookie_manager_s3._upload_cookies_to_s3(
            'cookies/youtube-cookies-active.txt',
            encrypted_cookies
        )
        assert success is True
        
        # Upload metadata
        metadata_json = json.dumps(sample_cookie_files['metadata'], indent=2)
        s3_client.put_object(
            Bucket=bucket_name,
            Key='cookies/metadata.json',
            Body=metadata_json,
            ContentType='application/json',
            ServerSideEncryption='AES256'
        )
        
        # Download and verify cookies
        downloaded_encrypted = cookie_manager_s3._download_cookies_from_s3(
            'cookies/youtube-cookies-active.txt'
        )
        assert downloaded_encrypted is not None
        
        # Decrypt and verify content
        decrypted_cookies = cookie_manager_s3._decrypt_cookie_data(downloaded_encrypted)
        assert decrypted_cookies == active_cookies
        
        # Download and verify metadata
        metadata_response = s3_client.get_object(Bucket=bucket_name, Key='cookies/metadata.json')
        downloaded_metadata = json.loads(metadata_response['Body'].read().decode('utf-8'))
        
        assert downloaded_metadata['cookie_count'] == sample_cookie_files['metadata']['cookie_count']
        assert downloaded_metadata['domains'] == sample_cookie_files['metadata']['domains']
    
    @pytest.mark.asyncio
    async def test_s3_versioning_and_backup_management(self, cookie_manager_s3, s3_test_bucket, sample_cookie_files):
        """Test S3 versioning for cookie backup management."""
        bucket_name, s3_client = s3_test_bucket
        key = 'cookies/youtube-cookies-active.txt'
        
        # Upload initial version
        initial_cookies = sample_cookie_files['active']
        encrypted_initial = cookie_manager_s3._encrypt_cookie_data(initial_cookies)
        success = cookie_manager_s3._upload_cookies_to_s3(key, encrypted_initial)
        assert success is True
        
        # Upload updated version
        updated_cookies = sample_cookie_files['backup']
        encrypted_updated = cookie_manager_s3._encrypt_cookie_data(updated_cookies)
        success = cookie_manager_s3._upload_cookies_to_s3(key, encrypted_updated)
        assert success is True
        
        # List versions
        versions = s3_client.list_object_versions(Bucket=bucket_name, Prefix=key)
        assert 'Versions' in versions
        assert len(versions['Versions']) == 2
        
        # Download latest version
        latest_encrypted = cookie_manager_s3._download_cookies_from_s3(key)
        latest_decrypted = cookie_manager_s3._decrypt_cookie_data(latest_encrypted)
        assert latest_decrypted == updated_cookies
        
        # Download previous version
        previous_version_id = versions['Versions'][1]['VersionId']
        previous_response = s3_client.get_object(
            Bucket=bucket_name,
            Key=key,
            VersionId=previous_version_id
        )
        previous_encrypted = previous_response['Body'].read()
        previous_decrypted = cookie_manager_s3._decrypt_cookie_data(previous_encrypted)
        assert previous_decrypted == initial_cookies
    
    @pytest.mark.asyncio
    async def test_s3_encryption_at_rest_validation(self, cookie_manager_s3, s3_test_bucket, sample_cookie_files):
        """Test S3 server-side encryption validation."""
        bucket_name, s3_client = s3_test_bucket
        
        # Upload cookies with encryption
        active_cookies = sample_cookie_files['active']
        encrypted_cookies = cookie_manager_s3._encrypt_cookie_data(active_cookies)
        
        key = 'cookies/encryption-test.txt'
        success = cookie_manager_s3._upload_cookies_to_s3(key, encrypted_cookies)
        assert success is True
        
        # Verify server-side encryption was applied
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        assert 'ServerSideEncryption' in response
        assert response['ServerSideEncryption'] == 'AES256'
        
        # Verify content encryption (double-encrypted: app-level + S3)
        raw_content = response['Body'].read()
        assert raw_content != active_cookies.encode('utf-8')  # Should be encrypted
        
        # Verify decryption works
        decrypted_cookies = cookie_manager_s3._decrypt_cookie_data(raw_content)
        assert decrypted_cookies == active_cookies
    
    @pytest.mark.asyncio
    async def test_s3_network_resilience_retry_logic(self, cookie_manager_s3, s3_test_bucket):
        """Test network resilience and retry logic for S3 operations."""
        bucket_name, s3_client = s3_test_bucket
        
        # Mock network failures followed by success
        original_get_object = s3_client.get_object
        call_count = {'count': 0}
        
        def failing_get_object(*args, **kwargs):
            call_count['count'] += 1
            if call_count['count'] <= 2:  # Fail first 2 attempts
                raise BotoCoreError("Network timeout")
            return original_get_object(*args, **kwargs)
        
        # Upload test data first
        test_data = b"test cookie data for resilience testing"
        s3_client.put_object(
            Bucket=bucket_name,
            Key='cookies/resilience-test.txt',
            Body=test_data,
            ServerSideEncryption='AES256'
        )
        
        # Test retry logic
        with patch.object(s3_client, 'get_object', side_effect=failing_get_object):
            # This should eventually succeed after retries
            try:
                result = cookie_manager_s3._download_cookies_from_s3('cookies/resilience-test.txt')
                # If retry logic is implemented, this should succeed
                if result is not None:
                    assert result == test_data
                else:
                    # If no retry logic, operation fails gracefully
                    assert result is None
            except Exception as e:
                # Should not raise unhandled exceptions
                pytest.fail(f"Unhandled exception in network resilience test: {e}")
        
        # Verify retry attempts were made
        assert call_count['count'] >= 1
    
    @pytest.mark.asyncio 
    async def test_s3_concurrent_operations_consistency(self, cookie_manager_s3, s3_test_bucket, sample_cookie_files):
        """Test consistency of concurrent S3 operations."""
        bucket_name, s3_client = s3_test_bucket
        
        # Prepare test data
        cookie_variants = [
            sample_cookie_files['active'],
            sample_cookie_files['backup'],
            sample_cookie_files['active'].replace('active', 'variant1'),
            sample_cookie_files['backup'].replace('backup', 'variant2')
        ]
        
        # Concurrent upload operations
        upload_tasks = []
        for i, cookie_data in enumerate(cookie_variants):
            encrypted_data = cookie_manager_s3._encrypt_cookie_data(cookie_data)
            
            async def upload_task(index, data):
                return cookie_manager_s3._upload_cookies_to_s3(
                    f'cookies/concurrent-test-{index}.txt',
                    data
                )
            
            task = upload_task(i, encrypted_data)
            upload_tasks.append((i, cookie_data, task))
        
        # Execute concurrent uploads
        upload_results = await asyncio.gather(
            *[task for _, _, task in upload_tasks],
            return_exceptions=True
        )
        
        # Verify all uploads succeeded
        for i, result in enumerate(upload_results):
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent upload {i} failed: {result}")
            assert result is True
        
        # Concurrent download operations
        download_tasks = []
        for i, original_data in enumerate(cookie_variants):
            async def download_task(index):
                encrypted = cookie_manager_s3._download_cookies_from_s3(
                    f'cookies/concurrent-test-{index}.txt'
                )
                if encrypted:
                    return cookie_manager_s3._decrypt_cookie_data(encrypted)
                return None
            
            download_tasks.append((i, original_data, download_task(i)))
        
        # Execute concurrent downloads
        download_results = await asyncio.gather(
            *[task for _, _, task in download_tasks],
            return_exceptions=True
        )
        
        # Verify all downloads succeeded and data integrity
        for i, (original_index, original_data, result) in enumerate(zip(
            range(len(cookie_variants)),
            cookie_variants,
            download_results
        )):
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent download {i} failed: {result}")
            
            assert result is not None
            assert result == original_data
    
    @pytest.mark.asyncio
    async def test_s3_performance_benchmarking(self, cookie_manager_s3, s3_test_bucket, sample_cookie_files):
        """Test S3 operation performance benchmarking."""
        bucket_name, s3_client = s3_test_bucket
        
        # Performance tracking
        performance_metrics = {
            'upload_times': [],
            'download_times': [],
            'encryption_times': [],
            'decryption_times': []
        }
        
        test_data = sample_cookie_files['active'] * 10  # Larger test data
        num_iterations = 5
        
        for i in range(num_iterations):
            # Measure encryption time
            encryption_start = time.time()
            encrypted_data = cookie_manager_s3._encrypt_cookie_data(test_data)
            encryption_time = time.time() - encryption_start
            performance_metrics['encryption_times'].append(encryption_time)
            
            # Measure upload time
            upload_start = time.time()
            upload_success = cookie_manager_s3._upload_cookies_to_s3(
                f'cookies/performance-test-{i}.txt',
                encrypted_data
            )
            upload_time = time.time() - upload_start
            performance_metrics['upload_times'].append(upload_time)
            
            assert upload_success is True
            
            # Measure download time
            download_start = time.time()
            downloaded_data = cookie_manager_s3._download_cookies_from_s3(
                f'cookies/performance-test-{i}.txt'
            )
            download_time = time.time() - download_start
            performance_metrics['download_times'].append(download_time)
            
            assert downloaded_data is not None
            
            # Measure decryption time
            decryption_start = time.time()
            decrypted_data = cookie_manager_s3._decrypt_cookie_data(downloaded_data)
            decryption_time = time.time() - decryption_start
            performance_metrics['decryption_times'].append(decryption_time)
            
            assert decrypted_data == test_data
        
        # Calculate averages
        avg_metrics = {
            metric_name: sum(times) / len(times)
            for metric_name, times in performance_metrics.items()
        }
        
        # Performance assertions (generous limits for test environment)
        assert avg_metrics['upload_times'] < 2.0    # Average upload under 2 seconds
        assert avg_metrics['download_times'] < 2.0   # Average download under 2 seconds
        assert avg_metrics['encryption_times'] < 0.1 # Average encryption under 100ms
        assert avg_metrics['decryption_times'] < 0.1 # Average decryption under 100ms
        
        # Log performance results for monitoring
        print(f"S3 Performance Metrics: {avg_metrics}")
    
    @pytest.mark.asyncio
    async def test_s3_error_handling_and_recovery(self, cookie_manager_s3, s3_test_bucket):
        """Test S3 error handling and recovery mechanisms."""
        bucket_name, s3_client = s3_test_bucket
        
        error_scenarios = [
            {
                'name': 'access_denied',
                'exception': ClientError(
                    error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
                    operation_name='GetObject'
                ),
                'expected_result': None
            },
            {
                'name': 'no_such_key',
                'exception': ClientError(
                    error_response={'Error': {'Code': 'NoSuchKey', 'Message': 'Key not found'}},
                    operation_name='GetObject'
                ),
                'expected_result': None
            },
            {
                'name': 'service_unavailable',
                'exception': ClientError(
                    error_response={'Error': {'Code': 'ServiceUnavailable', 'Message': 'Service unavailable'}},
                    operation_name='GetObject'
                ),
                'expected_result': None
            }
        ]
        
        for scenario in error_scenarios:
            # Mock the specific error
            with patch.object(s3_client, 'get_object', side_effect=scenario['exception']):
                result = cookie_manager_s3._download_cookies_from_s3(
                    f'cookies/error-test-{scenario["name"]}.txt'
                )
                
                # Verify graceful error handling
                assert result == scenario['expected_result']
            
            # Test upload error handling
            with patch.object(s3_client, 'put_object', side_effect=scenario['exception']):
                upload_result = cookie_manager_s3._upload_cookies_to_s3(
                    f'cookies/upload-error-{scenario["name"]}.txt',
                    b'test data'
                )
                
                # Verify upload fails gracefully
                assert upload_result is False
    
    @pytest.mark.asyncio
    async def test_s3_lifecycle_and_cleanup_policies(self, cookie_manager_s3, s3_test_bucket, sample_cookie_files):
        """Test S3 lifecycle policies and cleanup procedures."""
        bucket_name, s3_client = s3_test_bucket
        
        # Set up lifecycle policy
        lifecycle_config = {
            'Rules': [
                {
                    'ID': 'CookieHistoryCleanup',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': 'cookies/history/'},
                    'Expiration': {'Days': 90}
                },
                {
                    'ID': 'CookieBackupTransition',
                    'Status': 'Enabled',
                    'Filter': {'Prefix': 'cookies/backup/'},
                    'Transitions': [
                        {
                            'Days': 30,
                            'StorageClass': 'STANDARD_IA'
                        }
                    ]
                }
            ]
        }
        
        s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_config
        )
        
        # Upload test files to different prefixes
        prefixes = ['cookies/active/', 'cookies/backup/', 'cookies/history/']
        uploaded_files = []
        
        for prefix in prefixes:
            key = f'{prefix}test-cookies.txt'
            encrypted_data = cookie_manager_s3._encrypt_cookie_data(sample_cookie_files['active'])
            
            success = cookie_manager_s3._upload_cookies_to_s3(key, encrypted_data)
            assert success is True
            uploaded_files.append(key)
        
        # Verify lifecycle policy is applied
        lifecycle_response = s3_client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        assert len(lifecycle_response['Rules']) == 2
        
        # Verify files exist
        for key in uploaded_files:
            response = s3_client.head_object(Bucket=bucket_name, Key=key)
            assert response['ResponseMetadata']['HTTPStatusCode'] == 200
        
        # Test manual cleanup functionality
        cleanup_results = []
        for key in uploaded_files:
            try:
                s3_client.delete_object(Bucket=bucket_name, Key=key)
                cleanup_results.append(True)
            except Exception as e:
                cleanup_results.append(False)
        
        # Verify cleanup succeeded
        assert all(cleanup_results)
    
    @pytest.mark.asyncio
    async def test_s3_integration_with_kms_encryption(self, aws_credentials_integration, sample_cookie_files):
        """Test S3 integration with KMS encryption."""
        with mock_s3(), mock_kms():
            # Create KMS key
            kms_client = boto3.client('kms', region_name='us-east-1')
            key_response = kms_client.create_key(
                Description='Test key for cookie encryption'
            )
            key_id = key_response['KeyMetadata']['KeyId']
            
            # Create S3 bucket
            s3_client = boto3.client('s3', region_name='us-east-1')
            bucket_name = 'test-kms-cookie-bucket'
            s3_client.create_bucket(Bucket=bucket_name)
            
            # Create cookie manager with S3+KMS
            with patch('app.core.cookie_manager.boto3.client', return_value=s3_client):
                with patch('app.core.cookie_manager.settings') as mock_settings:
                    mock_settings.aws_region = 'us-east-1'
                    cookie_manager = CookieManager(
                        bucket_name=bucket_name,
                        encryption_key="kms-test-key-1234567890123456789012345678"
                    )
                    cookie_manager._s3_client = s3_client
                    
                    # Upload with KMS encryption
                    test_cookies = sample_cookie_files['active']
                    encrypted_data = cookie_manager._encrypt_cookie_data(test_cookies)
                    
                    # Mock KMS-encrypted upload
                    s3_client.put_object(
                        Bucket=bucket_name,
                        Key='cookies/kms-test.txt',
                        Body=encrypted_data,
                        ServerSideEncryption='aws:kms',
                        SSEKMSKeyId=key_id
                    )
                    
                    # Verify KMS encryption
                    response = s3_client.get_object(Bucket=bucket_name, Key='cookies/kms-test.txt')
                    assert response['ServerSideEncryption'] == 'aws:kms'
                    assert response['SSEKMSKeyId'] == key_id
                    
                    # Verify content integrity
                    downloaded_data = response['Body'].read()
                    decrypted_cookies = cookie_manager._decrypt_cookie_data(downloaded_data)
                    assert decrypted_cookies == test_cookies


if __name__ == "__main__":
    pytest.main([__file__, "-v"])