"""
Unit tests for prerequisite validators.
"""

import asyncio
from unittest.mock import AsyncMock, patch
from typing import Dict, Any

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
    """Mock validator for testing."""

    def __init__(self, result: Dict[str, Any]):
        self.result = result

    async def validate(self) -> Dict[str, Any]:
        return self.result


class TestValidator:
    """Test base Validator class."""

    def test_validator_is_abstract(self):
        """Test that Validator is abstract."""
        with pytest.raises(TypeError):
            Validator()


class TestToolValidator:
    """Test ToolValidator class."""

    def test_init_default_version_command(self):
        """Test initialization with default version command."""
        validator = ToolValidator("kubectl")
        assert validator.tool_name == "kubectl"
        assert validator.version_command == "kubectl --version"

    def test_init_custom_version_command(self):
        """Test initialization with custom version command."""
        validator = ToolValidator("python", "python --version")
        assert validator.tool_name == "python"
        assert validator.version_command == "python --version"

    @pytest.mark.asyncio
    async def test_validate_success(self):
        """Test successful tool validation."""
        validator = ToolValidator("echo")

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
    async def test_validate_success_stderr_version(self):
        """Test successful tool validation with version in stderr."""
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
    async def test_validate_command_failed(self):
        """Test tool validation with command failure."""
        validator = ToolValidator("nonexistent")

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"command not found")
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"command not found")):
                result = await validator.validate()

            assert result["status"] == "failed"
            assert result["tool"] == "nonexistent"
            assert "command failed" in result["message"]

    @pytest.mark.asyncio
    async def test_validate_timeout(self):
        """Test tool validation timeout."""
        validator = ToolValidator("slow-tool")

        with patch("asyncio.create_subprocess_shell"):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                result = await validator.validate()

            assert result["status"] == "failed"
            assert result["tool"] == "slow-tool"
            assert "timed out" in result["message"]

    @pytest.mark.asyncio
    async def test_validate_exception(self):
        """Test tool validation with exception."""
        validator = ToolValidator("error-tool")

        with patch(
            "asyncio.create_subprocess_shell", side_effect=Exception("Process error")
        ):
            result = await validator.validate()

            assert result["status"] == "failed"
            assert result["tool"] == "error-tool"
            assert "Process error" in result["message"]


class TestKubernetesValidator:
    """Test KubernetesValidator class."""

    def test_init_without_context(self):
        """Test initialization without context."""
        validator = KubernetesValidator("test-ns")
        assert validator.namespace == "test-ns"
        assert validator.context is None

    def test_init_with_context(self):
        """Test initialization with context."""
        validator = KubernetesValidator("test-ns", "test-context")
        assert validator.namespace == "test-ns"
        assert validator.context == "test-context"

    @pytest.mark.asyncio
    async def test_validate_all_success(self):
        """Test successful Kubernetes validation."""
        validator = KubernetesValidator("test-ns", "test-context")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Mock successful cluster-info
            mock_process1 = AsyncMock()
            mock_process1.returncode = 0
            mock_process1.communicate.return_value = (b"cluster info", b"")

            # Mock successful namespace check
            mock_process2 = AsyncMock()
            mock_process2.returncode = 0
            mock_process2.communicate.return_value = (b"namespace exists", b"")

            # Mock successful permissions check
            mock_process3 = AsyncMock()
            mock_process3.returncode = 0
            mock_process3.communicate.return_value = (b"yes", b"")

            mock_subprocess.side_effect = [mock_process1, mock_process2, mock_process3]

            with patch(
                "asyncio.wait_for",
                side_effect=[
                    (b"cluster info", b""),
                    (b"namespace exists", b""),
                ],
            ):
                result = await validator.validate()

            assert result["status"] == "passed"
            assert len(result["checks"]) == 3
            assert all(check["passed"] for check in result["checks"])

    @pytest.mark.asyncio
    async def test_validate_cluster_connection_failed(self):
        """Test Kubernetes validation with cluster connection failure."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"connection refused")
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"connection refused")):
                result = await validator.validate()

            assert result["status"] == "failed"
            assert len(result["checks"]) == 1
            assert not result["checks"][0]["passed"]
            assert "Cannot connect to cluster" in result["checks"][0]["message"]

    @pytest.mark.asyncio
    async def test_validate_cluster_connection_exception(self):
        """Test Kubernetes validation with cluster connection exception."""
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
    async def test_validate_namespace_access_failed(self):
        """Test Kubernetes validation with namespace access failure."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Cluster connection succeeds
            mock_process1 = AsyncMock()
            mock_process1.returncode = 0
            mock_process1.communicate.return_value = (b"cluster ok", b"")

            # Namespace check fails
            mock_process2 = AsyncMock()
            mock_process2.returncode = 1
            mock_process2.communicate.return_value = (b"", b"namespace not found")

            # Permissions check succeeds
            mock_process3 = AsyncMock()
            mock_process3.returncode = 0
            mock_process3.communicate.return_value = (b"yes", b"")

            mock_subprocess.side_effect = [mock_process1, mock_process2, mock_process3]

            with patch(
                "asyncio.wait_for",
                side_effect=[
                    (b"cluster ok", b""),
                    (b"", b"namespace not found"),
                ],
            ):
                result = await validator.validate()

            assert result["status"] == "warning"  # Namespace failure is warning
            assert len(result["checks"]) == 3

    @pytest.mark.asyncio
    async def test_validate_namespace_access_exception(self):
        """Test Kubernetes validation with namespace access exception."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Cluster connection succeeds
            mock_process1 = AsyncMock()
            mock_process1.returncode = 0
            mock_process1.communicate.return_value = (b"cluster ok", b"")

            # Namespace check throws exception
            def side_effect(*args, **kwargs):
                if "get" in args and "namespace" in args:
                    raise Exception("Namespace error")
                return mock_process1

            mock_subprocess.side_effect = side_effect

            with patch(
                "asyncio.wait_for",
                side_effect=[
                    (b"cluster ok", b""),
                    Exception("Should not reach"),
                ],
            ):
                result = await validator.validate()

            assert result["status"] == "warning"

    @pytest.mark.asyncio
    async def test_validate_permissions_failed(self):
        """Test Kubernetes validation with permissions failure."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # Cluster and namespace succeed
            mock_process_ok = AsyncMock()
            mock_process_ok.returncode = 0
            mock_process_ok.communicate.return_value = (b"ok", b"")

            # Permissions fail
            mock_process_fail = AsyncMock()
            mock_process_fail.returncode = 1
            mock_process_fail.communicate.return_value = (b"no", b"")

            mock_subprocess.side_effect = [
                mock_process_ok,
                mock_process_ok,
                mock_process_fail,
            ]

            with patch(
                "asyncio.wait_for",
                side_effect=[
                    (b"ok", b""),
                    (b"ok", b""),
                ],
            ):
                result = await validator.validate()

            assert result["status"] == "warning"
            # Should have 3 checks: cluster, namespace, permissions
            assert len(result["checks"]) == 3
            assert not result["checks"][2]["passed"]  # permissions check failed

    @pytest.mark.asyncio
    async def test_validate_permissions_exception(self):
        """Test Kubernetes validation with permissions exception."""
        validator = KubernetesValidator("test-ns")

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # First two calls succeed
            mock_process_ok = AsyncMock()
            mock_process_ok.returncode = 0
            mock_process_ok.communicate.return_value = (b"ok", b"")

            def side_effect(*args, **kwargs):
                if "auth" in args and "can-i" in args:
                    raise Exception("Auth error")
                return mock_process_ok

            mock_subprocess.side_effect = side_effect

            with patch(
                "asyncio.wait_for",
                side_effect=[
                    (b"ok", b""),
                    (b"ok", b""),
                ],
            ):
                result = await validator.validate()

            # Should still pass because permissions check is non-critical
            assert result["status"] == "passed"
            # Should only have 2 checks since permissions check failed
            assert len(result["checks"]) == 2


class TestFileSystemValidator:
    """Test FileSystemValidator class."""

    def test_init_default_paths(self):
        """Test initialization with default paths."""
        validator = FileSystemValidator()
        assert validator.required_paths == []

    def test_init_custom_paths(self):
        """Test initialization with custom paths."""
        paths = ["/tmp", "/usr/bin"]
        validator = FileSystemValidator(paths)
        assert validator.required_paths == paths

    @pytest.mark.asyncio
    async def test_validate_existing_paths(self):
        """Test validation with existing paths."""
        validator = FileSystemValidator(["/tmp", "/usr"])

        result = await validator.validate()

        assert result["status"] == "passed"
        assert len(result["paths"]) == 2
        assert all(path_info["exists"] for path_info in result["paths"])

    @pytest.mark.asyncio
    async def test_validate_mixed_paths(self):
        """Test validation with mix of existing and non-existing paths."""
        validator = FileSystemValidator(["/tmp", "/nonexistent/path"])

        result = await validator.validate()

        assert result["status"] == "warning"
        assert len(result["paths"]) == 2

        # Find the existing path
        tmp_path = next(p for p in result["paths"] if p["path"] == "/tmp")
        assert tmp_path["exists"] is True
        assert tmp_path["type"] == "directory"

        # Find the non-existing path
        missing_path = next(
            p for p in result["paths"] if p["path"] == "/nonexistent/path"
        )
        assert missing_path["exists"] is False
        assert "does not exist" in missing_path["message"]

    @pytest.mark.asyncio
    async def test_validate_file_vs_directory(self):
        """Test validation distinguishes files from directories."""
        import tempfile

        with tempfile.NamedTemporaryFile() as tmp_file:
            validator = FileSystemValidator([tmp_file.name, "/tmp"])

            result = await validator.validate()

            assert result["status"] == "passed"

            # Find the file and directory
            file_info = next(p for p in result["paths"] if p["path"] == tmp_file.name)
            dir_info = next(p for p in result["paths"] if p["path"] == "/tmp")

            assert file_info["type"] == "file"
            assert dir_info["type"] == "directory"

    @pytest.mark.asyncio
    async def test_validate_empty_paths(self):
        """Test validation with no paths."""
        validator = FileSystemValidator()

        result = await validator.validate()

        assert result["status"] == "passed"
        assert result["paths"] == []


class TestNetworkValidator:
    """Test NetworkValidator class."""

    def test_init_default_endpoints(self):
        """Test initialization with default endpoints."""
        validator = NetworkValidator()
        assert validator.endpoints == []

    def test_init_custom_endpoints(self):
        """Test initialization with custom endpoints."""
        endpoints = ["http://example.com", "https://google.com"]
        validator = NetworkValidator(endpoints)
        assert validator.endpoints == endpoints

    @pytest.mark.asyncio
    async def test_validate_reachable_endpoint(self):
        """Test validation with reachable endpoint."""
        validator = NetworkValidator(["http://example.com"])

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate.return_value = (b"200", b"")
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"200", b"")):
                result = await validator.validate()

            assert result["status"] == "passed"
            assert len(result["endpoints"]) == 1
            assert result["endpoints"][0]["reachable"] is True
            assert result["endpoints"][0]["status_code"] == "200"

    @pytest.mark.asyncio
    async def test_validate_unreachable_endpoint(self):
        """Test validation with unreachable endpoint."""
        validator = NetworkValidator(["http://unreachable.invalid"])

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b"", b"connection failed")
            mock_subprocess.return_value = mock_process

            with patch("asyncio.wait_for", return_value=(b"", b"connection failed")):
                result = await validator.validate()

            assert result["status"] == "warning"
            assert len(result["endpoints"]) == 1
            assert result["endpoints"][0]["reachable"] is False
            assert "not reachable" in result["endpoints"][0]["message"]

    @pytest.mark.asyncio
    async def test_validate_endpoint_exception(self):
        """Test validation with endpoint exception."""
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
    async def test_validate_mixed_endpoints(self):
        """Test validation with mix of reachable and unreachable endpoints."""
        validator = NetworkValidator(["http://good.test", "http://bad.test"])

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            # First call succeeds, second fails
            mock_process_good = AsyncMock()
            mock_process_good.returncode = 0
            mock_process_good.communicate.return_value = (b"200", b"")

            mock_process_bad = AsyncMock()
            mock_process_bad.returncode = 1
            mock_process_bad.communicate.return_value = (b"", b"error")

            mock_subprocess.side_effect = [mock_process_good, mock_process_bad]

            with patch(
                "asyncio.wait_for",
                side_effect=[
                    (b"200", b""),
                    (b"", b"error"),
                ],
            ):
                result = await validator.validate()

            assert result["status"] == "warning"  # Due to one failure
            assert len(result["endpoints"]) == 2

    @pytest.mark.asyncio
    async def test_validate_empty_endpoints(self):
        """Test validation with no endpoints."""
        validator = NetworkValidator()

        result = await validator.validate()

        assert result["status"] == "passed"
        assert result["endpoints"] == []


class TestPrerequisiteValidator:
    """Test PrerequisiteValidator class."""

    def test_init(self):
        """Test initialization."""
        validator = PrerequisiteValidator()
        assert validator.validators == []

    def test_add_validator(self):
        """Test adding custom validator."""
        main_validator = PrerequisiteValidator()
        custom_validator = MockValidator({"status": "passed"})

        main_validator.add_validator(custom_validator)

        assert len(main_validator.validators) == 1
        assert main_validator.validators[0] == custom_validator

    @pytest.mark.asyncio
    async def test_validate_no_tools(self):
        """Test validation with no required tools."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        result = await validator.validate(environment)

        assert result["all_passed"] is True
        assert result["has_warnings"] is False
        assert result["results"] == []
        assert "successfully" in result["summary"]

    @pytest.mark.asyncio
    async def test_validate_with_tools(self):
        """Test validation with required tools."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator, "validate", return_value={"status": "passed", "tool": "echo"}
        ):
            result = await validator.validate(environment, required_tools=["echo"])

        assert result["all_passed"] is True
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_validate_with_kubectl(self):
        """Test validation with kubectl (includes Kubernetes validator)."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator,
            "validate",
            return_value={"status": "passed", "tool": "kubectl"},
        ), patch.object(
            KubernetesValidator,
            "validate",
            return_value={"status": "passed", "checks": []},
        ):
            result = await validator.validate(environment, required_tools=["kubectl"])

        assert result["all_passed"] is True
        assert len(result["results"]) == 2  # Tool + Kubernetes validator

    @pytest.mark.asyncio
    async def test_validate_with_failures(self):
        """Test validation with failures."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator,
            "validate",
            return_value={"status": "failed", "tool": "missing"},
        ):
            result = await validator.validate(environment, required_tools=["missing"])

        assert result["all_passed"] is False
        assert result["has_warnings"] is False
        assert "failed" in result["summary"]

    @pytest.mark.asyncio
    async def test_validate_with_warnings(self):
        """Test validation with warnings."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        with patch.object(
            ToolValidator,
            "validate",
            return_value={"status": "warning", "tool": "warning"},
        ):
            result = await validator.validate(environment, required_tools=["warning"])

        assert result["all_passed"] is True  # Warnings don't fail validation
        assert result["has_warnings"] is True
        assert "warnings" in result["summary"]

    @pytest.mark.asyncio
    async def test_validate_with_custom_validators(self):
        """Test validation with custom validators."""
        main_validator = PrerequisiteValidator()
        custom_validator = MockValidator({"status": "passed", "custom": True})
        main_validator.add_validator(custom_validator)

        environment = EnvironmentConfig(name="test", namespace="test-ns")

        result = await main_validator.validate(environment)

        assert result["all_passed"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["custom"] is True

    @pytest.mark.asyncio
    async def test_validate_mixed_results(self):
        """Test validation with mixed results."""
        validator = PrerequisiteValidator()
        environment = EnvironmentConfig(name="test", namespace="test-ns")

        # Mock different validator results
        mock_validators = [
            MockValidator({"status": "passed"}),
            MockValidator({"status": "warning"}),
            MockValidator({"status": "failed"}),
        ]

        validator.validators.extend(mock_validators)

        result = await validator.validate(environment)

        assert result["all_passed"] is False  # Due to failure
        assert result["has_warnings"] is True  # Due to warning
        assert len(result["results"]) == 3
        assert "failed" in result["summary"]

    def test_generate_summary_all_passed(self):
        """Test summary generation for all passed."""
        validator = PrerequisiteValidator()

        results = [
            {"status": "passed"},
            {"status": "passed"},
        ]

        summary = validator._generate_summary(results)
        assert "successfully" in summary

    def test_generate_summary_with_failures(self):
        """Test summary generation with failures."""
        validator = PrerequisiteValidator()

        results = [
            {"status": "passed"},
            {"status": "failed"},
            {"status": "failed"},
        ]

        summary = validator._generate_summary(results)
        assert "2 prerequisites failed" in summary

    def test_generate_summary_with_warnings_only(self):
        """Test summary generation with warnings only."""
        validator = PrerequisiteValidator()

        results = [
            {"status": "passed"},
            {"status": "warning"},
        ]

        summary = validator._generate_summary(results)
        assert "1 warnings" in summary
