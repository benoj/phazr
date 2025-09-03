"""
Unit tests for prerequisite validators - focused on behavior verification.
"""
import asyncio
import tempfile
from unittest.mock import AsyncMock, patch

import pytest

from phazr.validators import (
    FileSystemValidator,
    KubernetesValidator,
    NetworkValidator,
    PrerequisiteValidator,
    ToolValidator,
    Validator,
)
from phazr.models import EnvironmentConfig


class MockValidator(Validator):
    """Mock validator for testing composite validator behavior."""

    def __init__(self, result):
        self.result = result

    async def validate(self):
        return self.result


class TestValidator:
    """Test base Validator abstract class."""

    def test_validator_cannot_be_instantiated_directly(self):
        """Test that Validator is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            Validator()


class TestToolValidator:
    """Test ToolValidator behavior for checking tool availability."""

    def test_tool_validator_configures_version_command_automatically(self):
        """Test that ToolValidator automatically configures version command."""
        validator = ToolValidator("kubectl")
        assert validator.tool_name == "kubectl"
        assert validator.version_command == "kubectl --version"

    def test_tool_validator_accepts_custom_version_command(self):
        """Test that ToolValidator accepts custom version command."""
        validator = ToolValidator("python", "python --version")
        assert validator.tool_name == "python"
        assert validator.version_command == "python --version"

    @pytest.mark.asyncio
    async def test_tool_validation_detects_available_tool(self):
        """Test that tool validation correctly identifies available tools."""
        validator = ToolValidator("echo")  # echo should be available on most systems

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"version 1.0\n", b"")
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"version 1.0\n", b"")):
                result = await validator.validate()

            assert result["status"] == "passed"
            assert result["tool"] == "echo"
            assert "version 1.0" in result["version"]
            assert "is available" in result["message"]

    @pytest.mark.asyncio
    async def test_tool_validation_handles_version_in_stderr(self):
        """Test that tool validation handles version output in stderr."""
        validator = ToolValidator("test-tool")

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"", b"version 2.0\n")
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"version 2.0\n")):
                result = await validator.validate()

            assert result["status"] == "passed"
            assert "version 2.0" in result["version"]

    @pytest.mark.asyncio
    async def test_tool_validation_detects_unavailable_tool(self):
        """Test that tool validation correctly identifies unavailable tools."""
        validator = ToolValidator("nonexistent-tool")

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"command not found")):
                result = await validator.validate()

            assert result["status"] == "failed"
            assert result["tool"] == "nonexistent-tool"
            assert "command failed" in result["message"]

    @pytest.mark.asyncio
    async def test_tool_validation_handles_timeout_gracefully(self):
        """Test that tool validation handles command timeouts gracefully."""
        validator = ToolValidator("slow-tool")

        with patch("asyncio.create_subprocess_shell"):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await validator.validate()

            assert result["status"] == "failed"
            assert result["tool"] == "slow-tool"
            assert "timed out" in result["message"]

    @pytest.mark.asyncio
    async def test_tool_validation_handles_subprocess_errors(self):
        """Test that tool validation handles subprocess creation errors."""
        validator = ToolValidator("error-tool")

        with patch(
            "asyncio.create_subprocess_shell", side_effect=Exception("Process error")
        ):
            result = await validator.validate()

            assert result["status"] == "failed"
            assert result["tool"] == "error-tool"
            assert "Process error" in result["message"]


class TestKubernetesValidator:
    """Test KubernetesValidator behavior for checking Kubernetes connectivity."""

    def test_kubernetes_validator_initializes_with_namespace(self):
        """Test that KubernetesValidator properly initializes with required namespace."""
        validator = KubernetesValidator("test-ns")
        assert validator.namespace == "test-ns"
        assert validator.context is None

    def test_kubernetes_validator_accepts_custom_context(self):
        """Test that KubernetesValidator accepts custom context configuration."""
        validator = KubernetesValidator("test-ns", "test-context")
        assert validator.namespace == "test-ns"
        assert validator.context == "test-context"

    @pytest.mark.asyncio
    async def test_kubernetes_validation_passes_with_full_access(self):
        """Test that Kubernetes validation passes when all checks succeed."""
        validator = KubernetesValidator("test-ns", "test-context")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock all three checks to succeed
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"success", b"")):
                result = await validator.validate()

            assert result["status"] == "passed"
            assert len(result["checks"]) == 3
            assert all(check["passed"] for check in result["checks"])

    @pytest.mark.asyncio
    async def test_kubernetes_validation_fails_on_cluster_connectivity_issues(self):
        """Test that Kubernetes validation fails when cluster is unreachable."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"connection refused")):
                result = await validator.validate()

            assert result["status"] == "failed"
            assert len(result["checks"]) == 1
            assert not result["checks"][0]["passed"]
            assert "Cannot connect to cluster" in result["checks"][0]["message"]

    @pytest.mark.asyncio
    async def test_kubernetes_validation_handles_cluster_connection_exceptions(self):
        """Test that Kubernetes validation handles cluster connection exceptions."""
        validator = KubernetesValidator("test-ns")

        with patch(
            "asyncio.create_subprocess_exec", side_effect=Exception("Network error")
        ):
            result = await validator.validate()

            assert result["status"] == "failed"
            assert len(result["checks"]) == 1
            assert not result["checks"][0]["passed"]
            assert "Network error" in result["checks"][0]["message"]

    @pytest.mark.asyncio
    async def test_kubernetes_validation_continues_on_namespace_access_issues(self):
        """Test that Kubernetes validation continues when namespace access fails."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # First call (cluster-info) succeeds, second (namespace) fails, third (permissions) succeeds
            success_process = AsyncMock()
            success_process.returncode = 0
            
            fail_process = AsyncMock()
            fail_process.returncode = 1

            mock_subprocess.side_effect = [success_process, fail_process, success_process]

            with patch("asyncio.wait_for", side_effect=[
                (b"cluster ok", b""),
                (b"", b"namespace not found"),
            ]):
                result = await validator.validate()

            # Should be warning (not failed) since namespace is non-critical
            assert result["status"] == "warning"
            assert len(result["checks"]) == 3

    @pytest.mark.asyncio
    async def test_kubernetes_validation_gracefully_handles_permission_check_failures(self):
        """Test that permission check failures are handled gracefully."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # First two succeed, third fails
            success_process = AsyncMock()
            success_process.returncode = 0
            
            fail_process = AsyncMock()
            fail_process.returncode = 1

            mock_subprocess.side_effect = [success_process, success_process, fail_process]

            with patch("asyncio.wait_for", side_effect=[
                (b"ok", b""),
                (b"ok", b""),
            ]):
                result = await validator.validate()

            assert result["status"] == "warning"
            assert len(result["checks"]) == 3
            assert not result["checks"][2]["passed"]  # permissions check failed

    @pytest.mark.asyncio
    async def test_kubernetes_validation_skips_permission_check_on_exception(self):
        """Test that permission check exceptions are handled non-critically."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            success_process = AsyncMock()
            success_process.returncode = 0

            def side_effect(*args, **kwargs):
                if "auth" in args and "can-i" in args:
                    raise Exception("Auth error")
                return success_process

            mock_subprocess.side_effect = side_effect

            with patch("asyncio.wait_for", side_effect=[
                (b"ok", b""),
                (b"ok", b""),
            ]):
                result = await validator.validate()

            # Should still pass because permissions check is non-critical
            assert result["status"] == "passed"
            assert len(result["checks"]) == 2  # Only cluster and namespace checks


class TestFileSystemValidator:
    """Test FileSystemValidator behavior for checking file system requirements."""

    def test_filesystem_validator_initializes_with_empty_paths(self):
        """Test that FileSystemValidator initializes with empty path list by default."""
        validator = FileSystemValidator()
        assert validator.required_paths == []

    def test_filesystem_validator_accepts_custom_paths(self):
        """Test that FileSystemValidator accepts custom required paths."""
        paths = ["/tmp", "/usr/bin"]
        validator = FileSystemValidator(paths)
        assert validator.required_paths == paths

    @pytest.mark.asyncio
    async def test_filesystem_validation_passes_with_existing_paths(self):
        """Test that filesystem validation passes when all paths exist."""
        # Use paths that should exist on most systems
        validator = FileSystemValidator(["/tmp", "/usr"])

        result = await validator.validate()

        assert result["status"] == "passed"
        assert len(result["paths"]) == 2
        assert all(path_info["exists"] for path_info in result["paths"])

    @pytest.mark.asyncio
    async def test_filesystem_validation_warns_on_missing_paths(self):
        """Test that filesystem validation warns when some paths don't exist."""
        validator = FileSystemValidator(["/tmp", "/nonexistent/path/that/should/not/exist"])

        result = await validator.validate()

        assert result["status"] == "warning"
        assert len(result["paths"]) == 2
        
        # Find the existing and missing paths
        existing = next(p for p in result["paths"] if p["path"] == "/tmp")
        missing = next(p for p in result["paths"] if p["path"] == "/nonexistent/path/that/should/not/exist")
        
        assert existing["exists"] is True
        assert existing["type"] == "directory"
        assert missing["exists"] is False
        assert "does not exist" in missing["message"]

    @pytest.mark.asyncio
    async def test_filesystem_validation_distinguishes_files_from_directories(self):
        """Test that filesystem validation correctly identifies files vs directories."""
        with tempfile.NamedTemporaryFile() as tmp_file:
            validator = FileSystemValidator([tmp_file.name, "/tmp"])

            result = await validator.validate()

            assert result["status"] == "passed"

            file_info = next(p for p in result["paths"] if p["path"] == tmp_file.name)
            dir_info = next(p for p in result["paths"] if p["path"] == "/tmp")

            assert file_info["type"] == "file"
            assert dir_info["type"] == "directory"

    @pytest.mark.asyncio
    async def test_filesystem_validation_passes_with_empty_requirements(self):
        """Test that filesystem validation passes when no paths are required."""
        validator = FileSystemValidator()

        result = await validator.validate()

        assert result["status"] == "passed"
        assert result["paths"] == []


class TestNetworkValidator:
    """Test NetworkValidator behavior for checking network connectivity."""

    def test_network_validator_initializes_with_empty_endpoints(self):
        """Test that NetworkValidator initializes with empty endpoint list by default."""
        validator = NetworkValidator()
        assert validator.endpoints == []

    def test_network_validator_accepts_custom_endpoints(self):
        """Test that NetworkValidator accepts custom endpoint URLs."""
        endpoints = ["http://example.com", "https://google.com"]
        validator = NetworkValidator(endpoints)
        assert validator.endpoints == endpoints

    @pytest.mark.asyncio
    async def test_network_validation_detects_reachable_endpoints(self):
        """Test that network validation correctly identifies reachable endpoints."""
        validator = NetworkValidator(["http://example.com"])

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"200", b"")):
                result = await validator.validate()

            assert result["status"] == "passed"
            assert len(result["endpoints"]) == 1
            assert result["endpoints"][0]["reachable"] is True
            assert result["endpoints"][0]["status_code"] == "200"

    @pytest.mark.asyncio
    async def test_network_validation_detects_unreachable_endpoints(self):
        """Test that network validation correctly identifies unreachable endpoints."""
        validator = NetworkValidator(["http://unreachable.invalid"])

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"connection failed")):
                result = await validator.validate()

            assert result["status"] == "warning"
            assert len(result["endpoints"]) == 1
            assert result["endpoints"][0]["reachable"] is False
            assert "not reachable" in result["endpoints"][0]["message"]

    @pytest.mark.asyncio
    async def test_network_validation_handles_connection_exceptions(self):
        """Test that network validation handles connection exceptions gracefully."""
        validator = NetworkValidator(["http://error.test"])

        with patch(
            "asyncio.create_subprocess_exec", side_effect=Exception("Network error")
        ):
            result = await validator.validate()

            assert result["status"] == "warning"
            assert len(result["endpoints"]) == 1
            assert result["endpoints"][0]["reachable"] is False
            assert "Network error" in result["endpoints"][0]["message"]

    @pytest.mark.asyncio
    async def test_network_validation_aggregates_mixed_results(self):
        """Test that network validation properly aggregates mixed endpoint results."""
        validator = NetworkValidator(["http://good.test", "http://bad.test"])

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            good_process = AsyncMock()
            good_process.returncode = 0
            
            bad_process = AsyncMock()
            bad_process.returncode = 1

            mock_subprocess.side_effect = [good_process, bad_process]

            with patch("asyncio.wait_for", side_effect=[
                (b"200", b""),
                (b"", b"error"),
            ]):
                result = await validator.validate()

            assert result["status"] == "warning"  # Due to one failure
            assert len(result["endpoints"]) == 2

    @pytest.mark.asyncio
    async def test_network_validation_passes_with_empty_endpoints(self):
        """Test that network validation passes when no endpoints are configured."""
        validator = NetworkValidator()

        result = await validator.validate()

        assert result["status"] == "passed"
        assert result["endpoints"] == []


class TestPrerequisiteValidator:
    """Test PrerequisiteValidator behavior for orchestrating multiple validation checks."""

    def test_prerequisite_validator_initializes_empty(self):
        """Test that PrerequisiteValidator initializes with empty validator list."""
        validator = PrerequisiteValidator()
        assert validator.validators == []

    def test_prerequisite_validator_accepts_custom_validators(self):
        """Test that PrerequisiteValidator accepts custom validator implementations."""
        main_validator = PrerequisiteValidator()
        custom_validator = MockValidator({"status": "passed"})

        main_validator.add_validator(custom_validator)

        assert len(main_validator.validators) == 1
        assert main_validator.validators[0] == custom_validator

    @pytest.mark.asyncio
    async def test_prerequisite_validation_passes_with_no_requirements(self):
        """Test that prerequisite validation passes when no tools or validators are required."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        result = await validator.validate(environment)

        assert result["all_passed"] is True
        assert result["has_warnings"] is False
        assert result["results"] == []
        assert "successfully" in result["summary"]

    @pytest.mark.asyncio
    async def test_prerequisite_validation_creates_tool_validators_for_required_tools(self):
        """Test that prerequisite validation automatically creates validators for required tools."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator, "validate", return_value={"status": "passed", "tool": "echo"}
        ):
            result = await validator.validate(environment, required_tools=["echo"])

        assert result["all_passed"] is True
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_prerequisite_validation_includes_kubernetes_validator_for_kubectl(self):
        """Test that prerequisite validation includes Kubernetes validation when kubectl is required."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator, "validate", return_value={"status": "passed", "tool": "kubectl"}
        ), patch.object(
            KubernetesValidator, "validate", return_value={"status": "passed", "checks": []}
        ):
            result = await validator.validate(environment, required_tools=["kubectl"])

        assert result["all_passed"] is True
        assert len(result["results"]) == 2  # Tool + Kubernetes validator

    @pytest.mark.asyncio
    async def test_prerequisite_validation_aggregates_failures_correctly(self):
        """Test that prerequisite validation correctly identifies and reports failures."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator, "validate", return_value={"status": "failed", "tool": "missing"}
        ):
            result = await validator.validate(environment, required_tools=["missing"])

        assert result["all_passed"] is False
        assert result["has_warnings"] is False
        assert "failed" in result["summary"]

    @pytest.mark.asyncio
    async def test_prerequisite_validation_distinguishes_warnings_from_failures(self):
        """Test that prerequisite validation properly handles warnings vs failures."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator, "validate", return_value={"status": "warning", "tool": "partial"}
        ):
            result = await validator.validate(environment, required_tools=["partial"])

        assert result["all_passed"] is True  # Warnings don't fail validation
        assert result["has_warnings"] is True
        assert "warnings" in result["summary"]

    @pytest.mark.asyncio
    async def test_prerequisite_validation_executes_custom_validators(self):
        """Test that prerequisite validation executes custom validators alongside built-in ones."""
        main_validator = PrerequisiteValidator()
        custom_validator = MockValidator({"status": "passed", "custom": True})
        main_validator.add_validator(custom_validator)

        environment = EnvironmentConfig(name="test", namespace="test-ns")

        result = await main_validator.validate(environment)

        assert result["all_passed"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["custom"] is True

    @pytest.mark.asyncio
    async def test_prerequisite_validation_handles_mixed_validation_results(self):
        """Test that prerequisite validation correctly aggregates mixed validation results."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        # Add validators with different results
        validator.add_validator(MockValidator({"status": "passed"}))
        validator.add_validator(MockValidator({"status": "warning"}))
        validator.add_validator(MockValidator({"status": "failed"}))

        result = await validator.validate(environment)

        assert result["all_passed"] is False  # Due to failure
        assert result["has_warnings"] is True  # Due to warning
        assert len(result["results"]) == 3
        assert "failed" in result["summary"]

    def test_prerequisite_validation_generates_accurate_summaries(self):
        """Test that prerequisite validation generates accurate summary messages."""
        validator = PrerequisiteValidator()

        # Test all passed
        all_passed = [{"status": "passed"}, {"status": "passed"}]
        summary = validator._generate_summary(all_passed)
        assert "successfully" in summary

        # Test with failures
        with_failures = [{"status": "passed"}, {"status": "failed"}, {"status": "failed"}]
        summary = validator._generate_summary(with_failures)
        assert "2 prerequisites failed" in summary

        # Test warnings only
        warnings_only = [{"status": "passed"}, {"status": "warning"}]
        summary = validator._generate_summary(warnings_only)
        assert "1 warnings" in summary