"""
Operation handlers for different operation types.
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Dict, Optional

from .models import EnvironmentConfig, ExecutionResult, Operation, OperationType


class OperationHandler(ABC):
    """Base class for operation handlers."""

    @abstractmethod
    async def execute(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> ExecutionResult:
        """Execute the operation and return result."""
        pass


class ScriptHandler(OperationHandler):
    """Handler for executing shell scripts."""

    async def execute(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> ExecutionResult:
        """Execute a shell script."""
        try:
            # Prepare environment variables
            env = self._prepare_environment(operation, environment)

            # Execute command
            process = await asyncio.create_subprocess_shell(
                operation.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Wait for completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=operation.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception(f"Command timed out after {operation.timeout} seconds")

            # Create result
            success = process.returncode == 0
            output = stdout.decode() if stdout else ""
            error = stderr.decode() if stderr and not success else None

            return ExecutionResult(
                operation=operation, success=success, output=output, error=error
            )

        except Exception as e:
            return ExecutionResult(operation=operation, success=False, error=str(e))

    def _prepare_environment(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> Dict[str, str]:
        """Prepare environment variables for script execution."""
        import os

        env = os.environ.copy()

        # Add environment-specific variables
        env["NAMESPACE"] = operation.namespace or environment.namespace
        env["ENVIRONMENT"] = environment.name

        if environment.context:
            env["KUBE_CONTEXT"] = environment.context

        # Add any operation-specific metadata as env vars
        for key, value in operation.metadata.items():
            env[f"OP_{key.upper()}"] = str(value)

        return env


class KubectlExecHandler(OperationHandler):
    """Handler for executing commands inside Kubernetes pods."""

    async def execute(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> ExecutionResult:
        """Execute command in a Kubernetes pod."""
        try:
            if not operation.service:
                raise ValueError("Service name required for kubectl exec")

            namespace = operation.namespace or environment.namespace

            # Build kubectl command
            kubectl_cmd = ["kubectl"]

            if environment.context:
                kubectl_cmd.extend(["--context", environment.context])

            kubectl_cmd.extend(["exec", "-n", namespace, operation.service])

            if operation.container:
                kubectl_cmd.extend(["-c", operation.container])

            kubectl_cmd.extend(["--", "sh", "-c", operation.command])

            # Execute
            process = await asyncio.create_subprocess_exec(
                *kubectl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=operation.timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise Exception(f"Command timed out after {operation.timeout} seconds")

            # Create result
            success = process.returncode == 0
            output = stdout.decode() if stdout else ""
            error = stderr.decode() if stderr and not success else None

            return ExecutionResult(
                operation=operation, success=success, output=output, error=error
            )

        except Exception as e:
            return ExecutionResult(operation=operation, success=False, error=str(e))


class KubectlRestartHandler(OperationHandler):
    """Handler for restarting Kubernetes deployments."""

    async def execute(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> ExecutionResult:
        """Restart a Kubernetes deployment."""
        try:
            if not operation.service:
                raise ValueError("Service name required for kubectl restart")

            namespace = operation.namespace or environment.namespace

            # Build kubectl command
            kubectl_cmd = ["kubectl"]

            if environment.context:
                kubectl_cmd.extend(["--context", environment.context])

            kubectl_cmd.extend(
                ["rollout", "restart", "deployment", operation.service, "-n", namespace]
            )

            # Execute restart
            process = await asyncio.create_subprocess_exec(
                *kubectl_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error = stderr.decode() if stderr else "Restart failed"
                return ExecutionResult(operation=operation, success=False, error=error)

            # Wait for ready if requested
            if operation.wait_for_ready:
                await self._wait_for_ready(
                    operation.service, namespace, environment.context, operation.timeout
                )

            return ExecutionResult(
                operation=operation,
                success=True,
                output=stdout.decode() if stdout else "Restart successful",
            )

        except Exception as e:
            return ExecutionResult(operation=operation, success=False, error=str(e))

    async def _wait_for_ready(
        self, deployment: str, namespace: str, context: Optional[str], timeout: int
    ):
        """Wait for deployment to be ready."""
        kubectl_cmd = ["kubectl"]

        if context:
            kubectl_cmd.extend(["--context", context])

        kubectl_cmd.extend(
            [
                "rollout",
                "status",
                "deployment",
                deployment,
                "-n",
                namespace,
                f"--timeout={timeout}s",
            ]
        )

        process = await asyncio.create_subprocess_exec(
            *kubectl_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        await process.communicate()

        if process.returncode != 0:
            raise Exception(
                f"Deployment {deployment} did not become ready within {timeout} seconds"
            )


class KubectlApplyHandler(OperationHandler):
    """Handler for applying Kubernetes manifests."""

    async def execute(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> ExecutionResult:
        """Apply Kubernetes manifests."""
        try:
            # Build kubectl command
            kubectl_cmd = ["kubectl"]

            if environment.context:
                kubectl_cmd.extend(["--context", environment.context])

            namespace = operation.namespace or environment.namespace
            kubectl_cmd.extend(["apply", "-n", namespace])

            # Add manifest path or stdin
            if operation.command.startswith("{") or operation.command.startswith("---"):
                # JSON or YAML content
                kubectl_cmd.extend(["-f", "-"])
                stdin_data = operation.command.encode()
            else:
                # File path
                kubectl_cmd.extend(["-f", operation.command])
                stdin_data = None

            # Execute
            if stdin_data:
                process = await asyncio.create_subprocess_exec(
                    *kubectl_cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate(input=stdin_data)
            else:
                process = await asyncio.create_subprocess_exec(
                    *kubectl_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await process.communicate()

            success = process.returncode == 0
            output = stdout.decode() if stdout else ""
            error = stderr.decode() if stderr and not success else None

            return ExecutionResult(
                operation=operation, success=success, output=output, error=error
            )

        except Exception as e:
            return ExecutionResult(operation=operation, success=False, error=str(e))


class HttpRequestHandler(OperationHandler):
    """Handler for making HTTP requests."""

    async def execute(
        self, operation: Operation, environment: EnvironmentConfig
    ) -> ExecutionResult:
        """Make an HTTP request."""
        try:
            import aiohttp

            # Parse command as JSON for request details
            request_config = json.loads(operation.command)

            url = request_config.get("url")
            method = request_config.get("method", "GET")
            headers = request_config.get("headers", {})
            data = request_config.get("data")

            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=data if data else None,
                    timeout=aiohttp.ClientTimeout(total=operation.timeout),
                ) as response:

                    response_text = await response.text()
                    success = 200 <= response.status < 300

                    return ExecutionResult(
                        operation=operation,
                        success=success,
                        output=response_text,
                        error=None if success else f"HTTP {response.status}",
                        metadata={"status_code": response.status},
                    )

        except json.JSONDecodeError as e:
            return ExecutionResult(
                operation=operation,
                success=False,
                error=f"Invalid JSON in command: {e}",
            )
        except Exception as e:
            return ExecutionResult(operation=operation, success=False, error=str(e))


class HandlerRegistry:
    """Registry for operation handlers."""

    def __init__(self):
        self._handlers: Dict[OperationType, OperationHandler] = {}

    def register(self, operation_type: OperationType, handler: OperationHandler):
        """Register a handler for an operation type."""
        self._handlers[operation_type] = handler

    def get_handler(self, operation_type: OperationType) -> Optional[OperationHandler]:
        """Get handler for an operation type."""
        return self._handlers.get(operation_type)

    def unregister(self, operation_type: OperationType):
        """Remove a handler registration."""
        if operation_type in self._handlers:
            del self._handlers[operation_type]
