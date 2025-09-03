"""
Test utility functions and helpers.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

from phazr.models import ExecutionResult, Operation, OperationType


class MockProcess:
    """Mock subprocess for testing."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = MockStream(stdout)
        self.stderr = MockStream(stderr)
        self._wait_called = False
        self.kill = AsyncMock()
        self.wait = AsyncMock(return_value=returncode)

    async def communicate(self, input=None):
        """Mock communicate method."""
        return await self.stdout.read(), await self.stderr.read()


class MockStream:
    """Mock stream for process stdout/stderr."""

    def __init__(self, data: bytes):
        self.data = data
        self._read_called = False

    async def read(self):
        """Mock read method."""
        self._read_called = True
        return self.data


def create_successful_result(
    operation: Operation, output: str = "Success"
) -> ExecutionResult:
    """Create a successful execution result."""
    return ExecutionResult(
        operation=operation,
        success=True,
        output=output,
        error_message=None,
        start_time=0.0,
        end_time=1.0,
        return_code=0,
    )


def create_failed_result(
    operation: Operation, error_message: str = "Test error", return_code: int = 1
) -> ExecutionResult:
    """Create a failed execution result."""
    return ExecutionResult(
        operation=operation,
        success=False,
        output="",
        error_message=error_message,
        start_time=0.0,
        end_time=1.0,
        return_code=return_code,
    )


async def wait_for_condition(condition, timeout: float = 1.0, interval: float = 0.01):
    """Wait for a condition to become true."""
    elapsed = 0.0
    while elapsed < timeout:
        if condition():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


def create_test_config_file(config_dir: Path, content: Dict[str, Any]) -> Path:
    """Create a test configuration file."""
    import yaml

    config_file = config_dir / "test.yaml"
    with open(config_file, "w") as f:
        yaml.dump(content, f)
    return config_file


def assert_operation_executed(mock_handler, operation: Operation):
    """Assert that an operation was executed through a mock handler."""
    mock_handler.execute.assert_called()
    call_args = mock_handler.execute.call_args
    assert call_args[0][0] == operation


def create_kubectl_operation(
    command: str = "get pods", service: str = "test-service", namespace: str = "default"
) -> Operation:
    """Create a kubectl operation for testing."""
    return Operation(
        command=command,
        description=f"Kubectl: {command}",
        type=OperationType.KUBECTL_EXEC,
        service=service,
        namespace=namespace,
        timeout=300,
    )


def create_http_operation(
    url: str = "http://example.com/api", method: str = "GET"
) -> Operation:
    """Create an HTTP operation for testing."""
    return Operation(
        command=json.dumps({"url": url, "method": method}),
        description=f"HTTP {method} {url}",
        type=OperationType.HTTP_REQUEST,
        timeout=30,
    )


class AsyncIterator:
    """Helper for testing async iteration."""

    def __init__(self, items: List[Any]):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item


def mock_async_subprocess_exec(
    return_value: MockProcess = None, side_effect: Exception = None
):
    """Create a mock for asyncio.create_subprocess_exec."""
    if return_value is None:
        return_value = MockProcess()

    mock = AsyncMock()
    if side_effect:
        mock.side_effect = side_effect
    else:
        mock.return_value = return_value

    return mock


def mock_async_subprocess_shell(
    return_value: MockProcess = None, side_effect: Exception = None
):
    """Create a mock for asyncio.create_subprocess_shell."""
    if return_value is None:
        return_value = MockProcess()

    mock = AsyncMock()
    if side_effect:
        mock.side_effect = side_effect
    else:
        mock.return_value = return_value

    return mock


class TestTimer:
    """Helper for testing time-based operations."""

    def __init__(self):
        self.start_time = 0.0
        self.current_time = 0.0

    def time(self) -> float:
        """Mock time function."""
        return self.current_time

    def advance(self, seconds: float):
        """Advance the mock time."""
        self.current_time += seconds

    def reset(self):
        """Reset the timer."""
        self.current_time = 0.0
        self.start_time = 0.0
