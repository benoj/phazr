"""
Rich display utilities for better UI experience.
"""

import time
from typing import Any, Dict, List

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from .models import ExecutionResult, Operation, Phase, PhaseResult


class DisplayManager:
    """Manages rich console output and UI elements."""

    def __init__(self, verbose: bool = False):
        self.console = Console()
        self.verbose = verbose
        self._current_phase = None
        self._start_time = None

    def print_header(self):
        """Print application header."""
        # ASCII art logo
        logo = """
[bold cyan]╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║  ██████╗ ██╗  ██╗ █████╗ ███████╗██████╗                            ║
║  ██╔══██╗██║  ██║██╔══██╗╚══███╔╝██╔══██╗                           ║
║  ██████╔╝███████║███████║  ███╔╝ ██████╔╝                           ║
║  ██╔═══╝ ██╔══██║██╔══██║ ███╔╝  ██╔══██╗                           ║
║  ██║     ██║  ██║██║  ██║███████╗██║  ██║                           ║
║  ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝                           ║
║                                                                       ║
║           [dim]Modern DAG-based workflow orchestration[/dim]                     ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝[/bold cyan]
        """
        self.console.print(logo)
        self.console.print()

    def print_config_info(self, config: Dict[str, Any]):
        """Display configuration information."""
        table = Table(title="Configuration", box=box.ROUNDED)
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="yellow")

        table.add_row(
            "Environment", config.get("environment", {}).get("name", "unknown")
        )
        table.add_row(
            "Namespace", config.get("environment", {}).get("namespace", "default")
        )

        if config.get("environment", {}).get("context"):
            table.add_row("Context", config["environment"]["context"])

        table.add_row(
            "Dry Run", "Yes" if config.get("execution", {}).get("dry_run") else "No"
        )
        table.add_row(
            "Parallel", "Yes" if config.get("execution", {}).get("parallel") else "No"
        )

        self.console.print(table)
        self.console.print()

    def start_phase(self, phase: Phase, total_operations: int):
        """Display phase start."""
        self._current_phase = phase.name
        self._start_time = time.time()

        # Use custom icon if provided, otherwise use defaults
        default_icons = {
            "prerequisites": "🔍",
            "environment": "🏗️",
            "environment_setup": "🏗️",
            "data": "💾",
            "data_setup": "💾",
            "database": "🗄️",
            "migrations": "🔄",
            "services": "🚀",
            "validation": "✅",
            "test": "🧪",
            "cleanup": "🧹",
            "deploy": "📦",
            "build": "🔨",
            "install": "📥",
            "configure": "⚙️",
        }

        # Use phase icon if specified, otherwise try to match by name
        if phase.icon:
            icon = phase.icon
        else:
            # Try to find icon based on phase name keywords
            icon = "▶️"  # Default
            for keyword, emoji in default_icons.items():
                if keyword in phase.name.lower():
                    icon = emoji
                    break

        # Build title with icon and phase name
        title = f"{icon} Phase: {phase.name.upper()}"
        if phase.description:
            subtitle = f"{phase.description} ({total_operations} operations)"
        else:
            subtitle = f"{total_operations} operations"

        # Start of phase container - print opening with title
        self.console.print()
        self.console.print(f"╔{'═' * 70}╗")
        self.console.print(f"║ [bold green]{title:<68}[/bold green] ║")
        self.console.print(f"║ [dim]{subtitle:<68}[/dim] ║")
        self.console.print(f"╠{'═' * 70}╣")

    def show_operation_progress(
        self, operation: Operation, index: int, total: int
    ) -> Any:
        """Create a progress context for an operation."""
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=self.console,
            transient=True,
        )

    def show_operation_start(self, operation: Operation, index: int, total: int):
        """Display operation start."""
        op_type_icons = {
            "script_exec": "📜",
            "kubectl_exec": "☸️",
            "kubectl_restart": "🔄",
            "kubectl_apply": "📦",
            "kubectl_delete": "🗑️",
            "http_request": "🌐",
            "custom": "⚙️",
            "skip": "⏭️",
        }

        icon = op_type_icons.get(operation.type.value, "▶️")

        # Build the operation line - icon takes 2 spaces in terminal
        prefix = f"[{index:2}/{total:2}]"
        op_desc = operation.description[:48]  # Limit description length

        # Format: "  [xx/yy] 📜 Description                                        ║"
        line = f"  [cyan]{prefix}[/cyan] {icon} [bold]{op_desc:<48}[/bold]"
        self.console.print(f"║{line} ║")

        if self.verbose and operation.command:
            # Split command into lines that fit in the box
            cmd_lines = operation.command[:200].split("\n")
            for line in cmd_lines[:3]:  # Max 3 lines
                if len(line) > 59:
                    line = line[:56] + "..."
                # Ensure proper alignment with 6 spaces indent
                self.console.print(f"║      [dim]{line:<59}[/dim]    ║")

    def show_operation_result(self, result: ExecutionResult, index: int, total: int):
        """Display operation result."""
        duration = f"({result.duration:.1f}s)"

        if result.operation.type.value == "skip":
            status_icon = "⏭️"
            status_text = "SKIPPED"
            status_color = "yellow"
        elif result.success:
            status_icon = "✅"
            status_text = "SUCCESS"
            status_color = "green"
        else:
            status_icon = "❌"
            status_text = "FAILED"
            status_color = "red"

        # Build the result line with proper padding
        # Format: "      ✅ SUCCESS (x.xs)                                        ║"
        result_text = f"{status_icon} {status_text} {duration}"
        # Calculate actual padding needed (icon = 2 spaces in terminal)
        padding_needed = 60 - len(result_text) - 1  # -1 for emoji width adjustment
        padded_result = result_text + (" " * padding_needed)

        self.console.print(
            f"║      [{status_color}]{padded_result}[/{status_color}]  ║"
        )

        if result.error and not result.success:
            # Display error inside the box
            error_lines = str(result.error)[:200].split("\n")
            for line in error_lines[:2]:  # Max 2 lines of error
                if len(line) > 57:
                    line = line[:54] + "..."
                # 8 spaces indent + arrow + space + error text
                self.console.print(f"║        [red]→ {line:<57}[/red]    ║")

        if self.verbose and result.output:
            # Display output inside the box
            output_lines = result.output[:200].split("\n")
            for line in output_lines[:2]:  # Max 2 lines of output
                line = line.strip()
                if len(line) > 57:
                    line = line[:54] + "..."
                if line:
                    # 8 spaces indent + arrow + space + output text
                    self.console.print(f"║        [dim]→ {line:<57}[/dim]    ║")

    def show_phase_summary(self, phase_result: PhaseResult):
        """Display phase completion summary."""
        duration = (
            time.time() - self._start_time
            if self._start_time
            else phase_result.duration
        )

        # Determine overall status
        if phase_result.failed_operations == 0:
            status_color = "green"
            status_icon = "✅"
        elif phase_result.failed_operations == phase_result.total_operations:
            status_color = "red"
            status_icon = "❌"
        else:
            status_color = "yellow"
            status_icon = "⚠️"

        # Close the phase box with summary
        self.console.print(f"╠{'═' * 70}╣")

        # Summary stats inside the box
        phase_name = phase_result.phase_name
        pass_fail_skip = f"{phase_result.successful_operations} passed, {phase_result.failed_operations} failed, {phase_result.skipped_operations} skipped"
        time_rate = f"{duration:.1f}s | {phase_result.success_rate:.0f}%"

        # Build centered stats line
        stats = f"{status_icon} {phase_name}: {pass_fail_skip} | {time_rate}"
        # Center it (icon takes 2 terminal spaces)
        padding = max(0, (68 - len(stats) + 1) // 2)
        stats_line = (" " * padding) + stats

        self.console.print(f"║ [{status_color}]{stats_line:<68}[/{status_color}] ║")
        self.console.print(f"╚{'═' * 70}╝")
        self.console.print()  # Add spacing between phases

    def show_validation_results(self, results: Dict[str, Any]):
        """Display validation results."""
        table = Table(
            title="🔍 Prerequisites Validation",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )

        table.add_column("Status", width=8)
        table.add_column("Component", style="cyan")
        table.add_column("Details", style="yellow")

        for result in results.get("results", []):
            if isinstance(result, dict):
                status = result.get("status", "unknown")

                if status == "passed":
                    status_icon = "✅"
                    row_style = "green"
                elif status == "failed":
                    status_icon = "❌"
                    row_style = "red"
                else:
                    status_icon = "⚠️"
                    row_style = "yellow"

                # Handle different result formats
                if "tool" in result:
                    component = result["tool"]
                    details = result.get("message", result.get("version", ""))
                elif "checks" in result:
                    component = "Kubernetes"
                    failed_checks = [
                        c for c in result["checks"] if not c.get("passed", True)
                    ]
                    if failed_checks:
                        details = failed_checks[0].get("message", "Check failed")
                    else:
                        details = "All checks passed"
                else:
                    component = "Unknown"
                    details = str(result)

                table.add_row(status_icon, component, details, style=row_style)

        self.console.print(table)

        # Overall status
        if results.get("all_passed"):
            self.console.print(
                Panel(
                    "[bold green]✅ All prerequisites validated successfully![/bold green]",
                    border_style="green",
                    box=box.DOUBLE,
                )
            )
        else:
            self.console.print(
                Panel(
                    "[bold red]❌ Prerequisites validation failed![/bold red]\n"
                    "[dim]Please fix the issues above before proceeding.[/dim]",
                    border_style="red",
                    box=box.DOUBLE,
                )
            )

    def show_final_summary(self, results: List[PhaseResult]):
        """Display final execution summary."""
        total_success = sum(r.successful_operations for r in results)
        total_failed = sum(r.failed_operations for r in results)
        total_skipped = sum(r.skipped_operations for r in results)
        total_ops = sum(r.total_operations for r in results)
        total_duration = sum(r.duration for r in results)

        # Create custom summary display
        self.console.print()
        self.console.print(
            "╔══════════════════════════════════════════════════════════════════════╗"
        )
        self.console.print(
            "║                        📊 EXECUTION SUMMARY                          ║"
        )
        self.console.print(
            "╠══════════════════════════════════════════════════════════════════════╣"
        )

        for result in results:
            if result.failed_operations == 0:
                status = "✅"
                color = "green"
            elif result.successful_operations == 0:
                status = "❌"
                color = "red"
            else:
                status = "⚠️"
                color = "yellow"

            phase_info = f"{status} {result.phase_name}"
            stats_info = f"✓ {result.successful_operations} ✗ {result.failed_operations} → {result.skipped_operations} | {result.duration:.1f}s"
            # Calculate padding to right-align stats
            total_width = 68
            phase_len = len(phase_info) + 2  # +2 for emoji width
            stats_len = len(stats_info)
            padding = total_width - phase_len - stats_len
            if padding < 2:
                padding = 2

            line = f" {phase_info}{' ' * padding}{stats_info} "
            self.console.print(f"║[{color}]{line:<70}[/{color}]║")

        # Separator
        self.console.print(
            "╠══════════════════════════════════════════════════════════════════════╣"
        )

        # Totals
        total_color = "green" if total_failed == 0 else "red"
        total_info = f"{'✅' if total_failed == 0 else '❌'} TOTAL"
        total_stats = f"✓ {total_success} ✗ {total_failed} → {total_skipped} | {total_duration:.1f}s"
        # Calculate padding
        total_len = len(total_info) + 2
        stats_len = len(total_stats)
        padding = 68 - total_len - stats_len
        if padding < 2:
            padding = 2

        total_line = f" {total_info}{' ' * padding}{total_stats} "
        self.console.print(
            f"║[bold {total_color}]{total_line:<70}[/bold {total_color}]║"
        )
        self.console.print(
            "╚══════════════════════════════════════════════════════════════════════╝"
        )

        # Final status
        if total_failed == 0:
            self.console.print(
                Panel(
                    f"[bold green]🎉 Setup completed successfully![/bold green]\n"
                    f"[dim]Executed {total_ops} operations in {total_duration:.1f} seconds[/dim]",
                    border_style="green",
                    box=box.DOUBLE,
                )
            )
        else:
            self.console.print(
                Panel(
                    f"[bold red]❌ Setup completed with {total_failed} failures[/bold red]\n"
                    f"[dim]Please review the errors above[/dim]",
                    border_style="red",
                    box=box.DOUBLE,
                )
            )

    def error(self, message: str):
        """Display an error message."""
        self.console.print(f"[bold red]❌ Error:[/bold red] {message}")

    def warning(self, message: str):
        """Display a warning message."""
        self.console.print(f"[bold yellow]⚠️ Warning:[/bold yellow] {message}")

    def info(self, message: str):
        """Display an info message."""
        self.console.print(f"[bold blue]ℹ️ Info:[/bold blue] {message}")

    def success(self, message: str):
        """Display a success message."""
        self.console.print(f"[bold green]✅ Success:[/bold green] {message}")
