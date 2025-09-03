"""
Unit tests for display manager functionality - focused on behavior verification.
"""
import time
from io import StringIO

import pytest
from rich.console import Console

from phazr.display import DisplayManager
from phazr.models import (
    ExecutionResult,
    Operation,
    OperationType,
    Phase,
    PhaseResult,
)


class TestDisplayManager:
    """Test DisplayManager behavior and outputs."""

    @pytest.fixture
    def display_manager(self):
        """Create DisplayManager instance for testing."""
        return DisplayManager(verbose=False)

    @pytest.fixture
    def verbose_display_manager(self):
        """Create verbose DisplayManager instance for testing."""
        return DisplayManager(verbose=True)

    @pytest.fixture
    def console_output(self):
        """Capture console output for verification."""
        output = StringIO()
        console = Console(file=output, width=80, legacy_windows=False)
        return console, output

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

    def test_init_sets_verbose_mode(self):
        """Test that verbose mode is set correctly during initialization."""
        normal_dm = DisplayManager(verbose=False)
        verbose_dm = DisplayManager(verbose=True)
        
        assert normal_dm.verbose is False
        assert verbose_dm.verbose is True

    def test_print_header_contains_logo(self, console_output):
        """Test that header contains the expected logo content."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        dm.print_header()
        
        content = output.getvalue()
        assert "██████╗" in content  # ASCII art header should be present
        assert "Modern DAG-based workflow orchestration" in content

    def test_print_config_info_displays_environment_details(self, console_output):
        """Test that config info shows environment and execution details."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        config = {
            "environment": {"name": "production", "namespace": "prod-ns", "context": "prod-cluster"},
            "execution": {"dry_run": True, "parallel": True},
        }
        
        dm.print_config_info(config)
        
        content = output.getvalue()
        assert "production" in content
        assert "prod-ns" in content
        assert "prod-cluster" in content
        assert "Yes" in content  # For dry_run and parallel flags

    def test_print_config_info_handles_missing_fields(self, console_output):
        """Test that config info handles missing configuration gracefully."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        config = {}  # Empty config
        
        dm.print_config_info(config)
        
        content = output.getvalue()
        # Should show defaults when fields are missing
        assert "unknown" in content or "default" in content

    def test_start_phase_tracks_current_phase(self, sample_phase):
        """Test that starting a phase correctly tracks the current phase."""
        dm = DisplayManager()
        
        dm.start_phase(sample_phase, 5)
        
        assert dm._current_phase == "test_phase"
        assert dm._start_time is not None

    def test_start_phase_displays_phase_info(self, console_output, sample_phase):
        """Test that phase start displays correct phase information."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        dm.start_phase(sample_phase, 3)
        
        content = output.getvalue()
        assert "TEST_PHASE" in content
        assert "Test phase description" in content
        assert "3 operations" in content

    def test_start_phase_uses_icon_matching(self, console_output):
        """Test that phase start uses appropriate icons for known phase types."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        # Test a phase with keyword matching
        database_phase = Phase(
            name="database_setup",
            description="Database operations",
            groups=["db_group"]
        )
        
        dm.start_phase(database_phase, 1)
        
        content = output.getvalue()
        assert "DATABASE_SETUP" in content

    def test_show_operation_start_displays_operation_info(self, console_output, sample_operation):
        """Test that operation start shows operation details."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        dm.show_operation_start(sample_operation, 2, 5)
        
        content = output.getvalue()
        assert "Test operation" in content
        assert "[" in content and "2" in content and "5" in content  # Check for progress indicator

    def test_show_operation_start_verbose_includes_command(self, console_output):
        """Test that verbose mode shows the actual command being executed."""
        console, output = console_output
        dm = DisplayManager(verbose=True)
        dm.console = console
        
        operation = Operation(
            command="kubectl get pods --namespace=test",
            description="List pods",
            type=OperationType.KUBECTL_EXEC,
        )
        
        dm.show_operation_start(operation, 1, 1)
        
        content = output.getvalue()
        assert "List pods" in content
        assert "kubectl get pods --namespace=test" in content

    def test_show_operation_result_success_shows_success_indicator(self, console_output, sample_operation):
        """Test that successful operation results show success indicators."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        result = ExecutionResult(
            operation=sample_operation,
            success=True,
            output="Operation completed successfully",
            duration=1.5,
        )
        
        dm.show_operation_result(result, 1, 5)
        
        content = output.getvalue()
        assert "SUCCESS" in content or "✅" in content
        assert "1.5s" in content

    def test_show_operation_result_failure_shows_error_details(self, console_output, sample_operation):
        """Test that failed operation results show error information."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        result = ExecutionResult(
            operation=sample_operation,
            success=False,
            error="Connection timeout after 30 seconds",
            duration=30.1,
        )
        
        dm.show_operation_result(result, 1, 5)
        
        content = output.getvalue()
        assert "FAILED" in content or "❌" in content
        assert "Connection timeout" in content
        assert "30.1s" in content

    def test_show_operation_result_skip_shows_skip_indicator(self, console_output):
        """Test that skipped operations show appropriate indicators."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        skip_operation = Operation(
            command="skipped",
            description="Skipped operation",
            type=OperationType.SKIP,
        )
        
        result = ExecutionResult(
            operation=skip_operation,
            success=True,
            duration=0.0,
        )
        
        dm.show_operation_result(result, 1, 5)
        
        content = output.getvalue()
        assert "SKIPPED" in content or "⏭️" in content

    def test_show_phase_summary_calculates_duration(self, console_output, sample_phase):
        """Test that phase summary calculates and displays duration correctly."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        # Set start time to 10 seconds ago
        dm._start_time = time.time() - 10
        
        phase_result = PhaseResult(
            phase_name="test_phase",
            phase_config=sample_phase,
            version="1.0",
            results=[],
            total_operations=5,
            successful_operations=4,
            failed_operations=1,
            skipped_operations=0,
            duration=9.5,  # This should be overridden by calculated duration
        )
        
        dm.show_phase_summary(phase_result)
        
        content = output.getvalue()
        assert "test_phase" in content
        assert "4 passed" in content
        assert "1 failed" in content
        # Duration should be approximately 10 seconds (calculated from start time)
        assert "10." in content or "9." in content

    def test_show_validation_results_displays_tool_status(self, console_output):
        """Test that validation results show tool availability status."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        results = {
            "all_passed": False,
            "results": [
                {"status": "passed", "tool": "kubectl", "version": "v1.25.0", "message": "kubectl is available"},
                {"status": "failed", "tool": "docker", "message": "docker not found"},
            ]
        }
        
        dm.show_validation_results(results)
        
        content = output.getvalue()
        assert "kubectl" in content
        assert "v1.25.0" in content
        assert "docker" in content
        assert "not found" in content
        assert "Prerequisites validation failed" in content

    def test_show_validation_results_all_passed(self, console_output):
        """Test validation results display when all prerequisites pass."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        results = {
            "all_passed": True,
            "results": [
                {"status": "passed", "tool": "kubectl", "version": "v1.25.0"},
                {"status": "passed", "tool": "python", "version": "3.11.0"},
            ]
        }
        
        dm.show_validation_results(results)
        
        content = output.getvalue()
        assert "All prerequisites validated successfully" in content

    def test_show_final_summary_aggregates_phase_results(self, console_output):
        """Test that final summary correctly aggregates results across phases."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        phase_results = [
            PhaseResult(
                phase_name="setup",
                version="1.0",
                results=[],
                total_operations=3,
                successful_operations=3,
                failed_operations=0,
                skipped_operations=0,
                duration=5.0,
            ),
            PhaseResult(
                phase_name="deploy",
                version="1.0", 
                results=[],
                total_operations=2,
                successful_operations=1,
                failed_operations=1,
                skipped_operations=0,
                duration=3.0,
            ),
        ]
        
        dm.show_final_summary(phase_results)
        
        content = output.getvalue()
        assert "EXECUTION SUMMARY" in content
        assert "setup" in content
        assert "deploy" in content
        # Total: 4 successful, 1 failed
        assert "✓ 4" in content
        assert "✗ 1" in content
        # Total duration: 8.0s
        assert "8.0s" in content

    def test_show_final_summary_success_message(self, console_output):
        """Test final summary shows success message when all operations pass."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        phase_results = [
            PhaseResult(
                phase_name="test",
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
        
        content = output.getvalue()
        assert "Setup completed successfully" in content

    def test_show_final_summary_failure_message(self, console_output):
        """Test final summary shows failure message when operations fail."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        phase_results = [
            PhaseResult(
                phase_name="test",
                version="1.0",
                results=[],
                total_operations=3,
                successful_operations=1,
                failed_operations=2,
                skipped_operations=0,
                duration=5.0,
            ),
        ]
        
        dm.show_final_summary(phase_results)
        
        content = output.getvalue()
        assert "completed with 2 failures" in content

    def test_logging_methods_output_appropriate_messages(self, console_output):
        """Test that logging methods produce correctly formatted output."""
        console, output = console_output
        dm = DisplayManager()
        dm.console = console
        
        test_cases = [
            (dm.error, "Test error", "Error"),
            (dm.warning, "Test warning", "Warning"), 
            (dm.info, "Test info", "Info"),
            (dm.success, "Test success", "Success"),
        ]
        
        for method, message, expected_type in test_cases:
            # Clear output between tests
            output.seek(0)
            output.truncate(0)
            
            method(message)
            content = output.getvalue()
            
            assert expected_type in content
            assert message in content

    def test_verbose_mode_shows_additional_details(self, console_output, sample_operation):
        """Test that verbose mode provides additional operational details."""
        console, output = console_output
        
        # Test with verbose mode off
        normal_dm = DisplayManager(verbose=False)
        normal_dm.console = console
        normal_dm.show_operation_start(sample_operation, 1, 1)
        normal_content = output.getvalue()
        
        # Clear and test with verbose mode on
        output.seek(0)
        output.truncate(0)
        
        verbose_dm = DisplayManager(verbose=True)
        verbose_dm.console = console
        verbose_dm.show_operation_start(sample_operation, 1, 1)
        verbose_content = output.getvalue()
        
        # Verbose should contain the command, normal should not
        assert "echo 'test'" not in normal_content
        assert "echo 'test'" in verbose_content

    def test_operation_progress_returns_progress_object(self, display_manager, sample_operation):
        """Test that operation progress method returns a usable progress object."""
        progress = display_manager.show_operation_progress(sample_operation, 1, 5)
        
        # Should return a Rich Progress object that can be used for tracking
        assert progress is not None
        assert hasattr(progress, 'add_task')  # Rich Progress method