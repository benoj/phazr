"""
Phazr - A modern DAG-based orchestration framework.

Phazr provides a flexible, phase-based execution framework for managing complex
workflows with dependencies, parallel execution, and rich progress visualization.
"""

__version__ = "1.0.0"
__author__ = "Your Team"

from .models import (
    OperationType,
    Phase,
    Operation,
    ExecutionResult,
    PhaseResult,
)
from .executor import Orchestrator
from .config import ConfigManager

__all__ = [
    "OperationType",
    "Phase", 
    "Operation",
    "ExecutionResult",
    "PhaseResult",
    "Orchestrator",
    "ConfigManager",
]