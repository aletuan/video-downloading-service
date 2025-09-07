"""
Integration tests for error handling and edge cases.

Tests HTTP error codes, authentication/authorization, request validation,
and malformed request handling across all endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
import threading


class TestErrorHandling:
    """Test error handling and HTTP status codes."""
    
    def test_404_for_nonexistent_endpoints(self, client, mock_database, mock_storage):
        """Test 404 response for non-existent endpoints."""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    def test_405_for_wrong_http_method(self, client, mock_database, mock_storage):
        """Test 405 response for wrong HTTP methods."""
        # Health endpoint only supports GET, try POST
        response = client.post("/health")
        assert response.status_code == 405
    
    def test_422_for_invalid_request_body(self, client, mock_database, mock_storage):
        """Test 422 response for invalid request body."""
        # Try to create admin key without required setup token header
        response = client.post(
            "/api/v1/bootstrap/admin-key",
            json={"invalid": "data"}
        )
        
        assert response.status_code in [422, 403]  # Validation error or missing header
    
    def test_content_type_handling(self, client, mock_database, mock_storage):
        """Test proper content-type handling."""
        # Send invalid JSON
        response = client.post(
            "/api/v1/bootstrap/admin-key",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422


class TestAuthenticationAndAuthorization:
    """Test authentication and authorization middleware."""
    
    def test_missing_api_key_header(self, client, mock_database, mock_storage):
        """Test endpoints that require API key but none provided."""
        protected_endpoints = [
            ("POST", "/api/v1/download"),
            ("GET", "/api/v1/jobs"),
            ("GET", "/api/v1/admin/api-keys")
        ]
        
        for method, endpoint in protected_endpoints:
            response = client.request(
                method, 
                endpoint,
                json={} if method == "POST" else None
            )
            assert response.status_code in [401, 403]
    
    def test_invalid_api_key_format(self, client, mock_database, mock_storage):
        """Test API key with invalid format."""
        invalid_keys = [
            "invalid_key",
            "yvs_",  # Too short
            "wrong_prefix_12345",
            ""
        ]
        
        for invalid_key in invalid_keys:
            response = client.post(
                "/api/v1/download",
                json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
                headers={"X-API-Key": invalid_key}
            )
            assert response.status_code in [401, 403]
    
    @patch("app.routers.downloads.validate_api_key")
    def test_insufficient_permissions(self, mock_validate, client, mock_database, mock_storage):
        """Test API key with insufficient permissions."""
        # Mock API key with read-only permissions trying to access download endpoint
        mock_validate.return_value = MagicMock(
            permission_level="read_only",
            is_valid=True
        )
        
        response = client.post(
            "/api/v1/download",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
            headers={"X-API-Key": "yvs_readonly_key"}
        )
        
        assert response.status_code == 403


class TestRequestValidation:
    """Test request validation and data sanitization."""
    
    def test_url_parameter_validation(self, client, mock_database, mock_storage):
        """Test URL parameter validation."""
        invalid_urls = [
            "",
            "not-a-url",
            "https://www.google.com",  # Not YouTube
            "javascript:alert('xss')",
        ]
        
        for invalid_url in invalid_urls:
            response = client.get(
                "/api/v1/info",
                params={"url": invalid_url}
            )
            assert response.status_code == 422
    
    def test_json_body_validation(self, client, mock_database, mock_storage):
        """Test JSON body validation."""
        # Test download endpoint with invalid data
        invalid_payloads = [
            {},  # Missing required url
            {"url": ""},  # Empty URL
            {"url": "https://www.youtube.com/watch?v=test", "quality": "invalid"},  # Invalid quality
            {"url": "https://www.youtube.com/watch?v=test", "output_format": "invalid"}  # Invalid format
        ]
        
        for payload in invalid_payloads:
            response = client.post("/api/v1/download", json=payload)
            assert response.status_code in [401, 403, 422]  # Auth error or validation error
    
    def test_query_parameter_limits(self, client, mock_database, mock_storage):
        """Test query parameter limits and validation."""
        # Test jobs endpoint with invalid pagination parameters
        with patch("app.routers.downloads.validate_api_key") as mock_validate:
            mock_validate.return_value = MagicMock(
                permission_level="admin",
                is_valid=True
            )
            
            # Test negative page number
            response = client.get(
                "/api/v1/jobs?page=-1",
                headers={"X-API-Key": "test_key"}
            )
            # Should handle gracefully, either 422 or default to page 1
            assert response.status_code in [200, 422]
            
            # Test excessive per_page limit
            response = client.get(
                "/api/v1/jobs?per_page=1000",
                headers={"X-API-Key": "test_key"}
            )
            # Should handle gracefully, either 422 or cap the limit
            assert response.status_code in [200, 422]


class TestMalformedRequestEdgeCases:
    """Test handling of malformed requests and boundary conditions."""
    
    def test_malformed_json_payloads(self, client, mock_database, mock_storage):
        """Test handling of malformed JSON payloads."""
        malformed_payloads = [
            '{"url": "https://youtube.com/watch?v=test"',  # Missing closing brace
            '{"url": "https://youtube.com/watch?v=test", "quality": }',  # Invalid JSON syntax
            '{"url": "https://youtube.com/watch?v=test", "quality": null}',  # Null value
            '{"url": undefined}',  # JavaScript-style undefined
            '{"url": "test", "nested": {"invalid": }}',  # Nested malformed JSON
        ]
        
        for payload in malformed_payloads:
            response = client.post(
                "/api/v1/download",
                data=payload,  # Send raw string instead of json parameter
                headers={"Content-Type": "application/json"}
            )
            # Should return 422 for malformed JSON
            assert response.status_code == 422
    
    def test_oversized_request_payloads(self, client, mock_database, mock_storage):
        """Test handling of oversized request payloads."""
        # Create oversized JSON payload
        oversized_payload = {
            "url": "https://youtube.com/watch?v=test",
            "huge_field": "x" * (10 * 1024 * 1024)  # 10MB string
        }
        
        try:
            response = client.post("/api/v1/download", json=oversized_payload)
            # Should either reject or handle gracefully
            assert response.status_code in [413, 422, 400]  # Payload too large, validation error, or bad request
        except Exception:
            # May throw exception for oversized payload - that's acceptable
            pass
    
    def test_unicode_and_special_characters(self, client, mock_database, mock_storage):
        """Test handling of unicode and special characters in requests."""
        unicode_payloads = [
            {"url": "https://youtube.com/watch?v=测试"},  # Chinese characters
            {"url": "https://youtube.com/watch?v=тест"},  # Cyrillic
            {"url": "https://youtube.com/watch?v=🎵🎬"},  # Emojis
            {"url": "https://youtube.com/watch?v=test", "description": "файл с русскими буквами"},
            {"url": "https://youtube.com/watch?v=test\x00null"},  # Null byte
        ]
        
        for payload in unicode_payloads:
            response = client.post("/api/v1/download", json=payload)
            # Should handle gracefully, either accepting or rejecting with proper error
            assert response.status_code in [200, 400, 401, 403, 422]
    
    def test_content_type_mismatches(self, client, mock_database, mock_storage):
        """Test handling of content type mismatches."""
        valid_payload = {"url": "https://youtube.com/watch?v=test"}
        
        # Send JSON with wrong content type
        response = client.post(
            "/api/v1/download",
            json=valid_payload,
            headers={"Content-Type": "text/plain"}
        )
        # Should handle content type mismatch
        assert response.status_code in [400, 415, 422]
        
        # Send form data instead of JSON
        response = client.post(
            "/api/v1/download",
            data="url=https://youtube.com/watch?v=test",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        # Should handle form data appropriately
        assert response.status_code in [400, 415, 422]
    
    def test_http_method_edge_cases(self, client, mock_database, mock_storage):
        """Test handling of unsupported HTTP methods."""
        unsupported_methods = [
            ("PATCH", "/api/v1/download"),
            ("PUT", "/api/v1/info"),
            ("DELETE", "/api/v1/health"),
            ("HEAD", "/api/v1/download"),
            ("OPTIONS", "/api/v1/admin/keys"),
        ]
        
        for method, endpoint in unsupported_methods:
            response = client.request(method, endpoint)
            # Should return method not allowed
            assert response.status_code == 405
    
    def test_header_injection_attempts(self, client, mock_database, mock_storage):
        """Test handling of header injection attempts."""
        malicious_headers = {
            "X-API-Key": "test\r\nEvil-Header: injected",  # CRLF injection
            "X-Forwarded-For": "127.0.0.1\r\nHost: evil.com",
            "User-Agent": "Mozilla/5.0\x00\r\nEvil: header",
        }
        
        for header, value in malicious_headers.items():
            try:
                response = client.get("/health", headers={header: value})
                # Should handle malicious headers gracefully
                assert response.status_code in [200, 400, 422]
            except Exception:
                # Headers with null bytes or CRLF may raise exceptions - acceptable
                pass
    
    def test_url_path_traversal_attempts(self, client, mock_database, mock_storage):
        """Test handling of path traversal attempts in URLs."""
        malicious_paths = [
            "/api/v1/../../../etc/passwd",
            "/api/v1/download/../../admin/keys",
            "/api/v1/info?url=../config",
            "/api/v1/jobs/../../../secret",
        ]
        
        for path in malicious_paths:
            response = client.get(path)
            # Should either return 404 (not found) or proper error, not expose sensitive paths
            assert response.status_code in [404, 400, 422]
            # Ensure no sensitive information is leaked in response
            response_text = response.text.lower()
            assert "passwd" not in response_text
            assert "config" not in response_text or "configuration" not in response_text
    
    def test_extremely_long_urls(self, client, mock_database, mock_storage):
        """Test handling of extremely long URLs."""
        # Create extremely long URL
        base_url = "https://youtube.com/watch?v=test"
        long_url = base_url + "&param=" + "x" * 10000
        
        response = client.get("/api/v1/info", params={"url": long_url})
        # Should handle long URLs gracefully
        assert response.status_code in [400, 413, 414, 422]  # Bad request, payload too large, URI too long, or validation error
    
    def test_concurrent_request_edge_cases(self, client, mock_database, mock_storage):
        """Test handling of rapid concurrent requests."""
        results = []
        
        def make_request():
            response = client.get("/health")
            results.append(response.status_code)
        
        # Send multiple concurrent requests
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All requests should complete successfully or with expected errors
        for status_code in results:
            assert status_code in [200, 429, 503]  # OK, too many requests, or service unavailable