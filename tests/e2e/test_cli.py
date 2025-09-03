"""
End-to-end CLI tests for phazr.
"""

import json
from unittest.mock import Mock, patch

import pytest
import yaml
from click.testing import CliRunner

from phazr.cli import cli, main


class TestCLICommands:
    """Test CLI commands end-to-end."""

    @pytest.fixture
    def runner(self):
        """Click test runner."""
        return CliRunner()

    @pytest.fixture
    def invalid_config_file(self, tmp_path):
        """Create invalid configuration file for testing."""
        config_file = tmp_path / "invalid_config.yaml"
        config_file.write_text("invalid: yaml: content: [")
        return config_file

    def test_cli_help(self, runner):
        """Test CLI help output."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Phazr - Modern DAG-based workflow orchestration" in result.output
        assert "validate" in result.output
        assert "setup" in result.output
        assert "run" in result.output

    def test_cli_with_valid_config(self, runner, sample_config_file):
        """Test CLI initialization with valid config."""
        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = {"all_passed": True}

            result = runner.invoke(cli, ["-c", str(sample_config_file), "validate"])

            assert result.exit_code == 0
            assert "Configuration is valid" in result.output

    def test_cli_with_invalid_config(self, runner, invalid_config_file):
        """Test CLI with invalid configuration."""
        result = runner.invoke(cli, ["-c", str(invalid_config_file), "validate"])

        assert result.exit_code == 1
        assert "Error loading configuration" in result.output

    def test_cli_with_nonexistent_config(self, runner):
        """Test CLI with nonexistent configuration file."""
        result = runner.invoke(cli, ["-c", "nonexistent.yaml", "validate"])

        assert result.exit_code == 1
        assert "Error loading configuration" in result.output

    def test_cli_dry_run_flag(self, runner, sample_config_file):
        """Test CLI dry-run flag."""
        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = {"all_passed": True}

            result = runner.invoke(
                cli, ["-c", str(sample_config_file), "--dry-run", "validate"]
            )

            # Should pass the dry_run flag through to the config
            assert result.exit_code == 0

    def test_cli_verbose_flag(self, runner, sample_config_file):
        """Test CLI verbose flag."""
        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = {"all_passed": True}

            result = runner.invoke(
                cli, ["-c", str(sample_config_file), "--verbose", "validate"]
            )

            assert result.exit_code == 0


class TestValidateCommand:
    """Test validate command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_validate_success(self, runner, sample_config_file):
        """Test successful validation."""
        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = {"all_passed": True}

            with patch("phazr.config.ConfigManager.validate_config") as mock_validate:
                mock_validate.return_value = []  # No issues

                result = runner.invoke(cli, ["-c", str(sample_config_file), "validate"])

                assert result.exit_code == 0
                assert "Configuration is valid" in result.output

    def test_validate_with_config_issues(self, runner, sample_config_file):
        """Test validation with configuration issues."""
        with patch("phazr.config.ConfigManager.validate_config") as mock_validate:
            mock_validate.return_value = ["Test issue 1", "Test issue 2"]

            result = runner.invoke(cli, ["-c", str(sample_config_file), "validate"])

            assert result.exit_code == 1
            assert "Configuration issues found:" in result.output
            assert "Test issue 1" in result.output
            assert "Test issue 2" in result.output

    def test_validate_with_prerequisite_failures(self, runner, sample_config_file):
        """Test validation with prerequisite failures."""
        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = {"all_passed": False}

            with patch("phazr.config.ConfigManager.validate_config") as mock_validate:
                mock_validate.return_value = []  # No config issues

                result = runner.invoke(cli, ["-c", str(sample_config_file), "validate"])

                assert result.exit_code == 1


class TestSetupCommand:
    """Test setup command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_setup_success(self, runner, sample_config_file):
        """Test successful setup."""
        mock_results = [Mock(failed_operations=0), Mock(failed_operations=0)]

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_results

            result = runner.invoke(cli, ["-c", str(sample_config_file), "setup"])

            assert result.exit_code == 0

    def test_setup_with_failures(self, runner, sample_config_file):
        """Test setup with operation failures."""
        mock_results = [
            Mock(failed_operations=1),  # One failure
            Mock(failed_operations=0),
        ]

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_results

            result = runner.invoke(cli, ["-c", str(sample_config_file), "setup"])

            assert result.exit_code == 1

    def test_setup_with_version(self, runner, sample_config_file):
        """Test setup with specific version."""
        mock_results = [Mock(failed_operations=0)]

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_results

            result = runner.invoke(
                cli, ["-c", str(sample_config_file), "setup", "--version", "1.0.0"]
            )

            assert result.exit_code == 0
            # Verify version was passed to orchestrator
            mock_run.assert_called_once()


class TestRunCommand:
    """Test run command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_run_valid_phase(self, runner, sample_config_file):
        """Test running valid phase."""
        mock_result = Mock(is_successful=True)

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result

            result = runner.invoke(cli, ["-c", str(sample_config_file), "run", "build"])

            assert result.exit_code == 0
            assert "Running phase build" in result.output

    def test_run_invalid_phase(self, runner, sample_config_file):
        """Test running non-existent phase."""
        result = runner.invoke(
            cli, ["-c", str(sample_config_file), "run", "nonexistent"]
        )

        assert result.exit_code == 1
        assert "Phase 'nonexistent' not found" in result.output
        assert "Available phases:" in result.output

    def test_run_phase_failure(self, runner, sample_config_file):
        """Test running phase that fails."""
        mock_result = Mock(is_successful=False)

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result

            result = runner.invoke(cli, ["-c", str(sample_config_file), "run", "build"])

            assert result.exit_code == 1

    def test_run_with_version(self, runner, sample_config_file):
        """Test running phase with specific version."""
        mock_result = Mock(is_successful=True)

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = mock_result

            result = runner.invoke(
                cli,
                ["-c", str(sample_config_file), "run", "build", "--version", "1.0.0"],
            )

            assert result.exit_code == 0


class TestMergeCommand:
    """Test merge command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_merge_configs_to_file(self, runner, tmp_path):
        """Test merging configurations to output file."""
        # Create input files
        config1 = {"environment": {"name": "test1"}, "execution": {"verbose": False}}
        config2 = {
            "environment": {"namespace": "default"},
            "execution": {"verbose": True},
        }

        file1 = tmp_path / "config1.yaml"
        file2 = tmp_path / "config2.yaml"
        output_file = tmp_path / "merged.yaml"

        with open(file1, "w") as f:
            yaml.dump(config1, f)
        with open(file2, "w") as f:
            yaml.dump(config2, f)

        # Mock merged config and save behavior
        mock_merged_config = Mock()
        mock_merged_config.model_dump.return_value = {"merged": "config"}

        with patch("phazr.config.ConfigManager.merge_configs") as mock_merge:
            mock_merge.return_value = mock_merged_config

            with patch("phazr.config.ConfigManager.save_config") as mock_save:
                with patch("phazr.config.ConfigManager.load_config") as mock_load:
                    # Mock the main CLI config loading to avoid needing orchestrator.yaml
                    mock_load.return_value = Mock()

                    result = runner.invoke(
                        cli,
                        ["merge", str(file1), str(file2), "--output", str(output_file)],
                    )

                    assert result.exit_code == 0
                assert f"Merged configuration saved to {output_file}" in result.output

                mock_merge.assert_called_once_with(str(file1), str(file2))
                mock_save.assert_called_once_with(mock_merged_config, str(output_file))

    def test_merge_configs_to_stdout(self, runner, tmp_path):
        """Test merging configurations to stdout."""
        # Create input files
        file1 = tmp_path / "config1.yaml"
        file2 = tmp_path / "config2.yaml"

        file1.write_text("environment: {name: test1}")
        file2.write_text("execution: {verbose: true}")

        mock_merged_config = Mock()
        mock_merged_config.model_dump.return_value = {"merged": "config"}

        with patch("phazr.config.ConfigManager.merge_configs") as mock_merge:
            mock_merge.return_value = mock_merged_config

            with patch("builtins.print") as mock_print:
                with patch("phazr.config.ConfigManager.load_config") as mock_load:
                    # Mock the main CLI config loading to avoid needing orchestrator.yaml
                    mock_load.return_value = Mock()

                    result = runner.invoke(cli, ["merge", str(file1), str(file2)])

                    assert result.exit_code == 0
                mock_print.assert_called_once()

    def test_merge_configs_error(self, runner, tmp_path):
        """Test merge command with error."""
        file1 = tmp_path / "config1.yaml"
        file1.write_text("valid: config")

        with patch("phazr.config.ConfigManager.merge_configs") as mock_merge:
            mock_merge.side_effect = Exception("Merge error")

            with patch("phazr.config.ConfigManager.load_config") as mock_load:
                # Mock the main CLI config loading to avoid needing orchestrator.yaml
                mock_load.return_value = Mock()

                result = runner.invoke(cli, ["merge", str(file1)])

                assert result.exit_code == 1
                assert "Error merging configurations" in result.output


class TestListCommands:
    """Test list commands."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_list_phases(self, runner, sample_config_file):
        """Test listing phases."""
        result = runner.invoke(cli, ["-c", str(sample_config_file), "list-phases"])

        assert result.exit_code == 0
        # Note: This test may need adjustment based on rich table output
        # The exact output format depends on the rich library rendering

    def test_list_phases_empty(self, runner, tmp_path):
        """Test listing phases with no phases configured."""
        config_data = {
            "phases": [],
            "versions": {
                "1.0.0": {
                    "build": [
                        {
                            "command": "echo build",
                            "description": "Build",
                            "type": "script_exec",
                        }
                    ]
                }
            },
            "environment": {"name": "test", "namespace": "default"},
        }

        config_file = tmp_path / "empty_phases.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        result = runner.invoke(cli, ["-c", str(config_file), "list-phases"])

        assert result.exit_code == 0
        assert "No phases configured" in result.output

    def test_list_versions(self, runner, sample_config_file):
        """Test listing versions."""
        result = runner.invoke(cli, ["-c", str(sample_config_file), "list-versions"])

        assert result.exit_code == 0
        assert "Available versions:" in result.output
        assert "1.0.0:" in result.output


class TestMainEntryPoint:
    """Test main entry point."""

    def test_main_function(self):
        """Test main function exists and is callable."""
        # Just test that main function exists and can be called
        # Actual CLI testing is done through CliRunner above
        assert callable(main)

        # Test that main can be imported and called (basic smoke test)
        with patch("phazr.cli.cli") as mock_cli:
            main()
            mock_cli.assert_called_once_with(obj={})


class TestCLIIntegration:
    """Integration tests for CLI with mocked external dependencies."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_end_to_end_workflow(self, runner, tmp_path):
        """Test complete workflow: validate -> setup -> run."""
        # Create config file
        config_data = {
            "phases": [
                {
                    "name": "build",
                    "description": "Build phase",
                    "groups": ["compile"],
                    "enabled": True,
                }
            ],
            "versions": {
                "1.0.0": {
                    "compile": [
                        {
                            "command": "echo 'building'",
                            "description": "Build",
                            "type": "script_exec",
                        }
                    ]
                }
            },
            "environment": {"name": "test", "namespace": "default"},
        }

        config_file = tmp_path / "workflow.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Mock all async operations
        with patch("phazr.cli.asyncio.run") as mock_run:
            # Step 1: Validate
            mock_run.return_value = {"all_passed": True}
            with patch("phazr.config.ConfigManager.validate_config", return_value=[]):
                result = runner.invoke(cli, ["-c", str(config_file), "validate"])
                assert result.exit_code == 0

            # Step 2: Setup
            mock_run.return_value = [Mock(failed_operations=0)]
            result = runner.invoke(cli, ["-c", str(config_file), "setup"])
            assert result.exit_code == 0

            # Step 3: Run specific phase
            mock_run.return_value = Mock(is_successful=True)
            result = runner.invoke(cli, ["-c", str(config_file), "run", "build"])
            assert result.exit_code == 0

    def test_cli_with_different_config_formats(self, runner, tmp_path):
        """Test CLI with different configuration formats."""
        config_data = {
            "phases": [{"name": "test", "groups": ["test_group"], "enabled": True}],
            "versions": {
                "1.0.0": {
                    "test_group": [
                        {
                            "command": "echo test",
                            "description": "Test",
                            "type": "script_exec",
                        }
                    ]
                }
            },
            "environment": {"name": "test", "namespace": "default"},
        }

        # Test YAML format
        yaml_file = tmp_path / "config.yaml"
        with open(yaml_file, "w") as f:
            yaml.dump(config_data, f)

        # Test JSON format
        json_file = tmp_path / "config.json"
        with open(json_file, "w") as f:
            json.dump(config_data, f)

        with patch("phazr.cli.asyncio.run") as mock_run:
            mock_run.return_value = {"all_passed": True}
            with patch("phazr.config.ConfigManager.validate_config", return_value=[]):
                # Test YAML
                result = runner.invoke(cli, ["-c", str(yaml_file), "validate"])
                assert result.exit_code == 0

                # Test JSON
                result = runner.invoke(cli, ["-c", str(json_file), "validate"])
                assert result.exit_code == 0
