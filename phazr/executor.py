"""
Core orchestration executor.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, cast

from .display import DisplayManager
from .handlers import HandlerRegistry
from .models import (
    ExecutionResult,
    Operation,
    OperationType,
    OrchestratorConfig,
    Phase,
    PhaseResult,
)
from .validators import PrerequisiteValidator


class Orchestrator:
    """Main orchestrator for executing operations."""

    def __init__(
        self,
        config: OrchestratorConfig,
        handler_registry: Optional[HandlerRegistry] = None,
        validator: Optional[PrerequisiteValidator] = None,
        display: Optional[DisplayManager] = None,
        logger=None,
    ):
        self.config = config
        self.handler_registry = handler_registry or HandlerRegistry()
        self.validator = validator or PrerequisiteValidator()
        self.display = display or DisplayManager(verbose=config.execution.verbose)
        self.logger = logger or self._create_default_logger()

        # Register default handlers
        self._register_default_handlers()

    def _create_default_logger(self):
        """Create a simple default logger."""
        import logging

        logging.basicConfig(level=self.config.execution.log_level)
        return logging.getLogger(__name__)

    def _register_default_handlers(self):
        """Register built-in operation handlers."""
        from .handlers import KubectlExecHandler, KubectlRestartHandler, ScriptHandler

        self.handler_registry.register(OperationType.SCRIPT_EXEC, ScriptHandler())
        self.handler_registry.register(OperationType.KUBECTL_EXEC, KubectlExecHandler())
        self.handler_registry.register(
            OperationType.KUBECTL_RESTART, KubectlRestartHandler()
        )

    async def validate_prerequisites(self) -> Dict[str, Any]:
        """Validate environment prerequisites."""
        self.display.info("Validating environment prerequisites...")

        results = await self.validator.validate(
            environment=self.config.environment,
            required_tools=self._get_required_tools(),
        )

        self.display.show_validation_results(results)
        return results

    def _get_required_tools(self) -> List[str]:
        """Determine required tools based on operation types."""
        tools = set()

        for version_config in self.config.versions.values():
            for operations in version_config.groups.values():
                for operation in operations:
                    if operation.type in [
                        OperationType.KUBECTL_EXEC,
                        OperationType.KUBECTL_RESTART,
                        OperationType.KUBECTL_APPLY,
                        OperationType.KUBECTL_DELETE,
                    ]:
                        tools.add("kubectl")

                    # Add other tool requirements based on operation types

        return list(tools)

    async def run_full_setup(self, version: Optional[str] = None) -> List[PhaseResult]:
        """Run all phases for a complete setup."""
        version = version or list(self.config.versions.keys())[0]

        self.display.print_header()
        self.display.info(f"Starting full setup for version {version}")

        all_results = []
        completed_phases = set()

        # Run through all configured phases
        for phase in self.config.phases:
            if not phase.enabled:
                self.display.info(f"Skipping disabled phase: {phase.name}")
                continue

            # Check dependencies
            if phase.depends_on:
                missing_deps = [
                    dep for dep in phase.depends_on if dep not in completed_phases
                ]
                if missing_deps:
                    self.display.warning(
                        f"Skipping phase {phase.name} - missing dependencies: {missing_deps}"
                    )
                    continue

            phase_result = await self.run_phase(phase, version)
            all_results.append(phase_result)
            completed_phases.add(phase.name)

            # Check if we should continue
            if (
                not phase_result.is_successful
                and not phase.continue_on_error
                and not self.config.execution.continue_on_error
            ):
                self.display.error(f"Phase {phase.name} failed, stopping execution")
                break

        # Show final summary
        self.display.show_final_summary(all_results)

        return all_results

    async def run_phase(
        self, phase: Phase, version: Optional[str] = None
    ) -> PhaseResult:
        """Run a single phase."""
        version = version or list(self.config.versions.keys())[0]
        version_config = self.config.versions.get(version)

        if not version_config:
            raise ValueError(f"Version {version} not found in configuration")

        # Get operation groups for this phase
        phase_groups = phase.groups

        if not phase_groups:
            self.display.warning(f"No operations configured for phase: {phase.name}")
            return PhaseResult(
                phase_name=phase.name,
                phase_config=phase,
                version=version,
                results=[],
                total_operations=0,
                successful_operations=0,
                failed_operations=0,
                skipped_operations=0,
                duration=0.0,
            )

        # Count total operations for this phase
        total_ops = sum(
            len(version_config.groups.get(group, [])) for group in phase_groups
        )

        # Display phase start
        self.display.start_phase(phase, total_ops)

        # Execute operations
        all_results = []
        start_time = time.time()
        operation_index = 0

        for group_name in phase_groups:
            operations = version_config.groups.get(group_name, [])

            if not operations:
                self.display.warning(
                    f"Group '{group_name}' not found in version config"
                )
                continue

            # Determine if we should run in parallel
            should_parallel = phase.parallel_groups or (
                self.config.execution.parallel
                and self._is_group_parallelizable(operations)
            )

            if should_parallel:
                results = await self._execute_parallel(
                    operations, operation_index, total_ops
                )
            else:
                results = await self._execute_sequential(
                    operations, operation_index, total_ops
                )

            all_results.extend(results)
            operation_index += len(operations)

            # Check if we should continue
            failed = [r for r in results if not r.success]
            if (
                failed
                and not phase.continue_on_error
                and not self.config.execution.continue_on_error
            ):
                self.display.error(f"Group {group_name} had failures, stopping phase")
                break

        # Create phase result
        phase_result = PhaseResult(
            phase_name=phase.name,
            phase_config=phase,
            version=version,
            results=all_results,
            total_operations=len(all_results),
            successful_operations=sum(1 for r in all_results if r.success),
            failed_operations=sum(
                1
                for r in all_results
                if not r.success and r.operation.type != OperationType.SKIP
            ),
            skipped_operations=sum(
                1 for r in all_results if r.operation.type == OperationType.SKIP
            ),
            duration=time.time() - start_time,
        )

        # Show phase summary
        self.display.show_phase_summary(phase_result)

        return phase_result

    async def run_phase_by_name(
        self, phase_name: str, version: Optional[str] = None
    ) -> PhaseResult:
        """Run a phase by its name."""
        # Find the phase configuration
        phase = None
        for p in self.config.phases:
            if p.name == phase_name:
                phase = p
                break

        if not phase:
            raise ValueError(f"Phase '{phase_name}' not found in configuration")

        return await self.run_phase(phase, version)

    def _is_group_parallelizable(self, operations: List[Operation]) -> bool:
        """Check if a group of operations can be run in parallel."""
        # Simple heuristic - could be made more sophisticated
        # Don't parallelize if operations depend on each other
        for op in operations:
            if op.type in [OperationType.KUBECTL_RESTART, OperationType.KUBECTL_DELETE]:
                return False  # These might have dependencies
        return True

    async def _execute_sequential(
        self,
        operations: List[Operation],
        start_index: int = 0,
        total: Optional[int] = None,
    ) -> List[ExecutionResult]:
        """Execute operations sequentially."""
        results = []
        total = total or len(operations)

        for i, operation in enumerate(operations, 1):
            current_index = start_index + i

            # Show operation start
            self.display.show_operation_start(operation, current_index, total)

            if self.config.execution.dry_run:
                result = self._create_dry_run_result(operation)
            else:
                result = await self._execute_operation(operation)

            results.append(result)

            # Show operation result
            self.display.show_operation_result(result, current_index, total)

            # Check if we should continue
            if not result.success and operation.fail_on_error:
                break

        return results

    async def _execute_parallel(
        self,
        operations: List[Operation],
        start_index: int = 0,
        total: Optional[int] = None,
    ) -> List[ExecutionResult]:
        """Execute operations in parallel."""
        total = total or len(operations)

        # Show all operations starting
        for i, operation in enumerate(operations, 1):
            current_index = start_index + i
            self.display.show_operation_start(operation, current_index, total)

        tasks = []
        for operation in operations:
            if self.config.execution.dry_run:

                async def dry_run_wrapper(op=operation):
                    return self._create_dry_run_result(op)

                task = asyncio.create_task(dry_run_wrapper())
            else:
                task = asyncio.create_task(self._execute_operation(operation))

            tasks.append((operation, task))

        # Execute with max parallelism limit
        results = []
        operation_tasks = list(tasks)

        for chunk in self._chunk_list(
            operation_tasks, self.config.execution.max_parallel
        ):
            chunk_tasks = [task for _, task in chunk]
            chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

            for (operation, _), result in zip(chunk, chunk_results):
                if isinstance(result, Exception):
                    # Create error result
                    error_result = ExecutionResult(
                        operation=operation,
                        success=False,
                        error=str(result),
                        duration=0.0,
                    )
                    results.append(error_result)
                    # Show result
                    idx = operations.index(operation) + start_index + 1
                    self.display.show_operation_result(error_result, idx, total)
                else:
                    # result should be ExecutionResult here since it's not an Exception
                    execution_result = cast(ExecutionResult, result)
                    results.append(execution_result)
                    # Show result
                    idx = operations.index(operation) + start_index + 1
                    self.display.show_operation_result(execution_result, idx, total)

        return results

    async def _execute_operation(self, operation: Operation) -> ExecutionResult:
        """Execute a single operation."""
        # Check skip condition
        if operation.skip_if and await self._evaluate_condition(operation.skip_if):
            return ExecutionResult(
                operation=operation,
                success=True,
                output="Operation skipped due to condition",
                duration=0.0,
                timestamp=str(int(time.time())),
            )

        # Get handler for operation type
        handler = self.handler_registry.get_handler(operation.type)
        if not handler:
            return ExecutionResult(
                operation=operation,
                success=False,
                error=f"No handler registered for operation type: {operation.type}",
                duration=0.0,
                timestamp=str(int(time.time())),
            )

        # Execute with retries
        retries = 0
        last_error = None
        start_time = time.time()

        while retries <= operation.retry_count:
            try:
                result = await handler.execute(operation, self.config.environment)

                # Run test command if specified
                if operation.test_command and result.success:
                    test_result = await self._run_test_command(operation.test_command)
                    if not test_result:
                        raise Exception("Test command failed")

                result.retries_used = retries
                result.duration = time.time() - start_time
                return result

            except Exception as e:
                last_error = str(e)
                retries += 1

                if retries <= operation.retry_count:
                    self.logger.warning(
                        f"Retry {retries}/{operation.retry_count} for {operation.description}"
                    )
                    await asyncio.sleep(operation.retry_delay)

        # All retries exhausted
        return ExecutionResult(
            operation=operation,
            success=False,
            error=last_error,
            duration=time.time() - start_time,
            timestamp=str(int(time.time())),
            retries_used=retries,
        )

    async def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a skip condition."""
        # This is a placeholder - implement condition evaluation logic
        # Could support shell commands, file existence checks, etc.
        return False

    async def _run_test_command(self, test_command: str) -> bool:
        """Run a test command to verify operation success."""
        # This is a placeholder - implement test command execution
        return True

    def _create_dry_run_result(self, operation: Operation) -> ExecutionResult:
        """Create a dry-run result."""
        return ExecutionResult(
            operation=operation,
            success=True,
            output=f"[DRY RUN] Would execute: {operation.description}",
            duration=0.0,
            timestamp=str(int(time.time())),
        )

    def _chunk_list(self, lst: List, chunk_size: int):
        """Split list into chunks."""
        for i in range(0, len(lst), chunk_size):
            yield lst[i : i + chunk_size]
