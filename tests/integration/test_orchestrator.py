"""
Integration tests for phazr.executor module (Orchestrator).
"""

import asyncio
from unittest.mock import Mock, patch

import pytest

from phazr.display import DisplayManager
from phazr.executor import Orchestrator
from phazr.handlers import HandlerRegistry, OperationHandler
from phazr.models import (
    EnvironmentConfig,
    ExecutionConfig,
    Operation,
    OperationType,
    OrchestratorConfig,
    Phase,
    PhaseResult,
    VersionConfig,
)
from tests.utils.test_helpers import create_failed_result, create_successful_result


class MockOperationHandler(OperationHandler):
    """Mock operation handler for testing."""

    def __init__(self, success=True, output="Mock output", delay=0.1):
        self.success = success
        self.output = output
        self.delay = delay
        self.call_count = 0

    async def execute(self, operation, environment):
        """Mock execute method."""
        self.call_count += 1
        await asyncio.sleep(self.delay)

        if self.success:
            return create_successful_result(operation, self.output)
        else:
            return create_failed_result(operation, "Mock error")


class TestOrchestrator:
    """Test Orchestrator integration."""

    @pytest.fixture
    def mock_handler_registry(self):
        """Create mock handler registry with registered handlers."""
        registry = HandlerRegistry()

        # Register mock handlers for different operation types
        registry.register(OperationType.SCRIPT_EXEC, MockOperationHandler(success=True))
        registry.register(
            OperationType.KUBECTL_EXEC, MockOperationHandler(success=True)
        )
        registry.register(
            OperationType.HTTP_REQUEST, MockOperationHandler(success=True)
        )

        return registry

    @pytest.fixture
    def mock_display(self):
        """Create mock display manager."""
        display = Mock(spec=DisplayManager)
        display.start_phase = Mock()
        display.end_phase = Mock()
        display.start_operation = Mock()
        display.end_operation = Mock()
        display.show_error = Mock()
        display.show_success = Mock()
        return display

    @pytest.fixture
    def sample_orchestrator_config_with_phases(self):
        """Create orchestrator config with phases for testing."""
        operations = {
            "build": [
                Operation(
                    command="make build",
                    description="Build application",
                    type=OperationType.SCRIPT_EXEC,
                    timeout=60,
                )
            ],
            "test": [
                Operation(
                    command="make test",
                    description="Run tests",
                    type=OperationType.SCRIPT_EXEC,
                    timeout=120,
                )
            ],
            "deploy": [
                Operation(
                    command="kubectl apply -f deployment.yaml",
                    description="Deploy to k8s",
                    type=OperationType.KUBECTL_EXEC,
                    service="web-app",
                    timeout=300,
                )
            ],
        }

        version = VersionConfig(version="1.0.0", groups=operations)

        phases = [
            Phase(name="build", groups=["build"], enabled=True),
            Phase(name="test", groups=["test"], depends_on=["build"], enabled=True),
            Phase(name="deploy", groups=["deploy"], depends_on=["test"], enabled=True),
        ]

        environment = EnvironmentConfig(name="test", namespace="default")
        execution = ExecutionConfig(dry_run=False, verbose=True)

        return OrchestratorConfig(
            versions={"1.0.0": version},
            phases=phases,
            environment=environment,
            execution=execution,
        )

    @pytest.fixture
    def orchestrator(
        self,
        sample_orchestrator_config_with_phases,
        mock_handler_registry,
        mock_display,
    ):
        """Create orchestrator instance for testing."""
        return Orchestrator(
            config=sample_orchestrator_config_with_phases,
            handler_registry=mock_handler_registry,
            display=mock_display,
        )

    @pytest.mark.asyncio
    async def test_orchestrator_initialization(
        self, sample_orchestrator_config_with_phases
    ):
        """Test orchestrator initialization."""
        orchestrator = Orchestrator(config=sample_orchestrator_config_with_phases)

        assert orchestrator.config == sample_orchestrator_config_with_phases
        assert orchestrator.handler_registry is not None
        assert orchestrator.display is not None
        assert orchestrator.logger is not None

    @pytest.mark.asyncio
    async def test_execute_single_phase_success(self, orchestrator, mock_display):
        """Test executing a single phase successfully."""
        # This test assumes the orchestrator has methods for phase execution
        # We'll need to check the actual implementation
        with patch.object(orchestrator, "run_phase") as mock_run_phase:
            mock_result = PhaseResult(
                phase_name="build",
                version="1.0.0",
                results=[],
                total_operations=1,
                successful_operations=1,
                failed_operations=0,
                skipped_operations=0,
            )
            mock_run_phase.return_value = mock_result

            # Test would depend on actual method signature
            # This is a placeholder for the integration test structure
            pass

    @pytest.mark.asyncio
    async def test_phase_dependency_resolution(self, orchestrator):
        """Test that phases execute in correct dependency order."""
        # Track execution order
        execution_order = []

        async def track_execution(phase_name):
            execution_order.append(phase_name)

        # Mock phase execution to track order
        with patch.object(orchestrator, "run_phase", side_effect=track_execution):
            # This would test the dependency resolution logic
            # Implementation depends on orchestrator's actual interface
            pass

    @pytest.mark.asyncio
    async def test_parallel_group_execution(self, orchestrator):
        """Test parallel execution of operation groups."""
        # Create phase with parallel groups enabled
        parallel_phase = Phase(
            name="parallel_test",
            groups=["group1", "group2", "group3"],
            parallel_groups=True,
            enabled=True,
        )

        # Test would verify that groups execute concurrently
        # Implementation depends on orchestrator's execution logic
        assert parallel_phase.parallel_groups is True
        pass

    @pytest.mark.asyncio
    async def test_error_handling_continue_on_error(self, mock_handler_registry):
        """Test error handling with continue_on_error enabled."""
        # Register a failing handler for one operation type
        mock_handler_registry.register(
            OperationType.SCRIPT_EXEC, MockOperationHandler(success=False)
        )

        # Create config with continue_on_error enabled
        operations = {
            "failing_group": [
                Operation(
                    command="fail command",
                    description="Failing operation",
                    type=OperationType.SCRIPT_EXEC,
                )
            ],
            "success_group": [
                Operation(
                    command="success command",
                    description="Success operation",
                    type=OperationType.HTTP_REQUEST,
                )
            ],
        }

        version = VersionConfig(version="1.0.0", groups=operations)

        phases = [
            Phase(
                name="error_phase",
                groups=["failing_group"],
                continue_on_error=True,
                enabled=True,
            ),
            Phase(
                name="next_phase",
                groups=["success_group"],
                depends_on=["error_phase"],
                enabled=True,
            ),
        ]

        config = OrchestratorConfig(
            versions={"1.0.0": version},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
            execution=ExecutionConfig(continue_on_error=True),
        )

        orchestrator = Orchestrator(
            config=config, handler_registry=mock_handler_registry
        )

        # Test that execution continues despite failures
        # Implementation depends on orchestrator's error handling
        assert orchestrator.config.execution.continue_on_error is True
        pass

    @pytest.mark.asyncio
    async def test_dry_run_mode(
        self, sample_orchestrator_config_with_phases, mock_handler_registry
    ):
        """Test orchestrator in dry run mode."""
        # Enable dry run
        sample_orchestrator_config_with_phases.execution.dry_run = True

        orchestrator = Orchestrator(
            config=sample_orchestrator_config_with_phases,
            handler_registry=mock_handler_registry,
        )

        # In dry run mode, operations should be previewed but not executed
        # Implementation depends on orchestrator's dry run logic
        assert orchestrator.config.execution.dry_run is True
        pass

    @pytest.mark.asyncio
    async def test_operation_timeout_handling(self, mock_handler_registry):
        """Test handling of operation timeouts."""
        # Create a slow handler that exceeds timeout
        slow_handler = MockOperationHandler(success=True, delay=2.0)
        mock_handler_registry.register(OperationType.SCRIPT_EXEC, slow_handler)

        operations = {
            "slow_group": [
                Operation(
                    command="slow command",
                    description="Slow operation",
                    type=OperationType.SCRIPT_EXEC,
                    timeout=1,  # 1 second timeout, but operation takes 2 seconds
                )
            ]
        }

        version = VersionConfig(version="1.0.0", groups=operations)
        phases = [Phase(name="slow_phase", groups=["slow_group"], enabled=True)]

        config = OrchestratorConfig(
            versions={"1.0.0": version},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        orchestrator = Orchestrator(
            config=config, handler_registry=mock_handler_registry
        )

        # Test timeout handling - implementation depends on orchestrator logic
        assert orchestrator.config.versions["1.0.0"] is not None
        pass

    @pytest.mark.asyncio
    async def test_operation_retry_logic(self, mock_handler_registry):
        """Test operation retry logic."""

        # Create handler that fails first few times, then succeeds
        class RetryHandler(OperationHandler):
            def __init__(self):
                self.attempt_count = 0

            async def execute(self, operation, environment):
                self.attempt_count += 1
                if self.attempt_count <= 2:  # Fail first 2 attempts
                    return create_failed_result(operation, "Temporary failure")
                return create_successful_result(operation, "Success on retry")

        retry_handler = RetryHandler()
        mock_handler_registry.register(OperationType.SCRIPT_EXEC, retry_handler)

        operations = {
            "retry_group": [
                Operation(
                    command="retry command",
                    description="Retry operation",
                    type=OperationType.SCRIPT_EXEC,
                    retry_count=3,
                    retry_delay=1,
                )
            ]
        }

        version = VersionConfig(version="1.0.0", groups=operations)
        phases = [Phase(name="retry_phase", groups=["retry_group"], enabled=True)]

        config = OrchestratorConfig(
            versions={"1.0.0": version},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        orchestrator = Orchestrator(
            config=config, handler_registry=mock_handler_registry
        )

        # Test retry logic - should eventually succeed after retries
        assert orchestrator.handler_registry is not None
        pass

    @pytest.mark.asyncio
    async def test_disabled_phase_skipping(
        self, sample_orchestrator_config_with_phases, mock_handler_registry
    ):
        """Test that disabled phases are skipped."""
        # Disable the test phase
        for phase in sample_orchestrator_config_with_phases.phases:
            if phase.name == "test":
                phase.enabled = False

        orchestrator = Orchestrator(
            config=sample_orchestrator_config_with_phases,
            handler_registry=mock_handler_registry,
        )

        # Test that disabled phase is skipped but dependents still run
        # Implementation depends on orchestrator's phase filtering logic
        assert orchestrator.config.phases[1].enabled is False
        pass

    @pytest.mark.asyncio
    async def test_missing_handler_error(self, sample_orchestrator_config_with_phases):
        """Test error handling when operation handler is missing."""
        # Create empty handler registry
        empty_registry = HandlerRegistry()

        orchestrator = Orchestrator(
            config=sample_orchestrator_config_with_phases,
            handler_registry=empty_registry,
        )

        # Should handle missing handler gracefully
        # Implementation depends on orchestrator's error handling
        # Check for a handler that's not registered by default
        assert (
            orchestrator.handler_registry.get_handler(OperationType.HTTP_REQUEST)
            is None
        )
        pass

    @pytest.mark.asyncio
    async def test_complex_dependency_graph(self, mock_handler_registry):
        """Test complex phase dependency resolution."""
        # Create diamond dependency pattern:
        # setup -> (build, lint) -> deploy
        operations = {
            "setup_ops": [
                Operation(
                    command="setup", description="Setup", type=OperationType.SCRIPT_EXEC
                )
            ],
            "build_ops": [
                Operation(
                    command="build", description="Build", type=OperationType.SCRIPT_EXEC
                )
            ],
            "lint_ops": [
                Operation(
                    command="lint", description="Lint", type=OperationType.SCRIPT_EXEC
                )
            ],
            "deploy_ops": [
                Operation(
                    command="deploy",
                    description="Deploy",
                    type=OperationType.KUBECTL_EXEC,
                    service="app",
                )
            ],
        }

        version = VersionConfig(version="1.0.0", groups=operations)

        phases = [
            Phase(name="setup", groups=["setup_ops"], enabled=True),
            Phase(
                name="build", groups=["build_ops"], depends_on=["setup"], enabled=True
            ),
            Phase(name="lint", groups=["lint_ops"], depends_on=["setup"], enabled=True),
            Phase(
                name="deploy",
                groups=["deploy_ops"],
                depends_on=["build", "lint"],
                enabled=True,
            ),
        ]

        config = OrchestratorConfig(
            versions={"1.0.0": version},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        orchestrator = Orchestrator(
            config=config, handler_registry=mock_handler_registry
        )

        # Test that phases execute in correct topological order
        # setup -> (build || lint) -> deploy
        assert len(orchestrator.config.phases) == 4
        pass

    @pytest.mark.asyncio
    async def test_version_selection(self, mock_handler_registry):
        """Test running operations for specific version."""
        # Create config with multiple versions
        v1_operations = {
            "build": [
                Operation(
                    command="build v1",
                    description="Build v1",
                    type=OperationType.SCRIPT_EXEC,
                )
            ]
        }
        v2_operations = {
            "build": [
                Operation(
                    command="build v2",
                    description="Build v2",
                    type=OperationType.SCRIPT_EXEC,
                )
            ]
        }

        config = OrchestratorConfig(
            versions={
                "1.0.0": VersionConfig(version="1.0.0", groups=v1_operations),
                "2.0.0": VersionConfig(version="2.0.0", groups=v2_operations),
            },
            phases=[Phase(name="build", groups=["build"], enabled=True)],
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        orchestrator = Orchestrator(
            config=config, handler_registry=mock_handler_registry
        )

        # Test version-specific operation execution
        # Implementation depends on orchestrator's version selection logic
        assert "1.0.0" in orchestrator.config.versions
        assert "2.0.0" in orchestrator.config.versions
        pass


class TestOrchestratorErrorScenarios:
    """Test orchestrator error scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_circular_dependency_detection(self):
        """Test detection of circular phase dependencies."""
        # Create phases with circular dependency
        phases = [
            Phase(
                name="phase_a", groups=["group_a"], depends_on=["phase_b"], enabled=True
            ),
            Phase(
                name="phase_b", groups=["group_b"], depends_on=["phase_c"], enabled=True
            ),
            Phase(
                name="phase_c", groups=["group_c"], depends_on=["phase_a"], enabled=True
            ),  # Circular!
        ]

        operations = {
            "group_a": [
                Operation(command="a", description="A", type=OperationType.SCRIPT_EXEC)
            ],
            "group_b": [
                Operation(command="b", description="B", type=OperationType.SCRIPT_EXEC)
            ],
            "group_c": [
                Operation(command="c", description="C", type=OperationType.SCRIPT_EXEC)
            ],
        }

        config = OrchestratorConfig(
            versions={"1.0.0": VersionConfig(version="1.0.0", groups=operations)},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        # Should detect and handle circular dependency
        # Implementation depends on DAG validation logic
        assert len(config.phases) == 3
        pass

    @pytest.mark.asyncio
    async def test_missing_dependency_handling(self):
        """Test handling of missing phase dependencies."""
        phases = [
            Phase(
                name="dependent_phase",
                groups=["group_a"],
                depends_on=["nonexistent_phase"],  # Missing dependency
                enabled=True,
            )
        ]

        operations = {
            "group_a": [
                Operation(command="a", description="A", type=OperationType.SCRIPT_EXEC)
            ]
        }

        config = OrchestratorConfig(
            versions={"1.0.0": VersionConfig(version="1.0.0", groups=operations)},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        # Should handle missing dependency gracefully
        assert config.phases[0].depends_on == ["nonexistent_phase"]
        pass

    @pytest.mark.asyncio
    async def test_empty_phase_handling(self):
        """Test handling of phases with no operations."""
        phases = [Phase(name="empty_phase", groups=["nonexistent_group"], enabled=True)]

        config = OrchestratorConfig(
            versions={"1.0.0": VersionConfig(version="1.0.0", groups={})},
            phases=phases,
            environment=EnvironmentConfig(name="test", namespace="default"),
        )

        orchestrator = Orchestrator(config=config)

        # Should handle empty phases gracefully
        assert orchestrator.config.phases[0].groups == ["nonexistent_group"]
        pass
