"""
Configuration management for the orchestrator.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .models import (
    EnvironmentConfig,
    ExecutionConfig,
    Operation,
    OrchestratorConfig,
    Phase,
    VersionConfig,
)


class ConfigManager:
    """Manage orchestrator configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path.cwd() / "config"
        self._config: Optional[OrchestratorConfig] = None
        self._raw_config: Dict[str, Any] = {}

    def load_config(self, config_file: str) -> OrchestratorConfig:
        """Load configuration from file."""
        config_path = Path(config_file)

        if not config_path.exists():
            # Try relative to config directory
            config_path = self.config_path / config_file

            if not config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_file}")

        # Load raw configuration
        if config_path.suffix in [".yaml", ".yml"]:
            with open(config_path, "r") as f:
                self._raw_config = yaml.safe_load(f)
        elif config_path.suffix == ".json":
            with open(config_path, "r") as f:
                self._raw_config = json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {config_path.suffix}")

        # Parse and validate
        self._config = self._parse_config(self._raw_config)
        return self._config

    def _parse_config(self, raw_config: Dict[str, Any]) -> OrchestratorConfig:
        """Parse raw configuration into model."""

        # Parse versions
        versions = {}
        for version_key, version_data in raw_config.get("versions", {}).items():
            groups = {}

            for group_name, operations_data in version_data.items():
                if group_name in ["metadata"]:
                    continue

                operations = []
                for op_data in operations_data:
                    operations.append(Operation(**op_data))

                groups[group_name] = operations

            versions[version_key] = VersionConfig(
                version=version_key,
                groups=groups,
                metadata=version_data.get("metadata", {}),
            )

        # Parse environment
        env_data = raw_config.get("environment", {})
        environment = EnvironmentConfig(**env_data)

        # Parse execution
        exec_data = raw_config.get("execution", {})
        execution = ExecutionConfig(**exec_data)

        # Parse phases
        phases = []
        phases_data = raw_config.get("phases", [])
        for phase_data in phases_data:
            phases.append(Phase(**phase_data))

        # Create main config
        return OrchestratorConfig(
            versions=versions,
            phases=phases,
            environment=environment,
            execution=execution,
            metadata=raw_config.get("metadata", {}),
        )

    def save_config(self, config: OrchestratorConfig, output_file: str):
        """Save configuration to file."""
        output_path = Path(output_file)

        # Convert to dict using modern Pydantic API with enum serialization
        config_dict = config.model_dump(mode="json")

        # Save based on extension
        if output_path.suffix in [".yaml", ".yml"]:
            with open(output_path, "w") as f:
                yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True)
        elif output_path.suffix == ".json":
            with open(output_path, "w") as f:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
        else:
            raise ValueError(f"Unsupported output format: {output_path.suffix}")

    def merge_configs(self, *config_files: str) -> OrchestratorConfig:
        """Merge multiple configuration files."""
        merged_raw: Dict[str, Any] = {}

        for config_file in config_files:
            config_path = Path(config_file)

            if config_path.suffix in [".yaml", ".yml"]:
                with open(config_path, "r") as f:
                    file_config = yaml.safe_load(f)
            elif config_path.suffix == ".json":
                with open(config_path, "r") as f:
                    file_config = json.load(f)
            else:
                continue

            # Deep merge
            merged_raw = self._deep_merge(merged_raw, file_config)

        return self._parse_config(merged_raw)

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def validate_config(self, config: OrchestratorConfig) -> List[str]:
        """Validate configuration and return any issues."""
        issues = []

        # Check for empty versions
        if not config.versions:
            issues.append("No versions defined in configuration")

        # Check each version
        for version_key, version_config in config.versions.items():
            if not version_config.groups:
                issues.append(f"Version {version_key} has no operation groups")

            # Check operations
            for group_name, operations in version_config.groups.items():
                for i, op in enumerate(operations):
                    # Check required fields based on operation type
                    if op.type == "kubectl_exec" and not op.service:
                        issues.append(
                            f"Operation {i} in {group_name} ({version_key}) "
                            f"is kubectl_exec but missing service"
                        )

                    if op.type == "kubectl_restart" and not op.service:
                        issues.append(
                            f"Operation {i} in {group_name} ({version_key}) "
                            f"is kubectl_restart but missing service"
                        )

        # Check environment
        if not config.environment.namespace:
            issues.append("No namespace specified in environment configuration")

        # Check phase mappings
        for phase, groups in config.phase_mappings.items():
            for group in groups:
                # Check if group exists in any version
                found = False
                for version_config in config.versions.values():
                    if group in version_config.groups:
                        found = True
                        break

                if not found:
                    issues.append(
                        f"Phase mapping '{phase}' references non-existent group '{group}'"
                    )

        return issues

    def get_phase_mappings(self) -> Dict[str, List[str]]:
        """Get phase to group mappings."""
        if self._config:
            return self._config.phase_mappings

        return {}

    def get_environment(self) -> Optional[EnvironmentConfig]:
        """Get environment configuration."""
        if self._config:
            return self._config.environment
        return None

    def get_execution_config(self) -> Optional[ExecutionConfig]:
        """Get execution configuration."""
        if self._config:
            return self._config.execution
        return None
