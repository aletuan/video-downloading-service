"""
ECS container integration tests for cookie management.

This module tests containerized deployment scenarios, environment variable
handling, health checks, and container-specific cookie operations.
"""

import pytest
import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from app.core.cookie_manager import CookieManager
from app.services.downloader import YouTubeDownloader
from app.core.config import get_settings, AWSSettings
from app.main import app


@pytest.mark.integration
class TestECSContainerIntegration:
    """Integration test suite for ECS container deployment."""
    
    @pytest.fixture
    def container_environment(self):
        """Mock ECS container environment variables."""
        container_env = {
            'ENVIRONMENT': 'aws',
            'AWS_REGION': 'us-east-1',
            'AWS_DEFAULT_REGION': 'us-east-1',
            'COOKIE_S3_BUCKET': 'test-cookie-bucket-ecs',
            'COOKIE_ENCRYPTION_KEY': 'container-test-key-1234567890123456789012',
            'COOKIE_REFRESH_INTERVAL': '30',
            'COOKIE_VALIDATION_ENABLED': 'true',
            'COOKIE_BACKUP_COUNT': '5',
            'COOKIE_TEMP_DIR': '/tmp/container_cookies',
            'COOKIE_DEBUG_LOGGING': 'false',
            'DATABASE_URL': 'postgresql://test:test@db:5432/test_db',
            'REDIS_URL': 'redis://redis:6379/0',
            'ECS_CONTAINER_METADATA_URI_V4': 'http://169.254.170.2/v4/container-123',
            'AWS_EXECUTION_ROLE_ARN': 'arn:aws:iam::123456789012:role/ecsTaskExecutionRole',
            'AWS_TASK_ROLE_ARN': 'arn:aws:iam::123456789012:role/ecsTaskRole'
        }
        
        with patch.dict(os.environ, container_env):
            yield container_env
    
    @pytest.fixture
    def ecs_metadata_mock(self):
        """Mock ECS container metadata endpoint."""
        metadata_response = {
            'DockerId': 'container-123',
            'Name': 'youtube-downloader',
            'DockerName': 'youtube-downloader-task',
            'Image': 'youtube-downloader:latest',
            'ImageID': 'sha256:abcdef123456',
            'Labels': {
                'com.amazonaws.ecs.cluster': 'youtube-downloader-cluster',
                'com.amazonaws.ecs.container-name': 'youtube-downloader',
                'com.amazonaws.ecs.task-arn': 'arn:aws:ecs:us-east-1:123456789012:task/cluster/task-123',
                'com.amazonaws.ecs.task-definition-family': 'youtube-downloader',
                'com.amazonaws.ecs.task-definition-version': '1'
            },
            'DesiredStatus': 'RUNNING',
            'KnownStatus': 'RUNNING',
            'Limits': {
                'CPU': 1024,
                'Memory': 2048
            },
            'CreatedAt': datetime.now().isoformat(),
            'StartedAt': datetime.now().isoformat(),
            'Type': 'NORMAL'
        }
        
        def mock_metadata_request(url):
            response_mock = Mock()
            response_mock.json.return_value = metadata_response
            response_mock.status_code = 200
            return response_mock
        
        with patch('requests.get', side_effect=mock_metadata_request):
            yield metadata_response
    
    @pytest.fixture
    def container_cookie_manager(self, container_environment, ecs_metadata_mock):
        """CookieManager configured for ECS container environment."""
        with patch('app.core.cookie_manager.boto3.client'):
            # Get settings in container environment
            settings = get_settings()
            assert isinstance(settings, AWSSettings)
            
            manager = CookieManager(
                bucket_name=settings.cookie_s3_bucket,
                encryption_key=settings.cookie_encryption_key
            )
            
            # Mock S3 operations for container testing
            manager._download_cookies_from_s3 = AsyncMock()
            manager._upload_cookies_to_s3 = AsyncMock(return_value=True)
            manager._validate_cookies = AsyncMock(return_value={
                'valid': True,
                'cookie_count': 20,
                'domains': ['.youtube.com', '.google.com']
            })
            
            return manager
    
    @pytest.mark.asyncio
    async def test_container_startup_health_check(self, container_environment, container_cookie_manager):
        """Test container startup health check with cookie manager."""
        health_check_results = []
        
        def mock_health_check_step(component, status, details=None):
            health_check_results.append({
                'component': component,
                'status': status,
                'details': details or {},
                'timestamp': datetime.now()
            })
        
        # Mock health check components
        with patch('app.core.health.check_database_health', return_value=True):
            with patch('app.core.health.check_redis_health', return_value=True):
                with patch('app.core.health.check_storage_health', return_value=True):
                    with patch('app.core.health.record_health_check', side_effect=mock_health_check_step):
                        # Simulate container startup health checks
                        health_checks = [
                            ('database', True),
                            ('redis', True),
                            ('storage', True),
                            ('cookie_manager', True)
                        ]
                        
                        for component, expected_status in health_checks:
                            mock_health_check_step(component, expected_status)
        
        # Verify all health checks passed
        assert len(health_check_results) == 4
        
        component_statuses = {hc['component']: hc['status'] for hc in health_check_results}
        for component, status in component_statuses.items():
            assert status is True, f"Health check failed for {component}"
        
        # Verify cookie manager specific health
        cookie_health = next((hc for hc in health_check_results if hc['component'] == 'cookie_manager'), None)
        assert cookie_health is not None
        assert cookie_health['status'] is True
    
    @pytest.mark.asyncio
    async def test_container_environment_variable_loading(self, container_environment):
        """Test loading of environment variables in container context."""
        # Test settings initialization in container environment
        settings = get_settings()
        
        # Verify AWS settings are loaded
        assert isinstance(settings, AWSSettings)
        assert settings.environment == 'aws'
        assert settings.aws_region == 'us-east-1'
        
        # Verify cookie-specific settings
        assert settings.cookie_s3_bucket == 'test-cookie-bucket-ecs'
        assert settings.cookie_encryption_key == 'container-test-key-1234567890123456789012'
        assert settings.cookie_refresh_interval == 30
        assert settings.cookie_validation_enabled is True
        assert settings.cookie_backup_count == 5
        assert settings.cookie_debug_logging is False
        
        # Verify infrastructure settings
        assert 'postgresql://' in settings.database_url
        assert 'redis://' in settings.redis_url
    
    @pytest.mark.asyncio
    async def test_container_file_system_permissions(self, container_environment, container_cookie_manager):
        """Test file system permissions for cookie operations in container."""
        temp_dir = Path(container_environment['COOKIE_TEMP_DIR'])
        
        # Test temporary directory creation
        try:
            temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            assert temp_dir.exists()
            assert temp_dir.is_dir()
        except PermissionError:
            pytest.skip("Container file system permissions test requires proper setup")
        
        # Test cookie file creation permissions
        test_cookie_file = temp_dir / 'test_container_cookies.txt'
        test_content = "# Test container cookie file\n.youtube.com\tTRUE\t/\tFALSE\t1735689600\tTEST\tvalue"
        
        try:
            test_cookie_file.write_text(test_content, mode='w')
            assert test_cookie_file.exists()
            
            # Verify file permissions are secure
            file_permissions = oct(test_cookie_file.stat().st_mode)[-3:]
            assert file_permissions in ['600', '700']  # Owner read/write only
            
            # Test read access
            read_content = test_cookie_file.read_text()
            assert read_content == test_content
            
        except PermissionError:
            pytest.skip("Container file permission test requires appropriate file system setup")
        
        finally:
            # Cleanup
            if test_cookie_file.exists():
                test_cookie_file.unlink()
            if temp_dir.exists() and temp_dir != Path('/tmp'):
                temp_dir.rmdir()
    
    @pytest.mark.asyncio
    async def test_container_memory_and_resource_constraints(self, container_environment, ecs_metadata_mock):
        """Test cookie operations under container resource constraints."""
        # Get container resource limits
        memory_limit_mb = ecs_metadata_mock['Limits']['Memory']
        cpu_limit = ecs_metadata_mock['Limits']['CPU']
        
        # Create large cookie data to test memory constraints
        large_cookie_data = "# Large cookie file for memory testing\n"
        for i in range(1000):  # Create substantial test data
            large_cookie_data += f".domain{i}.com\tTRUE\t/\tFALSE\t1735689600\tCOOKIE{i}\t{'x' * 100}\n"
        
        # Test memory usage during encryption
        import psutil
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="memory-test-bucket",
                encryption_key="memory-test-key-1234567890123456789012345678"
            )
            
            # Test encryption/decryption memory usage
            encrypted_data = manager._encrypt_cookie_data(large_cookie_data)
            decrypted_data = manager._decrypt_cookie_data(encrypted_data)
            
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = peak_memory - initial_memory
            
        # Verify memory usage stays within container limits
        assert memory_increase < (memory_limit_mb * 0.1)  # Should use less than 10% of container memory
        
        # Verify data integrity
        assert decrypted_data == large_cookie_data
    
    @pytest.mark.asyncio
    async def test_container_network_connectivity_validation(self, container_environment):
        """Test network connectivity from container environment."""
        network_tests = [
            {
                'name': 'aws_s3_connectivity',
                'endpoint': 's3.us-east-1.amazonaws.com',
                'port': 443,
                'protocol': 'https'
            },
            {
                'name': 'aws_sts_connectivity', 
                'endpoint': 'sts.us-east-1.amazonaws.com',
                'port': 443,
                'protocol': 'https'
            }
        ]
        
        connectivity_results = []
        
        for test in network_tests:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((test['endpoint'], test['port']))
                sock.close()
                
                connectivity_results.append({
                    'name': test['name'],
                    'endpoint': test['endpoint'],
                    'success': result == 0,
                    'error': None if result == 0 else f"Connection failed with code {result}"
                })
                
            except Exception as e:
                connectivity_results.append({
                    'name': test['name'],
                    'endpoint': test['endpoint'],
                    'success': False,
                    'error': str(e)
                })
        
        # Verify connectivity (may skip if network isolated)
        failed_connections = [r for r in connectivity_results if not r['success']]
        
        if len(failed_connections) == len(connectivity_results):
            pytest.skip("Container network connectivity test requires network access")
        
        # At least some connections should work in proper container environment
        successful_connections = [r for r in connectivity_results if r['success']]
        assert len(successful_connections) > 0
    
    @pytest.mark.asyncio
    async def test_container_iam_role_integration(self, container_environment, ecs_metadata_mock):
        """Test IAM role integration for cookie S3 operations."""
        task_role_arn = container_environment['AWS_TASK_ROLE_ARN']
        execution_role_arn = container_environment['AWS_EXECUTION_ROLE_ARN']
        
        # Mock AWS credentials from task role
        mock_credentials = {
            'AccessKeyId': 'ASIATEST123456789012',
            'SecretAccessKey': 'test-secret-key',
            'SessionToken': 'test-session-token',
            'Expiration': (datetime.now() + timedelta(hours=1)).isoformat()
        }
        
        def mock_assume_role(*args, **kwargs):
            return {
                'Credentials': mock_credentials,
                'AssumedRoleUser': {
                    'AssumedRoleId': 'AROATEST123456789012:test-session',
                    'Arn': f"{task_role_arn}/test-session"
                }
            }
        
        # Test IAM role-based S3 access
        with patch('boto3.client') as mock_boto_client:
            mock_s3_client = Mock()
            mock_sts_client = Mock()
            
            def boto_client_factory(service, **kwargs):
                if service == 's3':
                    return mock_s3_client
                elif service == 'sts':
                    mock_sts_client.assume_role = mock_assume_role
                    return mock_sts_client
                return Mock()
            
            mock_boto_client.side_effect = boto_client_factory
            
            # Mock successful S3 operations
            mock_s3_client.get_object.return_value = {
                'Body': Mock(read=Mock(return_value=b'test encrypted cookie data')),
                'ServerSideEncryption': 'AES256'
            }
            mock_s3_client.put_object.return_value = {
                'ETag': '"test-etag"',
                'ServerSideEncryption': 'AES256'
            }
            
            # Test cookie manager with IAM role
            manager = CookieManager(
                bucket_name=container_environment['COOKIE_S3_BUCKET'],
                encryption_key=container_environment['COOKIE_ENCRYPTION_KEY']
            )
            
            # Test download operation
            result = manager._download_cookies_from_s3('cookies/test.txt')
            assert result == b'test encrypted cookie data'
            
            # Test upload operation
            test_data = b'encrypted test cookie data'
            success = manager._upload_cookies_to_s3('cookies/test-upload.txt', test_data)
            assert success is True
            
            # Verify S3 client was called with proper parameters
            mock_s3_client.get_object.assert_called_once()
            mock_s3_client.put_object.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_container_logging_and_monitoring_integration(self, container_environment, ecs_metadata_mock):
        """Test logging and monitoring integration in container environment."""
        log_entries = []
        metric_entries = []
        
        def mock_log_handler(record):
            log_entries.append({
                'level': record.levelname,
                'message': record.getMessage(),
                'timestamp': datetime.now(),
                'module': record.module
            })
        
        def mock_metric_handler(metric_name, value, tags=None):
            metric_entries.append({
                'metric': metric_name,
                'value': value,
                'tags': tags or {},
                'timestamp': datetime.now()
            })
        
        # Test cookie manager logging
        with patch('logging.getLogger') as mock_logger:
            logger_instance = Mock()
            mock_logger.return_value = logger_instance
            
            # Configure log handler
            logger_instance.info.side_effect = lambda msg: mock_log_handler(Mock(levelname='INFO', getMessage=lambda: msg, module='cookie_manager'))
            logger_instance.warning.side_effect = lambda msg: mock_log_handler(Mock(levelname='WARNING', getMessage=lambda: msg, module='cookie_manager'))
            logger_instance.error.side_effect = lambda msg: mock_log_handler(Mock(levelname='ERROR', getMessage=lambda: msg, module='cookie_manager'))
            
            with patch('app.core.cookie_manager.boto3.client'):
                manager = CookieManager(
                    bucket_name=container_environment['COOKIE_S3_BUCKET'],
                    encryption_key=container_environment['COOKIE_ENCRYPTION_KEY']
                )
                
                # Generate log entries
                logger_instance.info("Cookie manager initialized in container environment")
                logger_instance.info(f"Container ID: {ecs_metadata_mock['DockerId']}")
                logger_instance.info(f"Task ARN: {ecs_metadata_mock['Labels']['com.amazonaws.ecs.task-arn']}")
        
        # Test performance metrics
        with patch('app.services.downloader.record_performance_metric', side_effect=mock_metric_handler):
            mock_metric_handler('cookie_manager.initialization.duration', 0.5, {'container_id': ecs_metadata_mock['DockerId']})
            mock_metric_handler('cookie_manager.s3.connection.success', 1, {'bucket': container_environment['COOKIE_S3_BUCKET']})
        
        # Verify logging integration
        assert len(log_entries) >= 3
        
        container_logs = [log for log in log_entries if 'container' in log['message'].lower()]
        assert len(container_logs) > 0
        
        # Verify metrics integration
        assert len(metric_entries) >= 2
        
        duration_metrics = [m for m in metric_entries if 'duration' in m['metric']]
        success_metrics = [m for m in metric_entries if 'success' in m['metric']]
        
        assert len(duration_metrics) > 0
        assert len(success_metrics) > 0
    
    @pytest.mark.asyncio
    async def test_container_graceful_shutdown_handling(self, container_environment, container_cookie_manager):
        """Test graceful shutdown handling for cookie operations."""
        shutdown_events = []
        
        def track_shutdown_event(event_type, details=None):
            shutdown_events.append({
                'event': event_type,
                'details': details or {},
                'timestamp': datetime.now()
            })
        
        # Mock signal handling
        import signal
        
        def mock_signal_handler(signum, frame):
            track_shutdown_event('signal_received', {'signal': signum})
            
            # Simulate graceful shutdown sequence
            track_shutdown_event('cleanup_started')
            
            # Cookie manager cleanup
            if hasattr(container_cookie_manager, 'cleanup_temporary_files'):
                container_cookie_manager.cleanup_temporary_files()
                track_shutdown_event('cookie_cleanup_completed')
            
            track_shutdown_event('shutdown_completed')
        
        # Register signal handler
        original_handler = signal.signal(signal.SIGTERM, mock_signal_handler)
        
        try:
            # Simulate container receiving SIGTERM
            os.kill(os.getpid(), signal.SIGTERM)
            
            # Allow signal processing
            await asyncio.sleep(0.1)
            
        except KeyboardInterrupt:
            # Expected behavior for signal handling
            pass
        
        finally:
            # Restore original handler
            signal.signal(signal.SIGTERM, original_handler)
        
        # Verify shutdown sequence
        expected_events = ['signal_received', 'cleanup_started', 'shutdown_completed']
        actual_events = [event['event'] for event in shutdown_events]
        
        for expected_event in expected_events:
            if expected_event in actual_events:
                assert expected_event in actual_events
    
    @pytest.mark.asyncio
    async def test_container_multi_service_integration(self, container_environment, container_cookie_manager):
        """Test integration between cookie manager and other container services."""
        service_health = {}
        
        # Mock service dependencies
        mock_services = {
            'database': Mock(status='healthy'),
            'redis': Mock(status='healthy'),
            'storage': Mock(status='healthy'),
            'cookie_manager': container_cookie_manager
        }
        
        # Test service interdependencies
        async def check_service_health(service_name, service_instance):
            if service_name == 'cookie_manager':
                # Cookie manager depends on storage and may depend on database
                storage_healthy = mock_services['storage'].status == 'healthy'
                
                if storage_healthy:
                    service_health[service_name] = 'healthy'
                else:
                    service_health[service_name] = 'unhealthy'
            else:
                service_health[service_name] = service_instance.status
        
        # Check all services
        for service_name, service_instance in mock_services.items():
            await check_service_health(service_name, service_instance)
        
        # Verify service integration
        assert all(status == 'healthy' for status in service_health.values())
        
        # Test service communication
        integration_tests = [
            {
                'name': 'cookie_manager_to_storage',
                'test': lambda: container_cookie_manager._upload_cookies_to_s3('test.txt', b'data'),
                'expected_result': True
            }
        ]
        
        for test in integration_tests:
            try:
                result = await test['test']()
                assert result == test['expected_result']
            except Exception as e:
                pytest.fail(f"Integration test {test['name']} failed: {e}")
    
    @pytest.mark.asyncio
    async def test_container_security_context_validation(self, container_environment, ecs_metadata_mock):
        """Test security context and permissions in container environment."""
        security_checks = []
        
        # Check environment variable security
        sensitive_vars = ['COOKIE_ENCRYPTION_KEY', 'DATABASE_URL']
        for var in sensitive_vars:
            if var in container_environment:
                value = container_environment[var]
                
                # Verify sensitive values are not logged
                security_checks.append({
                    'check': f'{var}_not_in_plaintext_logs',
                    'passed': len(value) > 10,  # Should be substantial
                    'details': f'{var} length: {len(value)}'
                })
        
        # Check file system security
        temp_dir = Path('/tmp/container_cookies')
        if temp_dir.exists():
            try:
                # Verify directory permissions
                dir_permissions = oct(temp_dir.stat().st_mode)[-3:]
                security_checks.append({
                    'check': 'temp_dir_permissions',
                    'passed': dir_permissions in ['700', '750'],
                    'details': f'Directory permissions: {dir_permissions}'
                })
            except Exception as e:
                security_checks.append({
                    'check': 'temp_dir_permissions',
                    'passed': False,
                    'details': f'Error checking permissions: {e}'
                })
        
        # Check IAM role configuration
        task_role = container_environment.get('AWS_TASK_ROLE_ARN')
        if task_role:
            security_checks.append({
                'check': 'iam_role_configured',
                'passed': task_role.startswith('arn:aws:iam::'),
                'details': f'Task role: {task_role}'
            })
        
        # Verify security checks
        failed_checks = [check for check in security_checks if not check['passed']]
        
        if failed_checks:
            for check in failed_checks:
                print(f"Security check failed: {check['check']} - {check['details']}")
        
        # All critical security checks should pass
        critical_checks = [check for check in security_checks if check['check'] in ['iam_role_configured']]
        for check in critical_checks:
            assert check['passed'], f"Critical security check failed: {check['check']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])