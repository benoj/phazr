"""
Unit tests for phazr.models module.
"""

import pytest
from pydantic import ValidationError

from phazr.models import (
    EnvironmentConfig,
    ExecutionConfig,
    ExecutionResult,
    Operation,
    OperationType,
    OrchestratorConfig,
    Phase,
    PhaseResult,
    VersionConfig,
)


class TestOperationType:
    """Test OperationType enum."""

    def test_operation_type_values(self):
        """Test that all operation types have expected values."""
        assert OperationType.SCRIPT_EXEC == "script_exec"
        assert OperationType.KUBECTL_EXEC == "kubectl_exec"
        assert OperationType.KUBECTL_RESTART == "kubectl_restart"
        assert OperationType.KUBECTL_APPLY == "kubectl_apply"
        assert OperationType.KUBECTL_DELETE == "kubectl_delete"
        assert OperationType.HTTP_REQUEST == "http_request"
        assert OperationType.CUSTOM == "custom"
        assert OperationType.SKIP == "skip"

    def test_operation_type_string_conversion(self):
        """Test operation type can be created from string."""
        assert OperationType("script_exec") == OperationType.SCRIPT_EXEC
        assert OperationType("kubectl_exec") == OperationType.KUBECTL_EXEC


class TestPhase:
    """Test Phase model."""

    def test_minimal_phase_creation(self):
        """Test creating phase with minimal required fields."""
        phase = Phase(name="test_phase")

        assert phase.name == "test_phase"
        assert phase.description is None
        assert phase.icon is None
        assert phase.groups == []
        assert phase.depends_on == []
        assert phase.continue_on_error is False
        assert phase.parallel_groups is False
        assert phase.enabled is True

    def test_full_phase_creation(self):
        """Test creating phase with all fields."""
        phase = Phase(
            name="deploy",
            description="Deploy application",
            icon="🚀",
            groups=["k8s", "health_check"],
            depends_on=["build", "test"],
            continue_on_error=True,
            parallel_groups=True,
            enabled=False,
        )

        assert phase.name == "deploy"
        assert phase.description == "Deploy application"
        assert phase.icon == "🚀"
        assert phase.groups == ["k8s", "health_check"]
        assert phase.depends_on == ["build", "test"]
        assert phase.continue_on_error is True
        assert phase.parallel_groups is True
        assert phase.enabled is False

    def test_phase_name_required(self):
        """Test that phase name is required."""
        with pytest.raises(ValidationError) as exc_info:
            Phase()

        assert "name" in str(exc_info.value)


class TestOperation:
    """Test Operation model."""

    def test_minimal_operation_creation(self):
        """Test creating operation with minimal required fields."""
        operation = Operation(
            command="echo hello",
            description="Say hello",
            type=OperationType.SCRIPT_EXEC,
        )

        assert operation.command == "echo hello"
        assert operation.description == "Say hello"
        assert operation.type == OperationType.SCRIPT_EXEC
        assert operation.service is None
        assert operation.namespace is None
        assert operation.container is None
        assert operation.wait_for_ready is False
        assert operation.timeout == 300
        assert operation.retry_count == 0
        assert operation.retry_delay == 5
        assert operation.fail_on_error is True
        assert operation.metadata == {}

    def test_full_operation_creation(self):
        """Test creating operation with all fields."""
        metadata = {"env": "test", "priority": "high"}

        operation = Operation(
            command="kubectl get pods",
            description="List pods",
            type=OperationType.KUBECTL_EXEC,
            service="web-app",
            namespace="production",
            container="app",
            wait_for_ready=True,
            timeout=600,
            test_command="test -f /ready",
            expected_output="Ready",
            retry_count=3,
            retry_delay=10,
            skip_if="test -f /skip",
            fail_on_error=False,
            metadata=metadata,
        )

        assert operation.command == "kubectl get pods"
        assert operation.service == "web-app"
        assert operation.namespace == "production"
        assert operation.container == "app"
        assert operation.wait_for_ready is True
        assert operation.timeout == 600
        assert operation.retry_count == 3
        assert operation.retry_delay == 10
        assert operation.skip_if == "test -f /skip"
        assert operation.fail_on_error is False
        assert operation.metadata == metadata

    def test_required_fields_validation(self):
        """Test that required fields are validated."""
        # Missing command
        with pytest.raises(ValidationError) as exc_info:
            Operation(description="Test", type=OperationType.SCRIPT_EXEC)
        assert "command" in str(exc_info.value)

        # Missing description
        with pytest.raises(ValidationError) as exc_info:
            Operation(command="echo test", type=OperationType.SCRIPT_EXEC)
        assert "description" in str(exc_info.value)

        # Missing type
        with pytest.raises(ValidationError) as exc_info:
            Operation(command="echo test", description="Test")
        assert "type" in str(exc_info.value)

    def test_operation_type_validation(self):
        """Test operation type validation."""
        # Valid operation type
        operation = Operation(
            command="echo test",
            description="Test",
            type="script_exec",  # String should be converted
        )
        assert operation.type == OperationType.SCRIPT_EXEC

        # Invalid operation type
        with pytest.raises(ValidationError):
            Operation(command="echo test", description="Test", type="invalid_type")


class TestExecutionResult:
    """Test ExecutionResult model."""

    def test_execution_result_creation(self):
        """Test creating execution result."""
        operation = Operation(
            command="echo test",
            description="Test command",
            type=OperationType.SCRIPT_EXEC,
        )

        result = ExecutionResult(
            operation=operation,
            success=True,
            output="test output",
            error=None,
            duration=1.5,
            timestamp="2023-01-01T12:00:00Z",
            retries_used=0,
            metadata={"exit_code": 0},
        )

        assert result.operation == operation
        assert result.success is True
        assert result.output == "test output"
        assert result.error is None
        assert result.duration == 1.5
        assert result.timestamp == "2023-01-01T12:00:00Z"
        assert result.retries_used == 0
        assert result.metadata == {"exit_code": 0}

    def test_execution_result_defaults(self):
        """Test execution result default values."""
        operation = Operation(
            command="echo test",
            description="Test command",
            type=OperationType.SCRIPT_EXEC,
        )

        result = ExecutionResult(operation=operation, success=False)

        assert result.output is None
        assert result.error is None
        assert result.duration == 0.0
        assert result.timestamp is None
        assert result.retries_used == 0
        assert result.metadata == {}


class TestPhaseResult:
    """Test PhaseResult model."""

    @pytest.fixture
    def sample_operations(self):
        """Sample operations for testing."""
        return [
            Operation(
                command="echo 1", description="Op 1", type=OperationType.SCRIPT_EXEC
            ),
            Operation(
                command="echo 2", description="Op 2", type=OperationType.SCRIPT_EXEC
            ),
            Operation(
                command="echo 3", description="Op 3", type=OperationType.SCRIPT_EXEC
            ),
        ]

    @pytest.fixture
    def sample_results(self, sample_operations):
        """Sample execution results."""
        return [
            ExecutionResult(operation=sample_operations[0], success=True),
            ExecutionResult(operation=sample_operations[1], success=True),
            ExecutionResult(operation=sample_operations[2], success=False),
        ]

    def test_phase_result_creation(self, sample_results):
        """Test creating phase result."""
        phase_result = PhaseResult(
            phase_name="test_phase",
            version="1.0.0",
            results=sample_results,
            total_operations=3,
            successful_operations=2,
            failed_operations=1,
            skipped_operations=0,
            duration=5.5,
        )

        assert phase_result.phase_name == "test_phase"
        assert phase_result.version == "1.0.0"
        assert len(phase_result.results) == 3
        assert phase_result.total_operations == 3
        assert phase_result.successful_operations == 2
        assert phase_result.failed_operations == 1
        assert phase_result.skipped_operations == 0
        assert phase_result.duration == 5.5

    def test_success_rate_calculation(self, sample_results):
        """Test success rate calculation."""
        phase_result = PhaseResult(
            phase_name="test",
            version="1.0.0",
            results=sample_results,
            total_operations=3,
            successful_operations=2,
            failed_operations=1,
            skipped_operations=0,
        )

        assert abs(phase_result.success_rate - 66.66666666666667) < 0.001

    def test_success_rate_with_zero_operations(self):
        """Test success rate with zero operations."""
        phase_result = PhaseResult(
            phase_name="test",
            version="1.0.0",
            results=[],
            total_operations=0,
            successful_operations=0,
            failed_operations=0,
            skipped_operations=0,
        )

        assert phase_result.success_rate == 100.0

    def test_is_successful_property(self, sample_results):
        """Test is_successful property."""
        # Failed phase
        failed_phase = PhaseResult(
            phase_name="test",
            version="1.0.0",
            results=sample_results,
            total_operations=3,
            successful_operations=2,
            failed_operations=1,
            skipped_operations=0,
        )
        assert failed_phase.is_successful is False

        # Successful phase
        successful_phase = PhaseResult(
            phase_name="test",
            version="1.0.0",
            results=[],
            total_operations=2,
            successful_operations=2,
            failed_operations=0,
            skipped_operations=0,
        )
        assert successful_phase.is_successful is True


class TestVersionConfig:
    """Test VersionConfig model."""

    def test_version_config_creation(self):
        """Test creating version config."""
        operations = {
            "build": [
                Operation(
                    command="make build",
                    description="Build",
                    type=OperationType.SCRIPT_EXEC,
                )
            ],
            "test": [
                Operation(
                    command="make test",
                    description="Test",
                    type=OperationType.SCRIPT_EXEC,
                )
            ],
        }

        config = VersionConfig(
            version="1.0.0", groups=operations, metadata={"branch": "main"}
        )

        assert config.version == "1.0.0"
        assert config.groups == operations
        assert config.metadata == {"branch": "main"}

    def test_empty_group_validation(self):
        """Test that empty groups are not allowed."""
        with pytest.raises(ValidationError) as exc_info:
            VersionConfig(
                version="1.0.0",
                groups={
                    "build": [],  # Empty group should fail validation
                    "test": [
                        Operation(
                            command="test",
                            description="Test",
                            type=OperationType.SCRIPT_EXEC,
                        )
                    ],
                },
            )

        assert "Group 'build' cannot be empty" in str(exc_info.value)


class TestEnvironmentConfig:
    """Test EnvironmentConfig model."""

    def test_minimal_environment_config(self):
        """Test creating environment config with minimal fields."""
        config = EnvironmentConfig(name="development", namespace="dev")

        assert config.name == "development"
        assert config.namespace == "dev"
        assert config.context is None
        assert config.cluster is None
        assert config.metadata == {}

    def test_full_environment_config(self):
        """Test creating environment config with all fields."""
        metadata = {"region": "us-west-2", "env_type": "staging"}

        config = EnvironmentConfig(
            name="staging",
            namespace="staging-ns",
            context="staging-cluster",
            cluster="cluster-west",
            metadata=metadata,
        )

        assert config.name == "staging"
        assert config.namespace == "staging-ns"
        assert config.context == "staging-cluster"
        assert config.cluster == "cluster-west"
        assert config.metadata == metadata


class TestExecutionConfig:
    """Test ExecutionConfig model."""

    def test_execution_config_defaults(self):
        """Test execution config default values."""
        config = ExecutionConfig()

        assert config.dry_run is False
        assert config.interactive is True
        assert config.parallel is False
        assert config.max_parallel == 5
        assert config.continue_on_error is False
        assert config.verbose is False
        assert config.log_level == "INFO"

    def test_execution_config_custom_values(self):
        """Test execution config with custom values."""
        config = ExecutionConfig(
            dry_run=True,
            interactive=False,
            parallel=True,
            max_parallel=10,
            continue_on_error=True,
            verbose=True,
            log_level="DEBUG",
        )

        assert config.dry_run is True
        assert config.interactive is False
        assert config.parallel is True
        assert config.max_parallel == 10
        assert config.continue_on_error is True
        assert config.verbose is True
        assert config.log_level == "DEBUG"


class TestOrchestratorConfig:
    """Test OrchestratorConfig model."""

    @pytest.fixture
    def sample_version_config(self):
        """Sample version configuration."""
        operations = {
            "build": [
                Operation(
                    command="make", description="Build", type=OperationType.SCRIPT_EXEC
                )
            ]
        }
        return VersionConfig(version="1.0.0", groups=operations)

    @pytest.fixture
    def sample_phases(self):
        """Sample phases."""
        return [
            Phase(name="build", groups=["build"]),
            Phase(name="test", groups=["test"], depends_on=["build"]),
        ]

    @pytest.fixture
    def sample_environment(self):
        """Sample environment."""
        return EnvironmentConfig(name="test", namespace="default")

    def test_orchestrator_config_creation(
        self, sample_version_config, sample_phases, sample_environment
    ):
        """Test creating orchestrator config."""
        config = OrchestratorConfig(
            versions={"1.0.0": sample_version_config},
            phases=sample_phases,
            environment=sample_environment,
            execution=ExecutionConfig(verbose=True),
            metadata={"created_by": "test"},
        )

        assert config.versions == {"1.0.0": sample_version_config}
        assert config.phases == sample_phases
        assert config.environment == sample_environment
        assert config.execution.verbose is True
        assert config.metadata == {"created_by": "test"}

    def test_orchestrator_config_defaults(
        self, sample_version_config, sample_environment
    ):
        """Test orchestrator config default values."""
        config = OrchestratorConfig(
            versions={"1.0.0": sample_version_config}, environment=sample_environment
        )

        assert config.phases == []
        assert isinstance(config.execution, ExecutionConfig)
        assert config.metadata == {}

    def test_required_fields_validation(self):
        """Test that required fields are validated."""
        # Missing versions
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfig(
                environment=EnvironmentConfig(name="test", namespace="default")
            )
        assert "versions" in str(exc_info.value)

        # Missing environment
        with pytest.raises(ValidationError) as exc_info:
            OrchestratorConfig(versions={})
        assert "environment" in str(exc_info.value)
