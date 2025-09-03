"""
Data models for the orchestration framework.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator


class OperationType(str, Enum):
    """Types of operations that can be executed."""

    SCRIPT_EXEC = "script_exec"  # Execute a shell script
    KUBECTL_EXEC = "kubectl_exec"  # Execute command in a pod
    KUBECTL_RESTART = "kubectl_restart"  # Restart a deployment/service
    KUBECTL_APPLY = "kubectl_apply"  # Apply manifests
    KUBECTL_DELETE = "kubectl_delete"  # Delete resources
    HTTP_REQUEST = "http_request"  # Make HTTP API calls
    CUSTOM = "custom"  # Custom operation type
    SKIP = "skip"  # Skip operation


class Phase(BaseModel):
    """Represents a configurable execution phase."""

    name: str = Field(description="Phase name/identifier")
    description: Optional[str] = Field(None, description="Phase description")
    icon: Optional[str] = Field(None, description="Icon/emoji for the phase")
    groups: List[str] = Field(
        default_factory=list, description="Operation groups in this phase"
    )
    depends_on: List[str] = Field(
        default_factory=list, description="Phases that must complete before this"
    )
    continue_on_error: bool = Field(
        False, description="Continue to next phase even if this fails"
    )
    parallel_groups: bool = Field(False, description="Execute groups in parallel")
    enabled: bool = Field(True, description="Whether this phase is enabled")


class Operation(BaseModel):
    """Represents a single executable operation."""

    command: str = Field(description="Command or script to execute")
    description: str = Field(description="Human-readable description")
    type: OperationType = Field(description="Type of operation")

    # Optional fields for specific operation types
    service: Optional[str] = Field(
        None, description="Service/deployment name for kubectl operations"
    )
    namespace: Optional[str] = Field(None, description="Kubernetes namespace override")
    container: Optional[str] = Field(
        None, description="Container name for kubectl exec"
    )
    wait_for_ready: bool = Field(False, description="Wait for resource to be ready")
    timeout: int = Field(300, description="Operation timeout in seconds")

    # Test and validation
    test_command: Optional[str] = Field(
        None, description="Command to test if operation succeeded"
    )
    expected_output: Optional[str] = Field(None, description="Expected output pattern")
    retry_count: int = Field(0, description="Number of retries on failure")
    retry_delay: int = Field(5, description="Delay between retries in seconds")

    # Conditions
    skip_if: Optional[str] = Field(None, description="Condition to skip this operation")
    fail_on_error: bool = Field(True, description="Whether to fail the phase on error")

    # Additional metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional operation metadata"
    )


class ExecutionResult(BaseModel):
    """Result of executing an operation."""

    operation: Operation
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
    timestamp: Optional[str] = None
    retries_used: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PhaseResult(BaseModel):
    """Aggregated results for a phase of operations."""

    phase_name: str
    phase_config: Optional[Phase] = None
    version: str
    results: List[ExecutionResult]
    total_operations: int
    successful_operations: int
    failed_operations: int
    skipped_operations: int
    duration: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_operations == 0:
            return 100.0
        return (self.successful_operations / self.total_operations) * 100.0

    @property
    def is_successful(self) -> bool:
        """Check if phase completed successfully."""
        return self.failed_operations == 0


class VersionConfig(BaseModel):
    """Configuration for a specific version."""

    version: str
    groups: Dict[str, List[Operation]]
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @validator("groups")
    def validate_groups(cls, v):
        """Ensure groups are not empty."""
        for group_name, operations in v.items():
            if not operations:
                raise ValueError(f"Group '{group_name}' cannot be empty")
        return v


class EnvironmentConfig(BaseModel):
    """Environment configuration."""

    name: str = Field(description="Environment name")
    namespace: str = Field(description="Default Kubernetes namespace")
    context: Optional[str] = Field(None, description="Kubernetes context")
    cluster: Optional[str] = Field(None, description="Cluster identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionConfig(BaseModel):
    """Execution behavior configuration."""

    dry_run: bool = Field(False, description="Preview operations without executing")
    interactive: bool = Field(True, description="Enable interactive prompts")
    parallel: bool = Field(
        False, description="Execute operations in parallel where safe"
    )
    max_parallel: int = Field(5, description="Maximum parallel operations")
    continue_on_error: bool = Field(False, description="Continue execution on errors")
    verbose: bool = Field(False, description="Enable verbose output")
    log_level: str = Field("INFO", description="Logging level")


class OrchestratorConfig(BaseModel):
    """Main orchestrator configuration."""

    versions: Dict[str, VersionConfig]
    phases: List[Phase] = Field(
        default_factory=list, description="Ordered list of phases to execute"
    )
    environment: EnvironmentConfig
    execution: ExecutionConfig = Field(
        default_factory=lambda: ExecutionConfig(
            dry_run=False,
            interactive=True, 
            parallel=False,
            max_parallel=5,
            continue_on_error=False,
            verbose=False,
            log_level="INFO"
        )
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def phase_mappings(self) -> Dict[str, List[str]]:
        """Get phase to group mappings."""
        return {phase.name: phase.groups for phase in self.phases}
