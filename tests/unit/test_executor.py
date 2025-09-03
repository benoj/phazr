"""
Unit tests for orchestration executor functionality.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from phazr.executor import Orchestrator
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


class TestOrchestrator:
    """Test Orchestrator class functionality."""

    @pytest.fixture
    def sample_environment(self):
        """Sample environment config."""
        return EnvironmentConfig(
            name="test-env",
            namespace="test-ns",
            context="test-context",
        )

    @pytest.fixture
    def sample_execution_config(self):
        """Sample execution config."""
        return ExecutionConfig(
            dry_run=False,
            verbose=False,
            parallel=False,
            max_parallel=3,
        )

    @pytest.fixture
    def sample_operation(self):
        """Sample operation."""
        return Operation(
            command="echo 'test'",
            description="Test operation",
            type=OperationType.SCRIPT_EXEC,
        )

    @pytest.fixture
    def sample_version_config(self, sample_operation):
        """Sample version config."""
        return VersionConfig(
            version="1.0.0",
            groups={
                "group1": [sample_operation],
                "group2": [sample_operation],
            },
        )

    @pytest.fixture
    def sample_phase(self):
        """Sample phase."""
        return Phase(
            name="test_phase",
            description="Test phase",
            groups=["group1"],
        )

    @pytest.fixture
    def sample_config(
        self,
        sample_environment,
        sample_execution_config,
        sample_version_config,
        sample_phase,
    ):
        """Sample orchestrator config."""
        return OrchestratorConfig(
            environment=sample_environment,
            execution=sample_execution_config,
            versions={"1.0.0": sample_version_config},
            phases=[sample_phase],
        )

    @pytest.fixture
    def orchestrator(self, sample_config):
        """Create orchestrator instance."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager") as mock_display:
            mock_display.return_value.verbose = False
            return Orchestrator(sample_config)

    def test_init_with_defaults(self, sample_config):
        """Test orchestrator initialization with default components."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager"):
            orchestrator = Orchestrator(sample_config)

            assert orchestrator.config == sample_config
            assert orchestrator.handler_registry is not None
            assert orchestrator.validator is not None
            assert orchestrator.display is not None

    def test_init_with_custom_components(self, sample_config):
        """Test orchestrator initialization with custom components."""
        mock_handler_registry = Mock()
        mock_validator = Mock()
        mock_display = Mock()
        mock_logger = Mock()

        orchestrator = Orchestrator(
            sample_config,
            handler_registry=mock_handler_registry,
            validator=mock_validator,
            display=mock_display,
            logger=mock_logger,
        )

        assert orchestrator.handler_registry == mock_handler_registry
        assert orchestrator.validator == mock_validator
        assert orchestrator.display == mock_display
        assert orchestrator.logger == mock_logger

    def test_create_default_logger(self, sample_config):
        """Test default logger creation."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager"), patch(
            "logging.basicConfig"
        ) as mock_basic_config, patch(
            "logging.getLogger"
        ) as mock_get_logger:

            orchestrator = Orchestrator(sample_config)
            logger = orchestrator._create_default_logger()

            # Expect 2 calls: one from init, one from our explicit call
            assert mock_basic_config.call_count >= 1
            mock_get_logger.assert_called()
            assert logger is not None

    def test_register_default_handlers(self, sample_config):
        """Test registration of default handlers."""
        mock_handler_registry = Mock()

        with patch("phazr.executor.PrerequisiteValidator"), patch(
            "phazr.executor.DisplayManager"
        ):
            Orchestrator(sample_config, handler_registry=mock_handler_registry)

            # Should have registered 3 handlers
            assert mock_handler_registry.register.call_count == 3

    @pytest.mark.asyncio
    async def test_validate_prerequisites(self, orchestrator):
        """Test prerequisites validation."""
        mock_results = {"all_passed": True, "results": []}
        orchestrator.validator.validate = AsyncMock(return_value=mock_results)
        orchestrator.display.info = Mock()
        orchestrator.display.show_validation_results = Mock()

        results = await orchestrator.validate_prerequisites()

        assert results == mock_results
        orchestrator.display.info.assert_called_once()
        orchestrator.display.show_validation_results.assert_called_once_with(
            mock_results
        )

    def test_get_required_tools_kubectl(self, sample_config):
        """Test required tools detection for kubectl operations."""
        # Add kubectl operations to test
        kubectl_op = Operation(
            command="kubectl get pods",
            description="Test kubectl",
            type=OperationType.KUBECTL_EXEC,
        )

        sample_config.versions["1.0.0"].groups["kubectl_group"] = [kubectl_op]

        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager"):
            orchestrator = Orchestrator(sample_config)

            tools = orchestrator._get_required_tools()

            assert "kubectl" in tools

    def test_get_required_tools_no_kubectl(self, sample_config):
        """Test required tools when no kubectl operations present."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager"):
            orchestrator = Orchestrator(sample_config)

            tools = orchestrator._get_required_tools()

            assert "kubectl" not in tools

    @pytest.mark.asyncio
    async def test_run_full_setup_success(self, orchestrator, sample_config):
        """Test successful full setup execution."""
        # Mock phase execution
        orchestrator.run_phase = AsyncMock(
            return_value=PhaseResult(
                phase_name="test_phase",
                version="1.0.0",
                results=[],
                total_operations=1,
                successful_operations=1,
                failed_operations=0,
                skipped_operations=0,
                duration=1.0,
            )
        )

        orchestrator.display.print_header = Mock()
        orchestrator.display.info = Mock()
        orchestrator.display.show_final_summary = Mock()

        results = await orchestrator.run_full_setup("1.0.0")

        assert len(results) == 1
        assert results[0].phase_name == "test_phase"
        orchestrator.display.print_header.assert_called_once()
        orchestrator.display.show_final_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_full_setup_skip_disabled_phase(
        self, orchestrator, sample_config
    ):
        """Test full setup skipping disabled phases."""
        # Disable the phase
        sample_config.phases[0].enabled = False

        orchestrator.display.print_header = Mock()
        orchestrator.display.info = Mock()
        orchestrator.display.show_final_summary = Mock()

        results = await orchestrator.run_full_setup("1.0.0")

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_run_full_setup_missing_dependencies(
        self, orchestrator, sample_config
    ):
        """Test full setup with missing phase dependencies."""
        # Add phase with missing dependency
        dependent_phase = Phase(
            name="dependent_phase",
            description="Dependent phase",
            groups=["group1"],
            depends_on=["missing_phase"],
        )
        sample_config.phases.append(dependent_phase)

        orchestrator.run_phase = AsyncMock(
            return_value=PhaseResult(
                phase_name="test_phase",
                version="1.0.0",
                results=[],
                total_operations=1,
                successful_operations=1,
                failed_operations=0,
                skipped_operations=0,
                duration=1.0,
            )
        )

        orchestrator.display.print_header = Mock()
        orchestrator.display.info = Mock()
        orchestrator.display.warning = Mock()
        orchestrator.display.show_final_summary = Mock()

        results = await orchestrator.run_full_setup("1.0.0")

        # Should only run the first phase, skip the dependent one
        assert len(results) == 1
        orchestrator.display.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_full_setup_stop_on_error(self, orchestrator, sample_config):
        """Test full setup stopping on error."""
        # Add another phase
        phase2 = Phase(name="phase2", groups=["group2"])
        sample_config.phases.append(phase2)

        # Mock first phase to fail
        orchestrator.run_phase = AsyncMock(
            return_value=PhaseResult(
                phase_name="test_phase",
                version="1.0.0",
                results=[],
                total_operations=1,
                successful_operations=0,
                failed_operations=1,
                skipped_operations=0,
                duration=1.0,
            )
        )

        orchestrator.display.print_header = Mock()
        orchestrator.display.info = Mock()
        orchestrator.display.error = Mock()
        orchestrator.display.show_final_summary = Mock()

        results = await orchestrator.run_full_setup("1.0.0")

        # Should stop after first failed phase
        assert len(results) == 1
        assert not results[0].is_successful
        orchestrator.display.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_phase_success(self, orchestrator, sample_config, sample_phase):
        """Test successful phase execution."""
        orchestrator._execute_sequential = AsyncMock(
            return_value=[
                ExecutionResult(
                    operation=sample_config.versions["1.0.0"].groups["group1"][0],
                    success=True,
                    duration=1.0,
                )
            ]
        )

        orchestrator.display.start_phase = Mock()
        orchestrator.display.show_phase_summary = Mock()

        result = await orchestrator.run_phase(sample_phase, "1.0.0")

        assert result.phase_name == "test_phase"
        assert result.successful_operations == 1
        assert result.failed_operations == 0
        orchestrator.display.start_phase.assert_called_once()
        orchestrator.display.show_phase_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_phase_no_operations(self, orchestrator, sample_config):
        """Test phase execution with no operations."""
        empty_phase = Phase(name="empty_phase", groups=["nonexistent_group"])

        orchestrator.display.warning = Mock()

        result = await orchestrator.run_phase(empty_phase, "1.0.0")

        assert result.total_operations == 0
        assert result.successful_operations == 0

    @pytest.mark.asyncio
    async def test_run_phase_parallel(self, orchestrator, sample_config, sample_phase):
        """Test phase execution in parallel mode."""
        sample_config.execution.parallel = True
        sample_phase.parallel_groups = True

        orchestrator._is_group_parallelizable = Mock(return_value=True)
        orchestrator._execute_parallel = AsyncMock(
            return_value=[
                ExecutionResult(
                    operation=sample_config.versions["1.0.0"].groups["group1"][0],
                    success=True,
                    duration=1.0,
                )
            ]
        )

        orchestrator.display.start_phase = Mock()
        orchestrator.display.show_phase_summary = Mock()

        result = await orchestrator.run_phase(sample_phase, "1.0.0")

        assert result.successful_operations == 1
        orchestrator._execute_parallel.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_phase_by_name_success(self, orchestrator, sample_config):
        """Test running phase by name."""
        orchestrator.run_phase = AsyncMock(
            return_value=PhaseResult(
                phase_name="test_phase",
                version="1.0.0",
                results=[],
                total_operations=0,
                successful_operations=0,
                failed_operations=0,
                skipped_operations=0,
            )
        )

        result = await orchestrator.run_phase_by_name("test_phase", "1.0.0")

        assert result.phase_name == "test_phase"

    @pytest.mark.asyncio
    async def test_run_phase_by_name_not_found(self, orchestrator):
        """Test running nonexistent phase by name."""
        with pytest.raises(ValueError, match="Phase 'nonexistent' not found"):
            await orchestrator.run_phase_by_name("nonexistent")

    @pytest.mark.asyncio
    async def test_run_phase_version_not_found(self, orchestrator, sample_phase):
        """Test running phase with nonexistent version."""
        with pytest.raises(
            ValueError, match="Version nonexistent not found in configuration"
        ):
            await orchestrator.run_phase(sample_phase, "nonexistent")

    def test_is_group_parallelizable_safe_operations(self, orchestrator):
        """Test parallelization check for safe operations."""
        safe_ops = [
            Operation(
                command="echo test",
                description="Safe op",
                type=OperationType.SCRIPT_EXEC,
            )
        ]

        assert orchestrator._is_group_parallelizable(safe_ops) is True

    def test_is_group_parallelizable_unsafe_operations(self, orchestrator):
        """Test parallelization check for unsafe operations."""
        unsafe_ops = [
            Operation(
                command="kubectl restart",
                description="Unsafe op",
                type=OperationType.KUBECTL_RESTART,
            )
        ]

        assert orchestrator._is_group_parallelizable(unsafe_ops) is False

    @pytest.mark.asyncio
    async def test_execute_sequential_success(self, orchestrator, sample_operation):
        """Test sequential operation execution."""
        orchestrator._execute_operation = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        orchestrator.display.show_operation_start = Mock()
        orchestrator.display.show_operation_result = Mock()

        results = await orchestrator._execute_sequential([sample_operation])

        assert len(results) == 1
        assert results[0].success is True
        orchestrator.display.show_operation_start.assert_called_once()
        orchestrator.display.show_operation_result.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_sequential_with_failure_stop(
        self, orchestrator, sample_operation
    ):
        """Test sequential execution stopping on failure."""
        sample_operation.fail_on_error = True

        orchestrator._execute_operation = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=False,
                error="Test error",
                duration=1.0,
            )
        )

        orchestrator.display.show_operation_start = Mock()
        orchestrator.display.show_operation_result = Mock()

        results = await orchestrator._execute_sequential(
            [sample_operation, sample_operation]
        )

        # Should stop after first failure
        assert len(results) == 1
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_execute_sequential_dry_run(self, orchestrator, sample_operation):
        """Test sequential execution in dry run mode."""
        orchestrator.config.execution.dry_run = True

        orchestrator.display.show_operation_start = Mock()
        orchestrator.display.show_operation_result = Mock()

        results = await orchestrator._execute_sequential([sample_operation])

        assert len(results) == 1
        assert results[0].success is True
        assert "[DRY RUN]" in results[0].output

    @pytest.mark.asyncio
    async def test_execute_parallel_success(self, orchestrator, sample_operation):
        """Test parallel operation execution."""
        orchestrator._execute_operation = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        orchestrator.display.show_operation_start = Mock()
        orchestrator.display.show_operation_result = Mock()

        results = await orchestrator._execute_parallel([sample_operation])

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_execute_parallel_with_exception(
        self, orchestrator, sample_operation
    ):
        """Test parallel execution with exception."""
        orchestrator._execute_operation = AsyncMock(side_effect=Exception("Test error"))

        orchestrator.display.show_operation_start = Mock()
        orchestrator.display.show_operation_result = Mock()

        results = await orchestrator._execute_parallel([sample_operation])

        assert len(results) == 1
        assert results[0].success is False
        assert "Test error" in results[0].error

    @pytest.mark.asyncio
    async def test_execute_parallel_dry_run(self, orchestrator, sample_operation):
        """Test parallel execution in dry run mode."""
        orchestrator.config.execution.dry_run = True

        orchestrator.display.show_operation_start = Mock()
        orchestrator.display.show_operation_result = Mock()

        results = await orchestrator._execute_parallel([sample_operation])

        assert len(results) == 1
        assert results[0].success is True
        assert "[DRY RUN]" in results[0].output

    @pytest.mark.asyncio
    async def test_execute_operation_success(self, orchestrator, sample_operation):
        """Test successful single operation execution."""
        mock_handler = AsyncMock()
        mock_handler.execute = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        orchestrator.handler_registry.get_handler = Mock(return_value=mock_handler)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is True
        mock_handler.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_operation_skipped(self, orchestrator, sample_operation):
        """Test operation execution with skip condition."""
        sample_operation.skip_if = "test_condition"

        orchestrator._evaluate_condition = AsyncMock(return_value=True)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is True
        assert "skipped" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_operation_no_handler(self, orchestrator, sample_operation):
        """Test operation execution with no handler."""
        orchestrator.handler_registry.get_handler = Mock(return_value=None)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is False
        assert "No handler registered" in result.error

    @pytest.mark.asyncio
    async def test_execute_operation_with_retries(self, orchestrator, sample_operation):
        """Test operation execution with retries."""
        sample_operation.retry_count = 2
        sample_operation.retry_delay = 0  # Fast retries for testing

        mock_handler = AsyncMock()
        # First two calls fail, third succeeds
        mock_handler.execute = AsyncMock(
            side_effect=[
                Exception("First failure"),
                Exception("Second failure"),
                ExecutionResult(operation=sample_operation, success=True, duration=1.0),
            ]
        )

        orchestrator.handler_registry.get_handler = Mock(return_value=mock_handler)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)
        orchestrator.logger.warning = Mock()

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is True
        assert result.retries_used == 2
        assert mock_handler.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_operation_retries_exhausted(
        self, orchestrator, sample_operation
    ):
        """Test operation execution with exhausted retries."""
        sample_operation.retry_count = 1
        sample_operation.retry_delay = 0

        mock_handler = AsyncMock()
        mock_handler.execute = AsyncMock(side_effect=Exception("Persistent failure"))

        orchestrator.handler_registry.get_handler = Mock(return_value=mock_handler)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)
        orchestrator.logger.warning = Mock()

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is False
        assert result.retries_used == 2  # Original + 1 retry
        assert "Persistent failure" in result.error

    @pytest.mark.asyncio
    async def test_execute_operation_with_test_command_success(
        self, orchestrator, sample_operation
    ):
        """Test operation execution with successful test command."""
        sample_operation.test_command = "test -f /tmp/testfile"

        mock_handler = AsyncMock()
        mock_handler.execute = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        orchestrator.handler_registry.get_handler = Mock(return_value=mock_handler)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)
        orchestrator._run_test_command = AsyncMock(return_value=True)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is True
        orchestrator._run_test_command.assert_called_once_with("test -f /tmp/testfile")

    @pytest.mark.asyncio
    async def test_execute_operation_with_test_command_failure(
        self, orchestrator, sample_operation
    ):
        """Test operation execution with failing test command."""
        sample_operation.test_command = "test -f /tmp/nonexistent"

        mock_handler = AsyncMock()
        mock_handler.execute = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        orchestrator.handler_registry.get_handler = Mock(return_value=mock_handler)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)
        orchestrator._run_test_command = AsyncMock(return_value=False)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is False

    @pytest.mark.asyncio
    async def test_evaluate_condition_placeholder(self, orchestrator):
        """Test condition evaluation placeholder."""
        # Currently returns False as placeholder
        result = await orchestrator._evaluate_condition("test condition")
        assert result is False

    @pytest.mark.asyncio
    async def test_run_test_command_placeholder(self, orchestrator):
        """Test test command execution placeholder."""
        # Currently returns True as placeholder
        result = await orchestrator._run_test_command("echo test")
        assert result is True

    def test_create_dry_run_result(self, orchestrator, sample_operation):
        """Test dry run result creation."""
        result = orchestrator._create_dry_run_result(sample_operation)

        assert result.operation == sample_operation
        assert result.success is True
        assert "[DRY RUN]" in result.output
        assert result.duration == 0.0

    def test_chunk_list_small(self, orchestrator):
        """Test list chunking with small list."""
        items = [1, 2, 3]
        chunks = list(orchestrator._chunk_list(items, 2))

        assert len(chunks) == 2
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3]

    def test_chunk_list_exact_fit(self, orchestrator):
        """Test list chunking with exact fit."""
        items = [1, 2, 3, 4]
        chunks = list(orchestrator._chunk_list(items, 2))

        assert len(chunks) == 2
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]

    def test_chunk_list_large_chunk_size(self, orchestrator):
        """Test list chunking with large chunk size."""
        items = [1, 2, 3]
        chunks = list(orchestrator._chunk_list(items, 10))

        assert len(chunks) == 1
        assert chunks[0] == [1, 2, 3]
