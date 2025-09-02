"""
Prerequisite validators for the orchestration framework.
"""

import subprocess
import asyncio
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

from .models import EnvironmentConfig


class Validator(ABC):
    """Base class for validators."""
    
    @abstractmethod
    async def validate(self) -> Dict[str, Any]:
        """Perform validation and return results."""
        pass


class ToolValidator(Validator):
    """Validate that required tools are installed."""
    
    def __init__(self, tool_name: str, version_command: Optional[str] = None):
        self.tool_name = tool_name
        self.version_command = version_command or f"{tool_name} --version"
    
    async def validate(self) -> Dict[str, Any]:
        """Check if tool is available."""
        try:
            process = await asyncio.create_subprocess_shell(
                self.version_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=5.0
            )
            
            if process.returncode == 0:
                version = stdout.decode().strip() or stderr.decode().strip()
                return {
                    "status": "passed",
                    "tool": self.tool_name,
                    "version": version,
                    "message": f"{self.tool_name} is available"
                }
            else:
                return {
                    "status": "failed",
                    "tool": self.tool_name,
                    "message": f"{self.tool_name} command failed"
                }
                
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "tool": self.tool_name,
                "message": f"{self.tool_name} command timed out"
            }
        except Exception as e:
            return {
                "status": "failed",
                "tool": self.tool_name,
                "message": f"{self.tool_name} not found: {e}"
            }


class KubernetesValidator(Validator):
    """Validate Kubernetes connectivity and permissions."""
    
    def __init__(self, namespace: str, context: Optional[str] = None):
        self.namespace = namespace
        self.context = context
    
    async def validate(self) -> Dict[str, Any]:
        """Check Kubernetes access."""
        results = {
            "status": "passed",
            "checks": []
        }
        
        # Check cluster connectivity
        kubectl_cmd = ["kubectl"]
        if self.context:
            kubectl_cmd.extend(["--context", self.context])
        
        # Test cluster info
        try:
            process = await asyncio.create_subprocess_exec(
                *kubectl_cmd, "cluster-info",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
            
            if process.returncode == 0:
                results["checks"].append({
                    "name": "cluster_connectivity",
                    "passed": True,
                    "message": "Connected to cluster"
                })
            else:
                results["status"] = "failed"
                results["checks"].append({
                    "name": "cluster_connectivity",
                    "passed": False,
                    "message": f"Cannot connect to cluster: {stderr.decode()}"
                })
                return results
                
        except Exception as e:
            results["status"] = "failed"
            results["checks"].append({
                "name": "cluster_connectivity",
                "passed": False,
                "message": f"Cannot connect to cluster: {e}"
            })
            return results
        
        # Check namespace access
        try:
            process = await asyncio.create_subprocess_exec(
                *kubectl_cmd, "get", "namespace", self.namespace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10.0
            )
            
            if process.returncode == 0:
                results["checks"].append({
                    "name": "namespace_access",
                    "passed": True,
                    "message": f"Namespace {self.namespace} is accessible"
                })
            else:
                results["status"] = "warning"
                results["checks"].append({
                    "name": "namespace_access",
                    "passed": False,
                    "message": f"Cannot access namespace {self.namespace}"
                })
                
        except Exception as e:
            results["status"] = "warning"
            results["checks"].append({
                "name": "namespace_access",
                "passed": False,
                "message": f"Error checking namespace: {e}"
            })
        
        # Check pod list permissions
        try:
            process = await asyncio.create_subprocess_exec(
                *kubectl_cmd, "auth", "can-i", "list", "pods",
                "-n", self.namespace,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode == 0:
                results["checks"].append({
                    "name": "pod_permissions",
                    "passed": True,
                    "message": "Can list pods"
                })
            else:
                results["status"] = "warning"
                results["checks"].append({
                    "name": "pod_permissions",
                    "passed": False,
                    "message": "Cannot list pods"
                })
                
        except Exception:
            pass  # Non-critical check
        
        return results


class FileSystemValidator(Validator):
    """Validate file system requirements."""
    
    def __init__(self, required_paths: List[str] = None):
        self.required_paths = required_paths or []
    
    async def validate(self) -> Dict[str, Any]:
        """Check file system requirements."""
        from pathlib import Path
        
        results = {
            "status": "passed",
            "paths": []
        }
        
        for path_str in self.required_paths:
            path = Path(path_str)
            
            if path.exists():
                results["paths"].append({
                    "path": path_str,
                    "exists": True,
                    "type": "directory" if path.is_dir() else "file"
                })
            else:
                results["status"] = "warning"
                results["paths"].append({
                    "path": path_str,
                    "exists": False,
                    "message": f"Path {path_str} does not exist"
                })
        
        return results


class NetworkValidator(Validator):
    """Validate network connectivity."""
    
    def __init__(self, endpoints: List[str] = None):
        self.endpoints = endpoints or []
    
    async def validate(self) -> Dict[str, Any]:
        """Check network endpoints."""
        results = {
            "status": "passed",
            "endpoints": []
        }
        
        for endpoint in self.endpoints:
            try:
                # Simple ping-like check using curl
                process = await asyncio.create_subprocess_exec(
                    "curl", "-I", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                    endpoint,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=5.0
                )
                
                if process.returncode == 0:
                    results["endpoints"].append({
                        "endpoint": endpoint,
                        "reachable": True,
                        "status_code": stdout.decode().strip()
                    })
                else:
                    results["status"] = "warning"
                    results["endpoints"].append({
                        "endpoint": endpoint,
                        "reachable": False,
                        "message": "Endpoint not reachable"
                    })
                    
            except Exception as e:
                results["status"] = "warning"
                results["endpoints"].append({
                    "endpoint": endpoint,
                    "reachable": False,
                    "message": str(e)
                })
        
        return results


class PrerequisiteValidator:
    """Main validator for checking all prerequisites."""
    
    def __init__(self):
        self.validators: List[Validator] = []
    
    def add_validator(self, validator: Validator):
        """Add a validator to the chain."""
        self.validators.append(validator)
    
    async def validate(
        self,
        environment: EnvironmentConfig,
        required_tools: List[str] = None
    ) -> Dict[str, Any]:
        """Run all validators and aggregate results."""
        
        # Add default validators
        validators = []
        
        # Tool validators
        if required_tools:
            for tool in required_tools:
                validators.append(ToolValidator(tool))
        
        # Only add Kubernetes validator if kubectl is in required tools
        if required_tools and "kubectl" in required_tools:
            validators.append(KubernetesValidator(
                namespace=environment.namespace,
                context=environment.context
            ))
        
        # Add any custom validators
        validators.extend(self.validators)
        
        # Run all validators
        all_results = []
        all_passed = True
        has_warnings = False
        
        for validator in validators:
            result = await validator.validate()
            all_results.append(result)
            
            if result.get("status") == "failed":
                all_passed = False
            elif result.get("status") == "warning":
                has_warnings = True
        
        return {
            "all_passed": all_passed,
            "has_warnings": has_warnings,
            "results": all_results,
            "summary": self._generate_summary(all_results)
        }
    
    def _generate_summary(self, results: List[Dict[str, Any]]) -> str:
        """Generate a summary message from validation results."""
        failed = [r for r in results if r.get("status") == "failed"]
        warnings = [r for r in results if r.get("status") == "warning"]
        
        if not failed and not warnings:
            return "All prerequisites validated successfully"
        elif failed:
            return f"{len(failed)} prerequisites failed validation"
        else:
            return f"Prerequisites passed with {len(warnings)} warnings"