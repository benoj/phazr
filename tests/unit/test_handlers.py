"""
Unit tests for phazr.handlers module.
"""

import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import pytest
from aioresponses import aioresponses

from phazr.models import Operation, ExecutionResult, EnvironmentConfig, OperationType
from phazr.handlers import (
    OperationHandler,
    ScriptHandler,
    KubectlExecHandler,
    KubectlRestartHandler,
    KubectlApplyHandler,
    HttpRequestHandler,
    HandlerRegistry
)
from tests.utils.test_helpers import MockProcess


class TestOperationHandler:
    """Test abstract OperationHandler class."""
    
    def test_abstract_handler_cannot_be_instantiated(self):
        """Test that abstract handler cannot be instantiated."""
        with pytest.raises(TypeError):
            OperationHandler()
    
    def test_custom_handler_implementation(self):
        """Test that custom handlers can implement the interface."""
        class CustomHandler(OperationHandler):
            async def execute(self, operation, environment):
                return ExecutionResult(operation=operation, success=True)
        
        handler = CustomHandler()
        assert isinstance(handler, OperationHandler)


class TestScriptHandler:
    """Test ScriptHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create ScriptHandler instance."""
        return ScriptHandler()
    
    @pytest.fixture
    def sample_operation(self):
        """Sample script operation."""
        return Operation(
            command="echo 'Hello World'",
            description="Test echo command",
            type=OperationType.SCRIPT_EXEC,
            timeout=30
        )
    
    @pytest.fixture
    def sample_environment(self):
        """Sample environment config."""
        return EnvironmentConfig(
            name="test",
            namespace="default",
            context="test-cluster"
        )
    
    @pytest.mark.asyncio
    async def test_successful_script_execution(self, handler, sample_operation, sample_environment):
        """Test successful script execution."""
        mock_process = MockProcess(
            returncode=0,
            stdout=b"Hello World\n",
            stderr=b""
        )
        
        with patch("asyncio.create_subprocess_shell", return_value=mock_process) as mock_create:
            with patch("asyncio.wait_for", return_value=(b"Hello World\n", b"")):
                result = await handler.execute(sample_operation, sample_environment)
        
        assert result.success is True
        assert result.output == "Hello World\n"
        assert result.error is None
        assert result.operation == sample_operation
        
        # Verify subprocess was called correctly
        mock_create.assert_called_once_with(
            sample_operation.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=handler._prepare_environment(sample_operation, sample_environment)
        )
    
    @pytest.mark.asyncio
    async def test_failed_script_execution(self, handler, sample_operation, sample_environment):
        """Test failed script execution."""
        mock_process = MockProcess(
            returncode=1,
            stdout=b"",
            stderr=b"Command failed\n"
        )
        
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"", b"Command failed\n")):
                result = await handler.execute(sample_operation, sample_environment)
        
        assert result.success is False
        assert result.output == ""
        assert result.error == "Command failed\n"
    
    @pytest.mark.asyncio
    async def test_script_timeout(self, handler, sample_operation, sample_environment):
        """Test script execution timeout."""
        mock_process = MockProcess()
        mock_process.kill = AsyncMock()
        mock_process.wait = AsyncMock()
        
        with patch("asyncio.create_subprocess_shell", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await handler.execute(sample_operation, sample_environment)
        
        assert result.success is False
        assert "timed out" in result.error
        mock_process.kill.assert_called_once()
        mock_process.wait.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_script_exception_handling(self, handler, sample_operation, sample_environment):
        """Test exception handling in script execution."""
        with patch("asyncio.create_subprocess_shell", side_effect=OSError("Permission denied")):
            result = await handler.execute(sample_operation, sample_environment)
        
        assert result.success is False
        assert result.error == "Permission denied"
    
    def test_prepare_environment(self, handler, sample_operation, sample_environment):
        """Test environment variable preparation."""
        sample_operation.metadata = {"priority": "high", "team": "backend"}
        
        with patch("os.environ", {"PATH": "/usr/bin", "HOME": "/home/user"}):
            env = handler._prepare_environment(sample_operation, sample_environment)
        
        # Check original env vars are preserved
        assert env["PATH"] == "/usr/bin"
        assert env["HOME"] == "/home/user"
        
        # Check added environment variables
        assert env["NAMESPACE"] == "default"
        assert env["ENVIRONMENT"] == "test"
        assert env["KUBE_CONTEXT"] == "test-cluster"
        
        # Check operation metadata as env vars
        assert env["OP_PRIORITY"] == "high"
        assert env["OP_TEAM"] == "backend"
    
    def test_prepare_environment_with_operation_namespace(self, handler, sample_environment):
        """Test environment preparation with operation-specific namespace."""
        operation = Operation(
            command="echo test",
            description="Test",
            type=OperationType.SCRIPT_EXEC,
            namespace="custom-ns"
        )
        
        with patch("os.environ", {}):
            env = handler._prepare_environment(operation, sample_environment)
        
        assert env["NAMESPACE"] == "custom-ns"


class TestKubectlExecHandler:
    """Test KubectlExecHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create KubectlExecHandler instance."""
        return KubectlExecHandler()
    
    @pytest.fixture
    def kubectl_operation(self):
        """Sample kubectl exec operation."""
        return Operation(
            command="ls -la",
            description="List files",
            type=OperationType.KUBECTL_EXEC,
            service="web-app",
            container="app",
            timeout=60
        )
    
    @pytest.fixture
    def sample_environment(self):
        """Sample environment config."""
        return EnvironmentConfig(
            name="production",
            namespace="prod",
            context="prod-cluster"
        )
    
    @pytest.mark.asyncio
    async def test_successful_kubectl_exec(self, handler, kubectl_operation, sample_environment):
        """Test successful kubectl exec."""
        mock_process = MockProcess(
            returncode=0,
            stdout=b"total 4\ndrwxr-xr-x 2 root root 4096 Jan  1 12:00 .\n",
            stderr=b""
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create:
            with patch("asyncio.wait_for", return_value=(mock_process.stdout.data, b"")):
                result = await handler.execute(kubectl_operation, sample_environment)
        
        assert result.success is True
        assert "total 4" in result.output
        assert result.error is None
        
        # Verify kubectl command construction
        expected_cmd = [
            "kubectl", "--context", "prod-cluster", "exec", "-n", "prod",
            "web-app", "-c", "app", "--", "sh", "-c", "ls -la"
        ]
        mock_create.assert_called_once_with(
            *expected_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    
    @pytest.mark.asyncio
    async def test_kubectl_exec_without_container(self, handler, sample_environment):
        """Test kubectl exec without container specification."""
        operation = Operation(
            command="ps aux",
            description="List processes",
            type=OperationType.KUBECTL_EXEC,
            service="web-app"
        )
        
        mock_process = MockProcess(returncode=0, stdout=b"PID USER\n")
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create:
            with patch("asyncio.wait_for", return_value=(b"PID USER\n", b"")):
                result = await handler.execute(operation, sample_environment)
        
        # Verify container flag is not included
        expected_cmd = [
            "kubectl", "--context", "prod-cluster", "exec", "-n", "prod",
            "web-app", "--", "sh", "-c", "ps aux"
        ]
        mock_create.assert_called_once_with(
            *expected_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    
    @pytest.mark.asyncio
    async def test_kubectl_exec_missing_service(self, handler, sample_environment):
        """Test kubectl exec with missing service name."""
        operation = Operation(
            command="ls",
            description="List files",
            type=OperationType.KUBECTL_EXEC
        )
        
        result = await handler.execute(operation, sample_environment)
        
        assert result.success is False
        assert "Service name required" in result.error
    
    @pytest.mark.asyncio
    async def test_kubectl_exec_timeout(self, handler, kubectl_operation, sample_environment):
        """Test kubectl exec timeout."""
        mock_process = MockProcess()
        mock_process.kill = AsyncMock()
        mock_process.wait = AsyncMock()
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await handler.execute(kubectl_operation, sample_environment)
        
        assert result.success is False
        assert "timed out" in result.error


class TestKubectlRestartHandler:
    """Test KubectlRestartHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create KubectlRestartHandler instance."""
        return KubectlRestartHandler()
    
    @pytest.fixture
    def restart_operation(self):
        """Sample restart operation."""
        return Operation(
            command="",  # Not used for restart
            description="Restart web app",
            type=OperationType.KUBECTL_RESTART,
            service="web-app",
            wait_for_ready=True,
            timeout=300
        )
    
    @pytest.fixture
    def sample_environment(self):
        """Sample environment config."""
        return EnvironmentConfig(
            name="staging",
            namespace="staging",
            context="staging-cluster"
        )
    
    @pytest.mark.asyncio
    async def test_successful_restart(self, handler, restart_operation, sample_environment):
        """Test successful deployment restart."""
        mock_process = MockProcess(
            returncode=0,
            stdout=b"deployment.apps/web-app restarted\n"
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create:
            with patch.object(handler, "_wait_for_ready", return_value=None) as mock_wait:
                result = await handler.execute(restart_operation, sample_environment)
        
        assert result.success is True
        assert "restarted" in result.output
        
        # Verify restart command
        expected_cmd = [
            "kubectl", "--context", "staging-cluster", "rollout", "restart",
            "deployment", "web-app", "-n", "staging"
        ]
        mock_create.assert_called_once_with(
            *expected_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Verify wait for ready was called
        mock_wait.assert_called_once_with(
            "web-app", "staging", "staging-cluster", 300
        )
    
    @pytest.mark.asyncio
    async def test_restart_without_wait_for_ready(self, handler, sample_environment):
        """Test restart without waiting for ready."""
        operation = Operation(
            command="",
            description="Quick restart",
            type=OperationType.KUBECTL_RESTART,
            service="api",
            wait_for_ready=False
        )
        
        mock_process = MockProcess(returncode=0, stdout=b"deployment.apps/api restarted\n")
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch.object(handler, "_wait_for_ready") as mock_wait:
                result = await handler.execute(operation, sample_environment)
        
        assert result.success is True
        mock_wait.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_restart_failure(self, handler, restart_operation, sample_environment):
        """Test failed restart."""
        mock_process = MockProcess(
            returncode=1,
            stderr=b"deployment 'web-app' not found"
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await handler.execute(restart_operation, sample_environment)
        
        assert result.success is False
        assert "not found" in result.error
    
    @pytest.mark.asyncio
    async def test_wait_for_ready_success(self, handler):
        """Test successful wait for ready."""
        mock_process = MockProcess(returncode=0)
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            # Should not raise exception
            await handler._wait_for_ready("web-app", "default", "test-context", 300)
    
    @pytest.mark.asyncio
    async def test_wait_for_ready_timeout(self, handler):
        """Test wait for ready timeout."""
        mock_process = MockProcess(returncode=1)
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with pytest.raises(Exception, match="did not become ready"):
                await handler._wait_for_ready("web-app", "default", None, 60)


class TestKubectlApplyHandler:
    """Test KubectlApplyHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create KubectlApplyHandler instance."""
        return KubectlApplyHandler()
    
    @pytest.fixture
    def apply_file_operation(self):
        """Sample apply operation with file path."""
        return Operation(
            command="manifests/deployment.yaml",
            description="Apply deployment manifest",
            type=OperationType.KUBECTL_APPLY,
            timeout=120
        )
    
    @pytest.fixture
    def apply_yaml_operation(self):
        """Sample apply operation with inline YAML."""
        return Operation(
            command="---\napiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n",
            description="Apply inline YAML",
            type=OperationType.KUBECTL_APPLY
        )
    
    @pytest.fixture
    def sample_environment(self):
        """Sample environment config."""
        return EnvironmentConfig(
            name="test",
            namespace="test-ns"
        )
    
    @pytest.mark.asyncio
    async def test_apply_from_file(self, handler, apply_file_operation, sample_environment):
        """Test applying from file path."""
        mock_process = MockProcess(
            returncode=0,
            stdout=b"deployment.apps/web-app created\n"
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create:
            result = await handler.execute(apply_file_operation, sample_environment)
        
        assert result.success is True
        assert "created" in result.output
        
        # Verify command construction
        expected_cmd = ["kubectl", "apply", "-n", "test-ns", "-f", "manifests/deployment.yaml"]
        mock_create.assert_called_once_with(
            *expected_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
    
    @pytest.mark.asyncio
    async def test_apply_inline_yaml(self, handler, apply_yaml_operation, sample_environment):
        """Test applying inline YAML."""
        mock_process = MockProcess(
            returncode=0,
            stdout=b"configmap/test created\n"
        )
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create:
            result = await handler.execute(apply_yaml_operation, sample_environment)
        
        assert result.success is True
        
        # Verify command uses stdin
        expected_cmd = ["kubectl", "apply", "-n", "test-ns", "-f", "-"]
        mock_create.assert_called_once()
        args, kwargs = mock_create.call_args
        assert list(args) == expected_cmd
        assert kwargs["stdin"] == asyncio.subprocess.PIPE
    
    @pytest.mark.asyncio
    async def test_apply_with_context(self, handler, apply_file_operation):
        """Test apply with Kubernetes context."""
        environment = EnvironmentConfig(
            name="prod",
            namespace="production",
            context="prod-cluster"
        )
        
        mock_process = MockProcess(returncode=0, stdout=b"applied\n")
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_create:
            result = await handler.execute(apply_file_operation, environment)
        
        # Verify context is included
        expected_cmd = [
            "kubectl", "--context", "prod-cluster", "apply", 
            "-n", "production", "-f", "manifests/deployment.yaml"
        ]
        mock_create.assert_called_once_with(
            *expected_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )


class TestHttpRequestHandler:
    """Test HttpRequestHandler class."""
    
    @pytest.fixture
    def handler(self):
        """Create HttpRequestHandler instance."""
        return HttpRequestHandler()
    
    @pytest.fixture
    def http_get_operation(self):
        """Sample HTTP GET operation."""
        return Operation(
            command='{"url": "http://api.example.com/health", "method": "GET"}',
            description="Health check API",
            type=OperationType.HTTP_REQUEST,
            timeout=30
        )
    
    @pytest.fixture
    def http_post_operation(self):
        """Sample HTTP POST operation."""
        return Operation(
            command='{"url": "http://api.example.com/deploy", "method": "POST", "data": {"version": "1.0.0"}}',
            description="Deploy API call",
            type=OperationType.HTTP_REQUEST,
            timeout=60
        )
    
    @pytest.fixture
    def sample_environment(self):
        """Sample environment config."""
        return EnvironmentConfig(name="test", namespace="default")
    
    @pytest.mark.asyncio
    async def test_successful_http_get(self, handler, http_get_operation, sample_environment):
        """Test successful HTTP GET request."""
        with aioresponses() as mock_responses:
            mock_responses.get("http://api.example.com/health", payload={"status": "ok"})
            
            result = await handler.execute(http_get_operation, sample_environment)
        
        assert result.success is True
        assert '{"status": "ok"}' in result.output
        assert result.metadata["status_code"] == 200
    
    @pytest.mark.asyncio
    async def test_successful_http_post(self, handler, http_post_operation, sample_environment):
        """Test successful HTTP POST request."""
        with aioresponses() as mock_responses:
            mock_responses.post(
                "http://api.example.com/deploy", 
                payload={"result": "success"},
                status=201
            )
            
            result = await handler.execute(http_post_operation, sample_environment)
        
        assert result.success is True
        assert result.metadata["status_code"] == 201
    
    @pytest.mark.asyncio
    async def test_http_error_response(self, handler, http_get_operation, sample_environment):
        """Test HTTP error response."""
        with aioresponses() as mock_responses:
            mock_responses.get("http://api.example.com/health", status=500, payload={"error": "Internal server error"})
            
            result = await handler.execute(http_get_operation, sample_environment)
        
        assert result.success is False
        assert result.error == "HTTP 500"
        assert result.metadata["status_code"] == 500
    
    @pytest.mark.asyncio
    async def test_invalid_json_command(self, handler, sample_environment):
        """Test handling of invalid JSON in command."""
        operation = Operation(
            command='{"url": "http://example.com", "invalid": json}',  # Invalid JSON
            description="Invalid JSON test",
            type=OperationType.HTTP_REQUEST
        )
        
        result = await handler.execute(operation, sample_environment)
        
        assert result.success is False
        assert "Invalid JSON" in result.error
    
    @pytest.mark.asyncio
    async def test_http_connection_error(self, handler, http_get_operation, sample_environment):
        """Test HTTP connection error."""
        # No mock response - will cause connection error
        result = await handler.execute(http_get_operation, sample_environment)
        
        assert result.success is False
        assert result.error is not None


class TestHandlerRegistry:
    """Test HandlerRegistry class."""
    
    @pytest.fixture
    def registry(self):
        """Create HandlerRegistry instance."""
        return HandlerRegistry()
    
    @pytest.fixture
    def mock_handler(self):
        """Create mock handler."""
        handler = Mock(spec=OperationHandler)
        handler.execute = AsyncMock()
        return handler
    
    def test_register_handler(self, registry, mock_handler):
        """Test registering a handler."""
        registry.register(OperationType.SCRIPT_EXEC, mock_handler)
        
        retrieved = registry.get_handler(OperationType.SCRIPT_EXEC)
        assert retrieved == mock_handler
    
    def test_get_nonexistent_handler(self, registry):
        """Test getting handler that doesn't exist."""
        handler = registry.get_handler(OperationType.CUSTOM)
        assert handler is None
    
    def test_unregister_handler(self, registry, mock_handler):
        """Test unregistering a handler."""
        registry.register(OperationType.HTTP_REQUEST, mock_handler)
        assert registry.get_handler(OperationType.HTTP_REQUEST) == mock_handler
        
        registry.unregister(OperationType.HTTP_REQUEST)
        assert registry.get_handler(OperationType.HTTP_REQUEST) is None
    
    def test_unregister_nonexistent_handler(self, registry):
        """Test unregistering handler that doesn't exist."""
        # Should not raise exception
        registry.unregister(OperationType.CUSTOM)
    
    def test_multiple_handlers(self, registry):
        """Test registering multiple handlers."""
        script_handler = Mock(spec=OperationHandler)
        http_handler = Mock(spec=OperationHandler)
        
        registry.register(OperationType.SCRIPT_EXEC, script_handler)
        registry.register(OperationType.HTTP_REQUEST, http_handler)
        
        assert registry.get_handler(OperationType.SCRIPT_EXEC) == script_handler
        assert registry.get_handler(OperationType.HTTP_REQUEST) == http_handler
    
    def test_handler_replacement(self, registry):
        """Test replacing an existing handler."""
        old_handler = Mock(spec=OperationHandler)
        new_handler = Mock(spec=OperationHandler)
        
        registry.register(OperationType.KUBECTL_EXEC, old_handler)
        registry.register(OperationType.KUBECTL_EXEC, new_handler)
        
        # Should return the new handler
        assert registry.get_handler(OperationType.KUBECTL_EXEC) == new_handler