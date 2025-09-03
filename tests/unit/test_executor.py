"""
Unit tests for orchestration executor functionality - focused on behavior verification.
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
    """Test Orchestrator behavior and workflow execution."""

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
        """Create orchestrator instance with mocked dependencies."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager") as mock_display:
            mock_display.return_value.verbose = False
            return Orchestrator(sample_config)

    def test_orchestrator_initialization_creates_required_components(self, sample_config):
        """Test that orchestrator initializes with all required components."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager"):
            orchestrator = Orchestrator(sample_config)

            assert orchestrator.config == sample_config
            assert orchestrator.handler_registry is not None
            assert orchestrator.validator is not None
            assert orchestrator.display is not None

    def test_orchestrator_accepts_custom_components(self, sample_config):
        """Test that orchestrator accepts custom component implementations."""
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

    def test_required_tools_detection_identifies_kubectl_operations(self, sample_config):
        """Test that orchestrator correctly identifies required tools from operations."""
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

    def test_required_tools_detection_excludes_unused_tools(self, sample_config):
        """Test that orchestrator doesn't require tools for operations not present."""
        with patch("phazr.executor.HandlerRegistry"), patch(
            "phazr.executor.PrerequisiteValidator"
        ), patch("phazr.executor.DisplayManager"):
            orchestrator = Orchestrator(sample_config)

            tools = orchestrator._get_required_tools()

            assert "kubectl" not in tools

    @pytest.mark.asyncio
    async def test_prerequisite_validation_returns_validator_results(self, orchestrator):
        """Test that prerequisite validation delegates to validator and returns results."""
        expected_results = {"all_passed": True, "results": []}
        orchestrator.validator.validate = AsyncMock(return_value=expected_results)

        results = await orchestrator.validate_prerequisites()

        assert results == expected_results
        orchestrator.validator.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_setup_executes_all_enabled_phases(self, orchestrator, sample_config):
        """Test that full setup executes all enabled phases in order."""
        # Mock phase execution to return success
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

        results = await orchestrator.run_full_setup("1.0.0")

        assert len(results) == 1
        assert results[0].phase_name == "test_phase"
        assert results[0].is_successful

    @pytest.mark.asyncio
    async def test_full_setup_skips_disabled_phases(self, orchestrator, sample_config):
        """Test that full setup skips phases marked as disabled."""
        # Disable the phase
        sample_config.phases[0].enabled = False

        results = await orchestrator.run_full_setup("1.0.0")

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_full_setup_respects_phase_dependencies(self, orchestrator, sample_config):
        """Test that full setup respects phase dependency requirements."""
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

        results = await orchestrator.run_full_setup("1.0.0")

        # Should only run the first phase, skip the dependent one
        assert len(results) == 1
        assert results[0].phase_name == "test_phase"

    @pytest.mark.asyncio
    async def test_full_setup_stops_on_phase_failure(self, orchestrator, sample_config):
        """Test that full setup stops execution when a phase fails."""
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

        results = await orchestrator.run_full_setup("1.0.0")

        # Should stop after first failed phase
        assert len(results) == 1
        assert not results[0].is_successful

    @pytest.mark.asyncio
    async def test_run_phase_executes_configured_operations(
        self, orchestrator, sample_config, sample_phase
    ):
        """Test that running a phase executes its configured operations."""
        # Mock sequential execution to return success
        mock_result = ExecutionResult(
            operation=sample_config.versions["1.0.0"].groups["group1"][0],
            success=True,
            duration=1.0,
        )
        orchestrator._execute_sequential = AsyncMock(return_value=[mock_result])

        result = await orchestrator.run_phase(sample_phase, "1.0.0")

        assert result.phase_name == "test_phase"
        assert result.successful_operations == 1
        assert result.failed_operations == 0
        orchestrator._execute_sequential.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_phase_handles_empty_operation_groups(self, orchestrator):
        """Test that running a phase with no operations handles gracefully."""
        empty_phase = Phase(name="empty_phase", groups=["nonexistent_group"])

        result = await orchestrator.run_phase(empty_phase, "1.0.0")

        assert result.total_operations == 0
        assert result.successful_operations == 0

    @pytest.mark.asyncio
    async def test_run_phase_uses_parallel_execution_when_enabled(
        self, orchestrator, sample_config, sample_phase
    ):
        """Test that phase uses parallel execution when configured."""
        sample_config.execution.parallel = True
        sample_phase.parallel_groups = True

        orchestrator._is_group_parallelizable = Mock(return_value=True)
        mock_result = ExecutionResult(
            operation=sample_config.versions["1.0.0"].groups["group1"][0],
            success=True,
            duration=1.0,
        )
        orchestrator._execute_parallel = AsyncMock(return_value=[mock_result])

        result = await orchestrator.run_phase(sample_phase, "1.0.0")

        assert result.successful_operations == 1
        orchestrator._execute_parallel.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_phase_by_name_finds_and_executes_phase(self, orchestrator):
        """Test that running phase by name finds the correct phase configuration."""
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
    async def test_run_phase_by_name_raises_error_for_unknown_phase(self, orchestrator):
        """Test that running unknown phase by name raises appropriate error."""
        with pytest.raises(ValueError, match="Phase 'nonexistent' not found"):
            await orchestrator.run_phase_by_name("nonexistent")

    @pytest.mark.asyncio
    async def test_run_phase_raises_error_for_unknown_version(self, orchestrator, sample_phase):
        """Test that running phase with unknown version raises appropriate error."""
        with pytest.raises(
            ValueError, match="Version nonexistent not found in configuration"
        ):
            await orchestrator.run_phase(sample_phase, "nonexistent")

    def test_parallel_safety_check_identifies_safe_operations(self, orchestrator):
        """Test that parallelization safety check correctly identifies safe operations."""
        safe_ops = [
            Operation(
                command="echo test",
                description="Safe op",
                type=OperationType.SCRIPT_EXEC,
            )
        ]

        assert orchestrator._is_group_parallelizable(safe_ops) is True

    def test_parallel_safety_check_identifies_unsafe_operations(self, orchestrator):
        """Test that parallelization safety check identifies operations that cannot run in parallel."""
        unsafe_ops = [
            Operation(
                command="kubectl restart",
                description="Unsafe op",
                type=OperationType.KUBECTL_RESTART,
            )
        ]

        assert orchestrator._is_group_parallelizable(unsafe_ops) is False

    @pytest.mark.asyncio
    async def test_sequential_execution_processes_operations_in_order(
        self, orchestrator, sample_operation
    ):
        """Test that sequential execution processes operations in the correct order."""
        orchestrator._execute_operation = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        results = await orchestrator._execute_sequential([sample_operation])

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_sequential_execution_stops_on_failure_when_required(
        self, orchestrator, sample_operation
    ):
        """Test that sequential execution stops when an operation fails and fail_on_error is true."""
        sample_operation.fail_on_error = True

        orchestrator._execute_operation = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=False,
                error="Test error",
                duration=1.0,
            )
        )

        results = await orchestrator._execute_sequential([sample_operation, sample_operation])

        # Should stop after first failure
        assert len(results) == 1
        assert results[0].success is False

    @pytest.mark.asyncio
    async def test_dry_run_mode_creates_preview_results(self, orchestrator, sample_operation):
        """Test that dry run mode creates preview results without executing operations."""
        orchestrator.config.execution.dry_run = True

        results = await orchestrator._execute_sequential([sample_operation])

        assert len(results) == 1
        assert results[0].success is True
        assert "[DRY RUN]" in results[0].output

    @pytest.mark.asyncio
    async def test_parallel_execution_processes_operations_concurrently(
        self, orchestrator, sample_operation
    ):
        """Test that parallel execution can process multiple operations concurrently."""
        orchestrator._execute_operation = AsyncMock(
            return_value=ExecutionResult(
                operation=sample_operation,
                success=True,
                duration=1.0,
            )
        )

        results = await orchestrator._execute_parallel([sample_operation])

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_parallel_execution_handles_operation_exceptions(
        self, orchestrator, sample_operation
    ):
        """Test that parallel execution gracefully handles operation exceptions."""
        orchestrator._execute_operation = AsyncMock(side_effect=Exception("Test error"))

        results = await orchestrator._execute_parallel([sample_operation])

        assert len(results) == 1
        assert results[0].success is False
        assert "Test error" in results[0].error

    @pytest.mark.asyncio
    async def test_operation_execution_delegates_to_appropriate_handler(
        self, orchestrator, sample_operation
    ):
        """Test that operation execution finds and uses the appropriate handler."""
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
    async def test_operation_execution_skips_when_condition_met(
        self, orchestrator, sample_operation
    ):
        """Test that operations are skipped when skip conditions are met."""
        sample_operation.skip_if = "test_condition"

        orchestrator._evaluate_condition = AsyncMock(return_value=True)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is True
        assert "skipped" in result.output.lower()

    @pytest.mark.asyncio
    async def test_operation_execution_fails_gracefully_without_handler(
        self, orchestrator, sample_operation
    ):
        """Test that operation execution fails gracefully when no handler is available."""
        orchestrator.handler_registry.get_handler = Mock(return_value=None)
        orchestrator._evaluate_condition = AsyncMock(return_value=False)

        result = await orchestrator._execute_operation(sample_operation)

        assert result.success is False
        assert "No handler registered" in result.error

    @pytest.mark.asyncio
    async def test_operation_execution_retries_on_failure(self, orchestrator, sample_operation):
        """Test that operation execution implements retry logic for failed operations."""
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
    async def test_operation_execution_fails_after_exhausting_retries(
        self, orchestrator, sample_operation
    ):
        """Test that operation execution fails after exhausting all retry attempts."""
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
    async def test_operation_execution_validates_with_test_command(
        self, orchestrator, sample_operation
    ):
        """Test that operation execution runs test commands to validate success."""
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
    async def test_operation_execution_fails_on_test_command_failure(
        self, orchestrator, sample_operation
    ):
        """Test that operation execution fails when test command validation fails."""
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

    def test_dry_run_result_creation_produces_preview(self, orchestrator, sample_operation):
        """Test that dry run result creation produces appropriate preview information."""
        result = orchestrator._create_dry_run_result(sample_operation)

        assert result.operation == sample_operation
        assert result.success is True
        assert "[DRY RUN]" in result.output
        assert result.duration == 0.0

    def test_list_chunking_splits_correctly(self, orchestrator):
        """Test that list chunking utility splits lists into appropriate chunks."""
        items = [1, 2, 3, 4, 5]
        chunks = list(orchestrator._chunk_list(items, 2))

        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5]

    def test_list_chunking_handles_large_chunk_size(self, orchestrator):
        """Test that list chunking handles chunk sizes larger than the list."""
        items = [1, 2, 3]
        chunks = list(orchestrator._chunk_list(items, 10))

        assert len(chunks) == 1
        assert chunks[0] == [1, 2, 3]