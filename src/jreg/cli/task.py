from jreg.services.task_manager import TaskManager
from jreg.services.router import Router
from jreg.adapters.base import MockAdapter
from jreg.models.schemas import ModelInfo, Capability, RoutingProfile
from jreg.core.database import SessionLocal
import asyncio

@app.command(name="task-run")
def task_run(objective: str):
    """Run a test task through the routing engine."""
    db = SessionLocal()
    
    # Setup mock models and router
    models = [
        ModelInfo(id="gpt-4", name="GPT-4", provider_id="openai", capabilities=[Capability.TEXT], priority=1),
        ModelInfo(id="claude-3", name="Claude 3", provider_id="anthropic", capabilities=[Capability.TEXT], priority=1),
    ]
    adapter = MockAdapter()
    router = Router(models, {"openai": adapter, "anthropic": adapter})
    
    manager = TaskManager(db, router)
    task = manager.create_task(objective)
    console.print(f"Created task [cyan]{task.id}[/cyan]")
    
    profile = RoutingProfile(name="default", preferred_capabilities=[Capability.TEXT])
    
    try:
        console.print("Running task...")
        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(manager.run_task(task.id, profile))
        console.print(f"[green]Task completed successfully![/green]")
        console.print(f"Response: {response['choices'][0]['message']['content']}")
    except Exception as e:
        console.print(f"[red]Task failed: {e}[/red]")
    finally:
        db.close()

@app.command(name="task-inspect")
def task_inspect(task_id: str):
    """Inspect task state, attempts, and checkpoints."""
    db = SessionLocal()
    from jreg.models.db import Task
    task = db.query(Task).filter(Task.id == task_id).first()
    
    if not task:
        console.print(f"[red]Task {task_id} not found[/red]")
        return
    
    console.print(f"[bold blue]Task {task.id}[/bold blue]")
    console.print(f"Objective: {task.objective}")
    console.print(f"Status: {task.status.value}")
    
    if task.attempts:
        table = Table(title="Model Attempts")
        table.add_column("Model", style="cyan")
        table.add_column("Status", style="magenta")
        table.add_column("Error Code", style="red")
        
        for attempt in task.attempts:
            table.add_row(attempt.model_id, attempt.status, attempt.error_code or "N/A")
        
        console.print(table)
    
    db.close()
