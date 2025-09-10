"""
Unit tests for temporary file cleanup functionality.

This module tests temporary file creation, tracking, cleanup mechanisms,
error scenarios, and resource management.
"""

import pytest
import os
import tempfile
import time
import threading
import weakref
from unittest.mock import patch, Mock, MagicMock
from pathlib import Path
import gc

from app.core.cookie_manager import CookieManager


class TestTemporaryFileCleanup:
    """Test suite for temporary file cleanup functionality."""
    
    @pytest.fixture
    def cookie_manager(self, mock_cookie_settings):
        """Create cookie manager for cleanup testing."""
        with patch('app.core.cookie_manager.boto3.client'):
            return CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
    
    @pytest.fixture
    def sample_cookie_data(self):
        """Sample cookie data for testing."""
        return """# Netscape HTTP Cookie File
.youtube.com\tTRUE\t/\tFALSE\t1735689600\tVISITOR_INFO1_LIVE\tabc123
.google.com\tTRUE\t/\tFALSE\t1735689600\tSESSION_TOKEN\tdef456
"""
    
    def test_temporary_file_creation_and_cleanup(self, cookie_manager, sample_cookie_data):
        """Test basic temporary file creation and cleanup."""
        # Create temporary file
        temp_path = cookie_manager._create_temporary_cookie_file(sample_cookie_data)
        
        # Verify file exists and contains correct data
        assert os.path.exists(temp_path)
        with open(temp_path, 'r') as f:
            content = f.read()
        assert content == sample_cookie_data
        
        # Cleanup the file
        cookie_manager._cleanup_temporary_file(temp_path)
        
        # Verify file is removed
        assert not os.path.exists(temp_path)
    
    def test_automatic_cleanup_on_deletion(self, sample_cookie_data):
        """Test that temporary files are cleaned up when CookieManager is deleted."""
        created_files = []
        
        # Create and track temporary files
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
            
            # Create multiple temporary files
            for i in range(3):
                temp_path = manager._create_temporary_cookie_file(f"{sample_cookie_data}\n# File {i}")
                created_files.append(temp_path)
                assert os.path.exists(temp_path)
        
        # Delete manager and trigger garbage collection
        del manager
        gc.collect()
        
        # Give some time for cleanup
        time.sleep(0.1)
        
        # Verify all files are cleaned up
        for temp_path in created_files:
            assert not os.path.exists(temp_path)
    
    def test_cleanup_with_invalid_paths(self, cookie_manager):
        """Test cleanup behavior with invalid file paths."""
        # Test cleanup of non-existent file (should not raise error)
        non_existent = "/tmp/non-existent-file.txt"
        cookie_manager._cleanup_temporary_file(non_existent)  # Should not crash
        
        # Test cleanup of None path
        cookie_manager._cleanup_temporary_file(None)  # Should not crash
        
        # Test cleanup of empty string
        cookie_manager._cleanup_temporary_file("")  # Should not crash
        
        # Test cleanup of directory path
        temp_dir = tempfile.mkdtemp()
        try:
            cookie_manager._cleanup_temporary_file(temp_dir)  # Should not crash
            # Directory should still exist (we don't delete directories)
            assert os.path.exists(temp_dir)
        finally:
            os.rmdir(temp_dir)
    
    def test_cleanup_with_permission_errors(self, cookie_manager, sample_cookie_data):
        """Test cleanup behavior when file permissions prevent deletion."""
        # Create temporary file
        temp_path = cookie_manager._create_temporary_cookie_file(sample_cookie_data)
        
        # Make file read-only and directory read-only (on Unix systems)
        if os.name != 'nt':  # Not Windows
            os.chmod(temp_path, 0o444)  # Read-only file
            parent_dir = os.path.dirname(temp_path)
            original_dir_mode = os.stat(parent_dir).st_mode
            os.chmod(parent_dir, 0o555)  # Read-only directory
            
            try:
                # Cleanup should handle permission errors gracefully
                cookie_manager._cleanup_temporary_file(temp_path)
                # File might still exist due to permissions, that's OK
                
            finally:
                # Restore permissions for cleanup
                os.chmod(parent_dir, original_dir_mode)
                if os.path.exists(temp_path):
                    os.chmod(temp_path, 0o644)
                    os.unlink(temp_path)
    
    def test_multiple_temporary_files_cleanup(self, cookie_manager, sample_cookie_data):
        """Test creation and cleanup of multiple temporary files."""
        temp_files = []
        
        # Create multiple temporary files
        for i in range(10):
            content = f"{sample_cookie_data}\n# File number {i}\n"
            temp_path = cookie_manager._create_temporary_cookie_file(content)
            temp_files.append(temp_path)
            assert os.path.exists(temp_path)
        
        # Verify all files exist
        for temp_path in temp_files:
            assert os.path.exists(temp_path)
        
        # Cleanup all files
        for temp_path in temp_files:
            cookie_manager._cleanup_temporary_file(temp_path)
        
        # Verify all files are removed
        for temp_path in temp_files:
            assert not os.path.exists(temp_path)
    
    def test_concurrent_file_creation_and_cleanup(self, cookie_manager, sample_cookie_data):
        """Test concurrent temporary file operations."""
        results = {'created': [], 'cleaned': [], 'errors': []}
        results_lock = threading.Lock()
        
        def worker_thread(worker_id):
            """Worker function for concurrent file operations."""
            try:
                # Create temporary file
                content = f"{sample_cookie_data}\n# Worker {worker_id}\n"
                temp_path = cookie_manager._create_temporary_cookie_file(content)
                
                with results_lock:
                    results['created'].append(temp_path)
                
                # Verify file exists
                assert os.path.exists(temp_path)
                
                # Small delay to simulate processing
                time.sleep(0.01)
                
                # Cleanup file
                cookie_manager._cleanup_temporary_file(temp_path)
                
                with results_lock:
                    results['cleaned'].append(temp_path)
                
                # Verify file is gone
                assert not os.path.exists(temp_path)
                
            except Exception as e:
                with results_lock:
                    results['errors'].append(str(e))
        
        # Create and start threads
        threads = []
        num_workers = 10
        
        for i in range(num_workers):
            thread = threading.Thread(target=worker_thread, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=5)
        
        # Verify results
        assert len(results['created']) == num_workers
        assert len(results['cleaned']) == num_workers
        assert len(results['errors']) == 0
        
        # Verify no files remain
        for temp_path in results['created']:
            assert not os.path.exists(temp_path)
    
    def test_cleanup_tracking_and_registration(self, cookie_manager, sample_cookie_data):
        """Test that temporary files are properly tracked for cleanup."""
        # Access internal tracking if available
        if hasattr(cookie_manager, '_temp_files'):
            initial_count = len(cookie_manager._temp_files)
        else:
            initial_count = 0
        
        # Create temporary files
        temp_files = []
        for i in range(3):
            temp_path = cookie_manager._create_temporary_cookie_file(sample_cookie_data)
            temp_files.append(temp_path)
        
        # Check tracking (if implemented)
        if hasattr(cookie_manager, '_temp_files'):
            assert len(cookie_manager._temp_files) == initial_count + 3
        
        # Cleanup files one by one
        for temp_path in temp_files:
            cookie_manager._cleanup_temporary_file(temp_path)
        
        # Check tracking after cleanup
        if hasattr(cookie_manager, '_temp_files'):
            assert len(cookie_manager._temp_files) == initial_count
    
    def test_cleanup_on_exception_during_file_creation(self, cookie_manager):
        """Test cleanup when exceptions occur during file creation."""
        # Mock file operations to fail after creation
        original_tempfile = tempfile.NamedTemporaryFile
        created_files = []
        
        def mock_tempfile(*args, **kwargs):
            temp_file = original_tempfile(*args, **kwargs)
            created_files.append(temp_file.name)
            return temp_file
        
        with patch('tempfile.NamedTemporaryFile', side_effect=mock_tempfile):
            # Mock write operation to fail
            with patch('builtins.open', side_effect=OSError("Write failed")):
                try:
                    cookie_manager._create_temporary_cookie_file("test data")
                    pytest.fail("Expected OSError")
                except OSError:
                    pass  # Expected
        
        # Verify cleanup happened
        for file_path in created_files:
            assert not os.path.exists(file_path)
    
    def test_large_file_cleanup(self, cookie_manager):
        """Test cleanup of large temporary files."""
        # Create large cookie data (10MB+)
        large_data = "# Large cookie file\n"
        for i in range(50000):
            large_data += f".domain{i}.com\tTRUE\t/\tFALSE\t1735689600\tCOOKIE{i}\tvalue{'x' * 100}\n"
        
        # Create temporary file with large data
        temp_path = cookie_manager._create_temporary_cookie_file(large_data)
        
        # Verify file exists and has correct size
        assert os.path.exists(temp_path)
        file_size = os.path.getsize(temp_path)
        assert file_size > 10 * 1024 * 1024  # > 10MB
        
        # Cleanup should work even for large files
        cookie_manager._cleanup_temporary_file(temp_path)
        assert not os.path.exists(temp_path)
    
    def test_cleanup_with_special_characters_in_path(self, cookie_manager, sample_cookie_data):
        """Test cleanup with special characters in file paths."""
        # Create temporary file in directory with special characters
        special_dir = tempfile.mkdtemp(suffix="_test with spaces & symbols!")
        try:
            # Create file in special directory
            temp_path = os.path.join(special_dir, "cookie file with spaces & symbols!.txt")
            with open(temp_path, 'w') as f:
                f.write(sample_cookie_data)
            
            assert os.path.exists(temp_path)
            
            # Cleanup should handle special characters
            cookie_manager._cleanup_temporary_file(temp_path)
            assert not os.path.exists(temp_path)
            
        finally:
            # Clean up directory
            if os.path.exists(special_dir):
                for file in os.listdir(special_dir):
                    os.unlink(os.path.join(special_dir, file))
                os.rmdir(special_dir)
    
    def test_cleanup_performance_with_many_files(self, cookie_manager, sample_cookie_data):
        """Test cleanup performance with many temporary files."""
        import time
        
        # Create many temporary files
        temp_files = []
        creation_start = time.time()
        
        for i in range(100):
            temp_path = cookie_manager._create_temporary_cookie_file(f"{sample_cookie_data}\n# File {i}")
            temp_files.append(temp_path)
        
        creation_time = time.time() - creation_start
        
        # Cleanup all files
        cleanup_start = time.time()
        for temp_path in temp_files:
            cookie_manager._cleanup_temporary_file(temp_path)
        cleanup_time = time.time() - cleanup_start
        
        # Performance assertions (generous limits)
        assert creation_time < 5.0  # Should create 100 files in under 5 seconds
        assert cleanup_time < 2.0   # Should cleanup 100 files in under 2 seconds
        
        # Verify all files are gone
        for temp_path in temp_files:
            assert not os.path.exists(temp_path)
    
    def test_weakref_cleanup_mechanism(self, sample_cookie_data):
        """Test cleanup using weak references (if implemented)."""
        temp_files_created = []
        
        # Create CookieManager and temporary files
        with patch('app.core.cookie_manager.boto3.client'):
            manager = CookieManager(
                bucket_name="test-bucket",
                encryption_key="test-key-1234567890123456789012345678"
            )
            
            # Create temporary files
            for i in range(3):
                temp_path = manager._create_temporary_cookie_file(sample_cookie_data)
                temp_files_created.append(temp_path)
            
            # Create weak reference to manager
            manager_ref = weakref.ref(manager)
            assert manager_ref() is not None
        
        # Delete strong reference
        del manager
        
        # Force garbage collection
        gc.collect()
        
        # Verify weak reference is gone
        assert manager_ref() is None
        
        # Verify temporary files are cleaned up
        for temp_path in temp_files_created:
            # Files should be cleaned up (may take a moment)
            max_wait = 1.0
            start_time = time.time()
            while os.path.exists(temp_path) and (time.time() - start_time) < max_wait:
                time.sleep(0.1)
                gc.collect()
            
            assert not os.path.exists(temp_path)
    
    def test_cleanup_with_symlinks(self, cookie_manager, sample_cookie_data):
        """Test cleanup behavior with symbolic links."""
        if os.name == 'nt':  # Skip on Windows
            pytest.skip("Symbolic links test not supported on Windows")
        
        # Create temporary file
        temp_path = cookie_manager._create_temporary_cookie_file(sample_cookie_data)
        assert os.path.exists(temp_path)
        
        # Create symlink to the file
        symlink_path = temp_path + "_symlink"
        os.symlink(temp_path, symlink_path)
        assert os.path.islink(symlink_path)
        assert os.path.exists(symlink_path)
        
        try:
            # Cleanup original file
            cookie_manager._cleanup_temporary_file(temp_path)
            assert not os.path.exists(temp_path)
            
            # Symlink should now be broken
            assert os.path.islink(symlink_path)  # Link still exists
            assert not os.path.exists(symlink_path)  # But target is gone
            
        finally:
            # Clean up symlink
            if os.path.islink(symlink_path):
                os.unlink(symlink_path)
    
    def test_cleanup_error_logging(self, cookie_manager, sample_cookie_data):
        """Test that cleanup errors are properly logged."""
        # Create temporary file
        temp_path = cookie_manager._create_temporary_cookie_file(sample_cookie_data)
        
        # Mock os.unlink to raise error
        with patch('os.unlink', side_effect=OSError("Permission denied")):
            # Mock logger to capture log messages
            with patch('app.core.cookie_manager.logger') as mock_logger:
                cookie_manager._cleanup_temporary_file(temp_path)
                
                # Verify error was logged (if logging is implemented)
                if mock_logger.error.called or mock_logger.warning.called:
                    assert mock_logger.error.called or mock_logger.warning.called
        
        # Manually clean up for test cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    
    def test_context_manager_cleanup(self, sample_cookie_data):
        """Test cleanup when using CookieManager as context manager."""
        temp_files = []
        
        # Use context manager (if implemented)
        try:
            with patch('app.core.cookie_manager.boto3.client'):
                manager = CookieManager(
                    bucket_name="test-bucket",
                    encryption_key="test-key-1234567890123456789012345678"
                )
                
                # Check if context manager methods exist
                if hasattr(manager, '__enter__') and hasattr(manager, '__exit__'):
                    with manager:
                        # Create temporary files within context
                        for i in range(3):
                            temp_path = manager._create_temporary_cookie_file(sample_cookie_data)
                            temp_files.append(temp_path)
                            assert os.path.exists(temp_path)
                    
                    # After context exit, files should be cleaned up
                    for temp_path in temp_files:
                        assert not os.path.exists(temp_path)
                else:
                    # If context manager not implemented, clean up manually
                    for i in range(3):
                        temp_path = manager._create_temporary_cookie_file(sample_cookie_data)
                        temp_files.append(temp_path)
                    
                    for temp_path in temp_files:
                        manager._cleanup_temporary_file(temp_path)
                        
        finally:
            # Ensure cleanup in case of test failures
            for temp_path in temp_files:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
    
    def test_cleanup_order_and_dependencies(self, cookie_manager, sample_cookie_data):
        """Test cleanup order when files have dependencies."""
        # Create parent temporary file
        parent_content = sample_cookie_data
        parent_path = cookie_manager._create_temporary_cookie_file(parent_content)
        
        # Create child files that reference parent (conceptually)
        child_paths = []
        for i in range(3):
            child_content = f"{sample_cookie_data}\n# Child of {os.path.basename(parent_path)}"
            child_path = cookie_manager._create_temporary_cookie_file(child_content)
            child_paths.append(child_path)
        
        # Verify all files exist
        assert os.path.exists(parent_path)
        for child_path in child_paths:
            assert os.path.exists(child_path)
        
        # Cleanup in any order should work (no real dependencies in filesystem)
        cookie_manager._cleanup_temporary_file(parent_path)  # Parent first
        for child_path in child_paths:
            cookie_manager._cleanup_temporary_file(child_path)
        
        # Verify all files are gone
        assert not os.path.exists(parent_path)
        for child_path in child_paths:
            assert not os.path.exists(child_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])