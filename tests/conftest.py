"""
Shared pytest fixtures and test configuration.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any
import pytest
import yaml
from unittest.mock import Mock, AsyncMock

from phazr.models import (
    OrchestratorConfig,
    EnvironmentConfig,
    ExecutionConfig,
    VersionConfig,
    Phase,
    Operation,
    OperationType,
)
from phazr.config import ConfigManager
from phazr.handlers import HandlerRegistry
from phazr.executor import Orchestrator
from phazr.display import DisplayManager


@pytest.fixture
def sample_environment():
    """Sample environment configuration."""
    return EnvironmentConfig(
        name="test",
        namespace="default",
        variables={"TEST_VAR": "test_value"}
    )


@pytest.fixture
def sample_execution_config():
    """Sample execution configuration."""
    return ExecutionConfig(
        dry_run=False,
        verbose=False,
        parallel=True,
        timeout=300,
        log_level="INFO"
    )


@pytest.fixture
def sample_operations():
    """Sample operations for testing."""
    return {
        "build": [
            Operation(
                command="echo 'Building...'",
                description="Build application",
                type=OperationType.SCRIPT_EXEC,
                timeout=60
            )
        ],
        "test": [
            Operation(
                command="echo 'Testing...'",
                description="Run tests",
                type=OperationType.SCRIPT_EXEC,
                timeout=120
            )
        ],
        "deploy": [
            Operation(
                command="echo 'Deploying...'",
                description="Deploy application",
                type=OperationType.SCRIPT_EXEC,
                timeout=180
            )
        ]
    }


@pytest.fixture
def sample_phases():
    """Sample phases for testing."""
    return [
        Phase(
            name="build",
            description="Build phase",
            groups=["build"],
            enabled=True
        ),
        Phase(
            name="test",
            description="Test phase", 
            groups=["test"],
            depends_on=["build"],
            enabled=True
        ),
        Phase(
            name="deploy",
            description="Deploy phase",
            groups=["deploy"],
            depends_on=["test"],
            enabled=True
        )
    ]


@pytest.fixture
def sample_version_config(sample_operations):
    """Sample version configuration."""
    return VersionConfig(
        version="1.0.0",
        groups=sample_operations
    )


@pytest.fixture
def sample_orchestrator_config(
    sample_environment,
    sample_execution_config, 
    sample_phases,
    sample_version_config
):
    """Sample orchestrator configuration."""
    return OrchestratorConfig(
        versions={"1.0.0": sample_version_config},
        phases=sample_phases,
        environment=sample_environment,
        execution=sample_execution_config
    )


@pytest.fixture
def mock_handler_registry():
    """Mock handler registry for testing."""
    registry = Mock(spec=HandlerRegistry)
    registry.get_handler = Mock()
    registry.register = Mock()
    return registry


@pytest.fixture
def mock_display():
    """Mock display manager for testing."""
    display = Mock(spec=DisplayManager)
    display.start_phase = Mock()
    display.end_phase = Mock() 
    display.start_operation = Mock()
    display.end_operation = Mock()
    display.show_error = Mock()
    return display


@pytest.fixture
def temp_config_dir():
    """Temporary directory for test configurations."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_config_yaml():
    """Sample YAML configuration content."""
    return """
phases:
  - name: "build"
    description: "Build the application"
    groups: ["compile"]
    
  - name: "test"
    description: "Test the application"
    groups: ["unit_test", "integration_test"]
    depends_on: ["build"]
    
  - name: "deploy"
    description: "Deploy application"
    groups: ["deployment"]
    depends_on: ["test"]

versions:
  "1.0.0":
    compile:
      - command: "echo 'Building...'"
        description: "Build app"
        type: "script_exec"
        timeout: 300
    
    unit_test:
      - command: "echo 'Unit testing...'"
        description: "Run unit tests"
        type: "script_exec"
        timeout: 600
    
    integration_test:
      - command: "echo 'Integration testing...'"
        description: "Run integration tests"
        type: "script_exec"
        timeout: 900
    
    deployment:
      - command: "echo 'Deploying...'"
        description: "Deploy app"
        type: "script_exec"
        timeout: 1200

environment:
  name: "test"
  namespace: "default"
  variables:
    ENV: "test"
    DEBUG: "true"

execution:
  dry_run: false
  verbose: true
  parallel: true
  timeout: 3600
  log_level: "INFO"
"""


@pytest.fixture
def config_file(temp_config_dir, sample_config_yaml):
    """Create a temporary config file."""
    config_file = temp_config_dir / "test_config.yaml"
    config_file.write_text(sample_config_yaml)
    return config_file


@pytest.fixture
def sample_config_file(tmp_path):
    """Create sample configuration file for CLI testing."""
    config_data = {
        "phases": [
            {
                "name": "build",
                "description": "Build application",
                "groups": ["compile"],
                "enabled": True
            },
            {
                "name": "test",
                "description": "Test application", 
                "groups": ["unit_tests"],
                "depends_on": ["build"],
                "enabled": True
            },
            {
                "name": "deploy",
                "description": "Deploy application",
                "groups": ["deployment"],
                "depends_on": ["test"],
                "enabled": True
            }
        ],
        "versions": {
            "1.0.0": {
                "compile": [
                    {
                        "command": "echo 'Building...'",
                        "description": "Build app",
                        "type": "script_exec",
                        "timeout": 300
                    }
                ],
                "unit_tests": [
                    {
                        "command": "echo 'Testing...'",
                        "description": "Run tests",
                        "type": "script_exec",
                        "timeout": 600
                    }
                ],
                "deployment": [
                    {
                        "command": "echo 'Deploying...'",
                        "description": "Deploy app",
                        "type": "script_exec",
                        "timeout": 1200
                    }
                ]
            }
        },
        "environment": {
            "name": "test",
            "namespace": "default",
            "context": "test-cluster"
        },
        "execution": {
            "dry_run": False,
            "verbose": False,
            "parallel": True,
            "timeout": 3600,
            "log_level": "INFO"
        }
    }
    
    config_file = tmp_path / "test_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    
    return config_file


@pytest.fixture
def config_manager():
    """ConfigManager instance for testing."""
    return ConfigManager()


@pytest.fixture
def orchestrator(sample_orchestrator_config, mock_handler_registry, mock_display):
    """Orchestrator instance for testing."""
    return Orchestrator(
        config=sample_orchestrator_config,
        handler_registry=mock_handler_registry,
        display=mock_display
    )


@pytest.fixture
def mock_subprocess():
    """Mock subprocess for testing script execution."""
    mock = AsyncMock()
    mock.returncode = 0
    mock.stdout = AsyncMock()
    mock.stderr = AsyncMock()
    mock.stdout.read = AsyncMock(return_value=b"Success output")
    mock.stderr.read = AsyncMock(return_value=b"")
    mock.wait = AsyncMock(return_value=0)
    return mock


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# Test utilities
class AsyncContextManager:
    """Helper class for testing async context managers."""
    
    def __init__(self, return_value=None):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def create_mock_operation(
    command: str = "echo test",
    description: str = "Test operation", 
    op_type: OperationType = OperationType.SCRIPT_EXEC,
    **kwargs
) -> Operation:
    """Create a mock operation with default values."""
    defaults = {
        "timeout": 300,
        "retry_count": 0,
        "retry_delay": 10,
    }
    defaults.update(kwargs)
    
    return Operation(
        command=command,
        description=description,
        type=op_type,
        **defaults
    )


def create_mock_phase(
    name: str = "test_phase",
    groups: list = None,
    depends_on: list = None,
    **kwargs
) -> Phase:
    """Create a mock phase with default values."""
    if groups is None:
        groups = ["test_group"]
    if depends_on is None:
        depends_on = []
        
    defaults = {
        "description": f"Test phase: {name}",
        "enabled": True,
        "continue_on_error": False,
        "parallel_groups": False,
    }
    defaults.update(kwargs)
    
    return Phase(
        name=name,
        groups=groups,
        depends_on=depends_on,
        **defaults
    )