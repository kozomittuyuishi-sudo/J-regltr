import asyncio
import os
from typing import Dict, List

import typer
from rich.console import Console
from rich.table import Table

from jreg.adapters.base import MockAdapter, ProviderAdapter
from jreg.core.config import settings
from jreg.core.database import init_db
from jreg.models.schemas import Capability, ModelInfo, RoutingProfile
from jreg.services.router import Router

app = typer.Typer(help="Provider-neutral AI model routing and task continuity.")
providers_app = typer.Typer(help="Inspect mock provider adapters.")
models_app = typer.Typer(help="Inspect and simulate mock models.")
routing_app = typer.Typer(help="Inspect routing policy and candidates.")
console = Console()

PROVIDERS = {
    "openai": "OpenAI (Mock)",
    "anthropic": "Anthropic (Mock)",
}
MODELS = [
    ModelInfo(
        id="gpt-4", name="GPT-4 (Mock)", provider_id="openai",
        capabilities=[Capability.TEXT, Capability.TOOLS], priority=1,
    ),
    ModelInfo(
        id="gpt-3.5", name="GPT-3.5 (Mock)", provider_id="openai",
        capabilities=[Capability.TEXT], priority=2,
    ),
    ModelInfo(
        id="claude-3", name="Claude 3 (Mock)", provider_id="anthropic",
        capabilities=[Capability.TEXT, Capability.TOOLS], priority=3,
    ),
]
DEFAULT_PROFILE = RoutingProfile(
    name="default", preferred_capabilities=[Capability.TEXT], max_retries=1
)
SIMULATION_PROFILE = RoutingProfile(
    name="mock-failover-demo",
    preferred_capabilities=[Capability.TEXT, Capability.TOOLS],
    max_retries=1,
)


def _adapters(behaviors: Dict[str, str] | None = None) -> Dict[str, ProviderAdapter]:
    behavior_map = behaviors or {}
    return {
        provider_id: MockAdapter(behavior_map)
        for provider_id in PROVIDERS
    }


@app.command()
def init() -> None:
    """Initialize local configuration and SQLite tables."""
    os.makedirs(settings.config_dir, exist_ok=True)
    console.print(f"[green]Configuration directory ready:[/green] {settings.config_dir}")
    init_db()
    console.print("[green]Database initialized.[/green]")


@app.command()
def status() -> None:
    """Display configuration and database file status."""
    console.print(f"[bold blue]{settings.app_name} Status[/bold blue]")
    console.print(f"Config Dir: {settings.config_dir}")
    console.print(f"Database: {settings.database_url}")
    if settings.database_url.startswith("sqlite:///"):
        db_path = settings.database_url.removeprefix("sqlite:///")
        if db_path.startswith("./"):
            db_path = os.path.join(os.getcwd(), db_path[2:])
        exists = os.path.exists(db_path)
        label = "Available" if exists else "Not initialized (run jreg init)"
        color = "green" if exists else "yellow"
        console.print(f"Database Status: [{color}]{label}[/{color}]")
    else:
        console.print("Database Status: [yellow]Configured; connection not probed[/yellow]")


@providers_app.command("list")
def providers_list() -> None:
    """List the built-in mock providers."""
    table = Table(title="Mock Providers")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="magenta")
    table.add_column("Adapter")
    for provider_id, name in PROVIDERS.items():
        table.add_row(provider_id, name, "mock")
    console.print(table)


@models_app.command("list")
def models_list() -> None:
    """List built-in mock models and routing metadata."""
    table = Table(title="Available Mock Models")
    table.add_column("ID", style="cyan")
    table.add_column("Provider", style="magenta")
    table.add_column("Capabilities", style="yellow")
    table.add_column("Priority", style="blue")
    table.add_column("Status", style="green")
    for model in sorted(MODELS, key=lambda item: item.priority):
        table.add_row(
            model.id,
            model.provider_id,
            ", ".join(capability.value for capability in model.capabilities),
            str(model.priority),
            model.status.value,
        )
    console.print(table)


@models_app.command("simulate")
def models_simulate(
    failure: str = typer.Option(
        "success",
        "--failure",
        help="Primary model behavior: success, quota_exhausted, rate_limit, timeout, error.",
    ),
) -> None:
    """Run a deterministic request against mock models."""
    allowed = {"success", "quota_exhausted", "rate_limit", "timeout", "error"}
    if failure not in allowed:
        raise typer.BadParameter(f"Choose one of: {', '.join(sorted(allowed))}")
    router = Router(MODELS, _adapters({"gpt-4": failure}))
    try:
        response, attempts = asyncio.run(
            router.route_with_attempts(
                SIMULATION_PROFILE,
                [{"role": "user", "content": "Demonstrate mock routing."}],
            )
        )
    except Exception as error:
        attempts = getattr(error, "attempts", [])
        console.print(f"[red]Routing failed:[/red] {getattr(error, 'code', 'UNKNOWN')}: {error}")
        _show_attempts(attempts)
        raise typer.Exit(code=1)
    _show_attempts(attempts)
    console.print(f"[green]Selected model:[/green] {response['model']}")
    console.print(response["choices"][0]["message"]["content"])


@routing_app.command("show")
def routing_show() -> None:
    """Show the default profile and its deterministic candidate order."""
    router = Router(MODELS, _adapters())
    console.print(
        f"Profile: {DEFAULT_PROFILE.name}; required capabilities: "
        f"{', '.join(cap.value for cap in DEFAULT_PROFILE.preferred_capabilities)}; "
        f"max retries per model: {DEFAULT_PROFILE.max_retries}; "
        f"fallback: {'enabled' if DEFAULT_PROFILE.fallback_enabled else 'disabled'}"
    )
    for index, model in enumerate(router.get_candidates(DEFAULT_PROFILE), start=1):
        console.print(f"{index}. {model.id} ({model.provider_id}, priority {model.priority})")


def _show_attempts(attempts: List[object]) -> None:
    table = Table(title="Routing Attempts")
    table.add_column("Model")
    table.add_column("Attempt")
    table.add_column("Outcome")
    table.add_column("Error")
    for attempt in attempts:
        table.add_row(
            attempt.model_id,
            str(attempt.attempt_number),
            attempt.status,
            attempt.error_code or "—",
        )
    console.print(table)


app.add_typer(providers_app, name="providers")
app.add_typer(models_app, name="models")
app.add_typer(routing_app, name="routing")

# Preserve the original flat spellings for existing scripts.
app.command(name="providers-list")(providers_list)
app.command(name="models-list")(models_list)


if __name__ == "__main__":
    app()
