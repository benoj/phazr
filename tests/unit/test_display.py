"""
Unit tests for display manager functionality.
"""

import time
from unittest.mock import Mock, patch

import pytest

from phazr.display import DisplayManager
from phazr.models import (
    ExecutionResult,
    Operation,
    OperationType,
    Phase,
    PhaseResult,
)


class TestDisplayManager:
    """Test DisplayManager class functionality."""

    @pytest.fixture
    def display_manager(self):
        """Create DisplayManager instance for testing."""
        return DisplayManager(verbose=False)

    @pytest.fixture
    def verbose_display_manager(self):
        """Create verbose DisplayManager instance for testing."""
        return DisplayManager(verbose=True)

    @pytest.fixture
    def mock_console(self):
        """Mock Rich console."""
        with patch("phazr.display.Console") as mock_console_class:
            mock_console = Mock()
            mock_console_class.return_value = mock_console
            yield mock_console

    @pytest.fixture
    def sample_operation(self):
        """Sample operation for testing."""
        return Operation(
            command="echo 'test'",
            description="Test operation",
            type=OperationType.SCRIPT_EXEC,
        )

    @pytest.fixture
    def sample_phase(self):
        """Sample phase for testing."""
        return Phase(
            name="test_phase",
            description="Test phase description",
            groups=["group1"],
            icon="🧪",
        )

    def test_init_default(self):
        """Test DisplayManager initialization with defaults."""
        dm = DisplayManager()
        assert dm.verbose is False
        assert dm._current_phase is None
        assert dm._start_time is None
        assert dm.console is not None

    def test_init_with_verbose(self):
        """Test DisplayManager initialization with verbose=True."""
        dm = DisplayManager(verbose=True)
        assert dm.verbose is True

    def test_print_header(self, mock_console):
        """Test header printing."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.print_header()

        # Should call print twice (logo and empty line)
        assert mock_console.print.call_count == 2

    def test_print_config_info_basic(self, mock_console):
        """Test config info display with basic config."""
        dm = DisplayManager()
        dm.console = mock_console

        config = {
            "environment": {"name": "test", "namespace": "test-ns"},
            "execution": {"dry_run": True, "parallel": False},
        }

        dm.print_config_info(config)

        # Should call print twice (table and empty line)
        assert mock_console.print.call_count == 2

    def test_print_config_info_with_context(self, mock_console):
        """Test config info display with context."""
        dm = DisplayManager()
        dm.console = mock_console

        config = {
            "environment": {
                "name": "test",
                "namespace": "test-ns",
                "context": "test-context",
            },
            "execution": {"dry_run": False, "parallel": True},
        }

        dm.print_config_info(config)

        assert mock_console.print.call_count == 2

    def test_print_config_info_empty_config(self, mock_console):
        """Test config info display with empty config."""
        dm = DisplayManager()
        dm.console = mock_console

        config = {}

        dm.print_config_info(config)

        assert mock_console.print.call_count == 2

    def test_start_phase_with_icon(self, mock_console, sample_phase):
        """Test phase start with custom icon."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.start_phase(sample_phase, 5)

        assert dm._current_phase == "test_phase"
        assert dm._start_time is not None
        # Should print 5 times (empty line + 4 header lines)
        assert mock_console.print.call_count == 5

    def test_start_phase_without_icon(self, mock_console):
        """Test phase start without custom icon."""
        dm = DisplayManager()
        dm.console = mock_console

        phase = Phase(
            name="services", description="Service operations", groups=["group1"]
        )

        dm.start_phase(phase, 3)

        assert dm._current_phase == "services"
        assert mock_console.print.call_count == 5

    def test_start_phase_with_keyword_match(self, mock_console):
        """Test phase start with keyword matching for icon."""
        dm = DisplayManager()
        dm.console = mock_console

        phase = Phase(
            name="database_migrations", description="DB operations", groups=["group1"]
        )

        dm.start_phase(phase, 2)

        assert dm._current_phase == "database_migrations"
        assert mock_console.print.call_count == 5

    def test_start_phase_no_description(self, mock_console):
        """Test phase start without description."""
        dm = DisplayManager()
        dm.console = mock_console

        phase = Phase(name="test", groups=["group1"])

        dm.start_phase(phase, 1)

        assert mock_console.print.call_count == 5

    def test_show_operation_progress(self, display_manager, sample_operation):
        """Test operation progress display."""
        progress = display_manager.show_operation_progress(sample_operation, 1, 5)

        # Should return a Progress object
        assert progress is not None

    def test_show_operation_start_basic(self, mock_console, sample_operation):
        """Test basic operation start display."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.show_operation_start(sample_operation, 1, 5)

        # Should print once for the operation line
        assert mock_console.print.call_count == 1

    def test_show_operation_start_verbose(self, mock_console, sample_operation):
        """Test verbose operation start display."""
        dm = DisplayManager(verbose=True)
        dm.console = mock_console

        dm.show_operation_start(sample_operation, 1, 5)

        # Should print operation line + command line
        assert mock_console.print.call_count == 2

    def test_show_operation_start_verbose_multiline_command(self, mock_console):
        """Test verbose operation start with multiline command."""
        dm = DisplayManager(verbose=True)
        dm.console = mock_console

        operation = Operation(
            command="line1\nline2\nline3\nline4",
            description="Multi-line test",
            type=OperationType.SCRIPT_EXEC,
        )

        dm.show_operation_start(operation, 1, 5)

        # Should print operation line + max 3 command lines
        assert mock_console.print.call_count == 4

    def test_show_operation_start_long_command(self, mock_console):
        """Test operation start with long command."""
        dm = DisplayManager(verbose=True)
        dm.console = mock_console

        operation = Operation(
            command="a" * 200,
            description="Long command test",
            type=OperationType.SCRIPT_EXEC,
        )

        dm.show_operation_start(operation, 1, 5)

        assert mock_console.print.call_count == 2

    def test_show_operation_start_different_types(self, mock_console):
        """Test operation start with different operation types."""
        dm = DisplayManager()
        dm.console = mock_console

        types_to_test = [
            OperationType.KUBECTL_EXEC,
            OperationType.KUBECTL_RESTART,
            OperationType.HTTP_REQUEST,
            OperationType.CUSTOM,
            OperationType.SKIP,
        ]

        for op_type in types_to_test:
            operation = Operation(
                command="test",
                description=f"Test {op_type}",
                type=op_type,
            )
            dm.show_operation_start(operation, 1, 1)

        # Should print once for each operation
        assert mock_console.print.call_count == len(types_to_test)

    def test_show_operation_result_success(self, mock_console, sample_operation):
        """Test successful operation result display."""
        dm = DisplayManager()
        dm.console = mock_console

        result = ExecutionResult(
            operation=sample_operation,
            success=True,
            output="Success output",
            duration=1.5,
        )

        dm.show_operation_result(result, 1, 5)

        assert mock_console.print.call_count == 1

    def test_show_operation_result_failed(self, mock_console, sample_operation):
        """Test failed operation result display."""
        dm = DisplayManager()
        dm.console = mock_console

        result = ExecutionResult(
            operation=sample_operation,
            success=False,
            error="Test error message",
            duration=2.0,
        )

        dm.show_operation_result(result, 1, 5)

        # Should print result line + error line
        assert mock_console.print.call_count == 2

    def test_show_operation_result_skipped(self, mock_console):
        """Test skipped operation result display."""
        dm = DisplayManager()
        dm.console = mock_console

        operation = Operation(
            command="test",
            description="Skipped test",
            type=OperationType.SKIP,
        )

        result = ExecutionResult(
            operation=operation,
            success=True,
            duration=0.0,
        )

        dm.show_operation_result(result, 1, 5)

        assert mock_console.print.call_count == 1

    def test_show_operation_result_verbose_with_output(
        self, mock_console, sample_operation
    ):
        """Test verbose operation result with output."""
        dm = DisplayManager(verbose=True)
        dm.console = mock_console

        result = ExecutionResult(
            operation=sample_operation,
            success=True,
            output="Verbose output line 1\nVerbose output line 2",
            duration=1.0,
        )

        dm.show_operation_result(result, 1, 5)

        # Should print result line + output lines
        assert mock_console.print.call_count == 3

    def test_show_operation_result_multiline_error(
        self, mock_console, sample_operation
    ):
        """Test operation result with multiline error."""
        dm = DisplayManager()
        dm.console = mock_console

        result = ExecutionResult(
            operation=sample_operation,
            success=False,
            error="Error line 1\nError line 2\nError line 3",
            duration=1.0,
        )

        dm.show_operation_result(result, 1, 5)

        # Should print result line + max 2 error lines
        assert mock_console.print.call_count == 3

    def test_show_phase_summary_success(self, mock_console, sample_phase):
        """Test phase summary for successful phase."""
        dm = DisplayManager()
        dm.console = mock_console
        dm._start_time = time.time() - 10  # 10 seconds ago

        phase_result = PhaseResult(
            phase_name="test_phase",
            phase_config=sample_phase,
            version="1.0",
            results=[],
            total_operations=5,
            successful_operations=5,
            failed_operations=0,
            skipped_operations=0,
            duration=9.5,
        )

        dm.show_phase_summary(phase_result)

        # Should print 3 lines (separator, summary, closing)
        assert mock_console.print.call_count == 4

    def test_show_phase_summary_partial_failure(self, mock_console, sample_phase):
        """Test phase summary for partially failed phase."""
        dm = DisplayManager()
        dm.console = mock_console
        dm._start_time = None  # Use phase duration

        phase_result = PhaseResult(
            phase_name="test_phase",
            phase_config=sample_phase,
            version="1.0",
            results=[],
            total_operations=5,
            successful_operations=3,
            failed_operations=1,
            skipped_operations=1,
            duration=15.0,
        )

        dm.show_phase_summary(phase_result)

        assert mock_console.print.call_count == 4

    def test_show_phase_summary_total_failure(self, mock_console, sample_phase):
        """Test phase summary for completely failed phase."""
        dm = DisplayManager()
        dm.console = mock_console
        dm._start_time = time.time() - 5

        phase_result = PhaseResult(
            phase_name="test_phase",
            phase_config=sample_phase,
            version="1.0",
            results=[],
            total_operations=3,
            successful_operations=0,
            failed_operations=3,
            skipped_operations=0,
            duration=4.5,
        )

        dm.show_phase_summary(phase_result)

        assert mock_console.print.call_count == 4

    def test_show_validation_results_all_passed(self, mock_console):
        """Test validation results display with all passed."""
        dm = DisplayManager()
        dm.console = mock_console

        results = {
            "all_passed": True,
            "results": [
                {"status": "passed", "tool": "kubectl", "version": "1.25.0"},
                {"status": "passed", "tool": "python", "version": "3.11.0"},
            ],
        }

        dm.show_validation_results(results)

        # Should print table + success panel
        assert mock_console.print.call_count == 2

    def test_show_validation_results_with_failures(self, mock_console):
        """Test validation results display with failures."""
        dm = DisplayManager()
        dm.console = mock_console

        results = {
            "all_passed": False,
            "results": [
                {"status": "failed", "tool": "kubectl", "message": "Not found"},
                {"status": "passed", "tool": "python", "version": "3.11.0"},
            ],
        }

        dm.show_validation_results(results)

        # Should print table + failure panel
        assert mock_console.print.call_count == 2

    def test_show_validation_results_kubernetes_checks(self, mock_console):
        """Test validation results with kubernetes-style checks."""
        dm = DisplayManager()
        dm.console = mock_console

        results = {
            "all_passed": False,
            "results": [
                {
                    "status": "failed",
                    "checks": [
                        {"passed": True, "message": "Context OK"},
                        {"passed": False, "message": "Namespace not found"},
                    ],
                }
            ],
        }

        dm.show_validation_results(results)

        assert mock_console.print.call_count == 2

    def test_show_validation_results_unknown_format(self, mock_console):
        """Test validation results with unknown format."""
        dm = DisplayManager()
        dm.console = mock_console

        results = {
            "all_passed": True,
            "results": [{"status": "unknown", "some_field": "some_value"}],
        }

        dm.show_validation_results(results)

        assert mock_console.print.call_count == 2

    def test_show_final_summary_all_success(self, mock_console):
        """Test final summary with all successful phases."""
        dm = DisplayManager()
        dm.console = mock_console

        phase_results = [
            PhaseResult(
                phase_name="phase1",
                version="1.0",
                results=[],
                total_operations=3,
                successful_operations=3,
                failed_operations=0,
                skipped_operations=0,
                duration=5.0,
            ),
            PhaseResult(
                phase_name="phase2",
                version="1.0",
                results=[],
                total_operations=2,
                successful_operations=2,
                failed_operations=0,
                skipped_operations=0,
                duration=3.0,
            ),
        ]

        dm.show_final_summary(phase_results)

        # Should print multiple lines for the summary
        assert (
            mock_console.print.call_count >= 7
        )  # Header + phases + footer + success panel

    def test_show_final_summary_with_failures(self, mock_console):
        """Test final summary with some failures."""
        dm = DisplayManager()
        dm.console = mock_console

        phase_results = [
            PhaseResult(
                phase_name="phase1",
                version="1.0",
                results=[],
                total_operations=3,
                successful_operations=2,
                failed_operations=1,
                skipped_operations=0,
                duration=5.0,
            ),
        ]

        dm.show_final_summary(phase_results)

        # Should end with failure panel
        assert mock_console.print.call_count >= 6

    def test_show_final_summary_mixed_results(self, mock_console):
        """Test final summary with mixed phase results."""
        dm = DisplayManager()
        dm.console = mock_console

        phase_results = [
            PhaseResult(
                phase_name="success_phase",
                version="1.0",
                results=[],
                total_operations=2,
                successful_operations=2,
                failed_operations=0,
                skipped_operations=0,
                duration=2.0,
            ),
            PhaseResult(
                phase_name="partial_phase",
                version="1.0",
                results=[],
                total_operations=3,
                successful_operations=1,
                failed_operations=1,
                skipped_operations=1,
                duration=3.0,
            ),
            PhaseResult(
                phase_name="failed_phase",
                version="1.0",
                results=[],
                total_operations=1,
                successful_operations=0,
                failed_operations=1,
                skipped_operations=0,
                duration=1.0,
            ),
        ]

        dm.show_final_summary(phase_results)

        assert mock_console.print.call_count >= 8

    def test_error_message(self, mock_console):
        """Test error message display."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.error("Test error message")

        mock_console.print.assert_called_once()

    def test_warning_message(self, mock_console):
        """Test warning message display."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.warning("Test warning message")

        mock_console.print.assert_called_once()

    def test_info_message(self, mock_console):
        """Test info message display."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.info("Test info message")

        mock_console.print.assert_called_once()

    def test_success_message(self, mock_console):
        """Test success message display."""
        dm = DisplayManager()
        dm.console = mock_console

        dm.success("Test success message")

        mock_console.print.assert_called_once()

    def test_show_operation_result_long_error(self, mock_console, sample_operation):
        """Test operation result with long error message."""
        dm = DisplayManager()
        dm.console = mock_console

        # Create error longer than 57 chars to hit line 206
        long_error = "a" * 60
        result = ExecutionResult(
            operation=sample_operation,
            success=False,
            error=long_error,
            duration=1.0,
        )

        dm.show_operation_result(result, 1, 5)

        assert mock_console.print.call_count == 2

    def test_show_operation_result_verbose_long_output(
        self, mock_console, sample_operation
    ):
        """Test verbose operation result with long output."""
        dm = DisplayManager(verbose=True)
        dm.console = mock_console

        # Create output longer than 57 chars to hit line 216
        long_output = "b" * 60
        result = ExecutionResult(
            operation=sample_operation,
            success=True,
            output=long_output,
            duration=1.0,
        )

        dm.show_operation_result(result, 1, 5)

        assert mock_console.print.call_count == 2
