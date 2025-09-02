"""
Command-line interface for the orchestrator.
"""

import asyncio
import click
from pathlib import Path
from typing import Optional

from .config import ConfigManager
from .executor import Orchestrator
from .display import DisplayManager


@click.group()
@click.option("--config", "-c", default="orchestrator.yaml", help="Configuration file path")
@click.option("--dry-run", is_flag=True, help="Preview operations without executing")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx, config, dry_run, verbose):
    """Phazr - Modern DAG-based workflow orchestration."""
    ctx.ensure_object(dict)
    
    # Load configuration
    config_manager = ConfigManager()
    try:
        orchestrator_config = config_manager.load_config(config)
    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        ctx.exit(1)
    
    # Apply CLI overrides
    if dry_run:
        orchestrator_config.execution.dry_run = True
    if verbose:
        orchestrator_config.execution.verbose = True
    
    # Store in context
    ctx.obj["config"] = orchestrator_config
    ctx.obj["config_manager"] = config_manager


@cli.command()
@click.pass_context
def validate(ctx):
    """Validate configuration and prerequisites."""
    config = ctx.obj["config"]
    config_manager = ctx.obj["config_manager"]
    
    # Create display manager
    display = DisplayManager(verbose=config.execution.verbose)
    display.print_header()
    
    display.info("Validating configuration...")
    
    # Validate configuration
    issues = config_manager.validate_config(config)
    
    if issues:
        display.error("Configuration issues found:")
        for issue in issues:
            display.error(f"  - {issue}")
        ctx.exit(1)
    
    display.success("Configuration is valid")
    
    # Create orchestrator and validate prerequisites
    orchestrator = Orchestrator(config, display=display)
    
    # Run validation (display is handled inside)
    results = asyncio.run(orchestrator.validate_prerequisites())
    
    if not results.get("all_passed"):
        ctx.exit(1)


@cli.command()
@click.option("--version", "-V", help="Version to set up")
@click.pass_context
def setup(ctx, version):
    """Run full environment setup."""
    config = ctx.obj["config"]
    
    if not version:
        version = list(config.versions.keys())[0]
    
    # Create display manager
    display = DisplayManager(verbose=config.execution.verbose)
    
    # Create orchestrator with display
    orchestrator = Orchestrator(config, display=display)
    
    # Run setup
    results = asyncio.run(orchestrator.run_full_setup(version))
    
    # Exit code based on failures
    total_failures = sum(r.failed_operations for r in results)
    if total_failures > 0:
        ctx.exit(1)


@cli.command()
@click.argument("phase")
@click.option("--version", "-V", help="Version to use")
@click.pass_context
def run(ctx, phase, version):
    """Run a specific phase."""
    config = ctx.obj["config"]
    
    # Validate phase exists
    phase_names = [p.name for p in config.phases]
    if phase not in phase_names:
        click.echo(f"Error: Phase '{phase}' not found. Available phases: {', '.join(phase_names)}", err=True)
        ctx.exit(1)
    
    if not version:
        version = list(config.versions.keys())[0]
    
    # Create display manager
    display = DisplayManager(verbose=config.execution.verbose)
    display.print_header()
    display.info(f"Running phase {phase} for version {version}")
    
    # Create orchestrator with display
    orchestrator = Orchestrator(config, display=display)
    
    # Run phase (display is handled inside)
    result = asyncio.run(orchestrator.run_phase_by_name(phase, version))
    
    if not result.is_successful:
        ctx.exit(1)


@cli.command()
@click.argument("input_files", nargs=-1, required=True)
@click.option("--output", "-o", help="Output file path")
@click.pass_context
def merge(ctx, input_files, output):
    """Merge multiple configuration files."""
    config_manager = ctx.obj["config_manager"]
    
    click.echo(f"Merging {len(input_files)} configuration files...")
    
    try:
        merged_config = config_manager.merge_configs(*input_files)
        
        if output:
            config_manager.save_config(merged_config, output)
            click.echo(f"Merged configuration saved to {output}")
        else:
            # Print to stdout
            import yaml
            print(yaml.dump(merged_config.dict(), default_flow_style=False))
            
    except Exception as e:
        click.echo(f"Error merging configurations: {e}", err=True)
        ctx.exit(1)


@cli.command()
@click.pass_context
def list_phases(ctx):
    """List available phases and their operations."""
    config = ctx.obj["config"]
    
    display = DisplayManager()
    display.print_header()
    
    if not config.phases:
        display.warning("No phases configured")
        return
    
    from rich.table import Table
    from rich import box
    
    table = Table(title="Configured Phases", box=box.ROUNDED)
    table.add_column("Phase", style="cyan")
    table.add_column("Description", style="yellow")
    table.add_column("Groups", style="green")
    table.add_column("Dependencies", style="magenta")
    table.add_column("Options", style="blue")
    
    for phase in config.phases:
        options = []
        if phase.continue_on_error:
            options.append("continue-on-error")
        if phase.parallel_groups:
            options.append("parallel")
        if not phase.enabled:
            options.append("DISABLED")
        
        table.add_row(
            phase.name,
            phase.description or "-",
            ", ".join(phase.groups) if phase.groups else "-",
            ", ".join(phase.depends_on) if phase.depends_on else "-",
            ", ".join(options) if options else "-"
        )
    
    display.console.print(table)


@cli.command()
@click.pass_context
def list_versions(ctx):
    """List available versions."""
    config = ctx.obj["config"]
    
    click.echo("Available versions:")
    
    for version_key, version_config in config.versions.items():
        total_ops = sum(len(ops) for ops in version_config.groups.values())
        click.echo(f"  - {version_key}: {len(version_config.groups)} groups, {total_ops} operations")


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()