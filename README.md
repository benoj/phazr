# Phazr 🚀

A modern DAG-based orchestration framework for executing complex workflows with dependencies, parallel execution, and rich progress visualization.

## Features

- **Dynamic Phases**: Define custom phases with dependencies, creating a DAG (Directed Acyclic Graph)
- **Declarative Configuration**: Simple YAML-based workflow definitions
- **Parallel Execution**: Run independent operations concurrently
- **Rich UI**: Beautiful terminal output with progress tracking and status indicators
- **Extensible**: Plugin system for custom operation handlers
- **Retry Logic**: Automatic retries with configurable delays
- **Dry Run Mode**: Preview operations before execution
- **Multiple Operation Types**: Shell scripts, kubectl, HTTP requests, and more

## Installation

```bash
pip install phazr
```

Or install from source:

```bash
git clone https://github.com/yourorg/phazr.git
cd phazr
pip install -e .
```

## Quick Start

1. Create a configuration file (`workflow.yaml`):

```yaml
phases:
  - name: "build"
    description: "Build the application"
    groups: ["compile", "test"]
    
  - name: "deploy"
    description: "Deploy application"
    groups: ["deployment"]
    depends_on: ["build"]  # Creates dependency

versions:
  "1.0.0":
    compile:
      - command: "echo 'Building...'"
        description: "Build app"
        type: "script_exec"
    
    test:
      - command: "echo 'Testing...'"
        description: "Run tests"
        type: "script_exec"
    
    deployment:
      - command: "echo 'Deploying...'"
        description: "Deploy app"
        type: "script_exec"

environment:
  name: "production"
  namespace: "default"
```

2. Run phazr:

```bash
# Run all phases
phazr setup

# Run specific phase
phazr run build

# List available phases
phazr list-phases

# Dry run to preview
phazr --dry-run setup
```

## Dynamic Phases & DAG

Phazr uses a DAG (Directed Acyclic Graph) to manage phase dependencies:

```yaml
phases:
  - name: "setup"
    groups: ["init"]
    
  - name: "build-frontend"
    groups: ["frontend_build"]
    depends_on: ["setup"]
    
  - name: "build-backend"
    groups: ["backend_build"]
    depends_on: ["setup"]
    
  - name: "deploy"
    groups: ["deployment"]
    depends_on: ["build-frontend", "build-backend"]  # Multiple dependencies
```

This creates a diamond-shaped DAG where frontend and backend can build in parallel!

## Operation Types

### Script Execution
```yaml
- command: "./build.sh"
  description: "Run build script"
  type: "script_exec"
  timeout: 300
```

### Kubectl Operations
```yaml
- command: "python manage.py migrate"
  description: "Run migrations"
  type: "kubectl_exec"
  service: "web-app"
  container: "app"
```

### HTTP Requests
```yaml
- command: '{"url": "http://api/health", "method": "GET"}'
  description: "Health check"
  type: "http_request"
```

## Phase Configuration

Each phase supports:

- `name`: Phase identifier
- `description`: Human-readable description  
- `icon`: Custom emoji/icon
- `groups`: Operation groups to execute
- `depends_on`: List of phases that must complete first
- `parallel_groups`: Execute groups in parallel
- `continue_on_error`: Continue even if phase fails
- `enabled`: Enable/disable phase

## Advanced Features

### Parallel Execution
```yaml
phases:
  - name: "tests"
    groups: ["unit", "integration", "e2e"]
    parallel_groups: true  # Run all test groups in parallel
```

### Retry Logic
```yaml
- command: "curl http://service/ready"
  type: "script_exec"
  retry_count: 5
  retry_delay: 10
```

### Conditional Execution
```yaml
- command: "setup.sh"
  type: "script_exec"
  skip_if: "test -f /tmp/already-setup"
```

## Extending Phazr

### Custom Operation Handlers

```python
from phazr.handlers import OperationHandler
from phazr.models import Operation, ExecutionResult

class CustomHandler(OperationHandler):
    async def execute(self, operation: Operation, environment) -> ExecutionResult:
        # Your custom logic here
        return ExecutionResult(
            operation=operation,
            success=True,
            output="Custom operation completed"
        )

# Register the handler
from phazr import Orchestrator
orchestrator = Orchestrator(config)
orchestrator.handler_registry.register("custom_type", CustomHandler())
```

## CLI Commands

- `phazr validate` - Validate configuration
- `phazr setup` - Run all phases
- `phazr run PHASE` - Run specific phase
- `phazr list-phases` - Show available phases
- `phazr list-versions` - Show versions
- `phazr merge FILE1 FILE2` - Merge configs

## Why Phazr?

Phazr combines the best of:
- **Make**: Dependency-based execution
- **Ansible**: Declarative configuration
- **Apache Airflow**: DAG workflows
- **GitHub Actions**: Modern YAML syntax

Perfect for:
- CI/CD pipelines
- Development environment setup
- Database migrations
- Deployment orchestration
- Testing workflows
- Any multi-step process with dependencies

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black phazr/

# Type checking
mypy phazr/
```

## License

MIT License - see [LICENSE](LICENSE) file for details.