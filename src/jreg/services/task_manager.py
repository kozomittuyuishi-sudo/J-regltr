import uuid
from sqlalchemy.orm import Session
from jreg.models.db import Task, TaskStatus, ModelAttempt
from jreg.models.schemas import RoutingProfile
from jreg.services.router import Router

class TaskManager:
    def __init__(self, db: Session, router: Router):
        self.db = db
        self.router = router

    def create_task(self, objective: str) -> Task:
        task = Task(
            id=str(uuid.uuid4()),
            objective=objective,
            status=TaskStatus.PENDING,
            context={"messages": [{"role": "user", "content": objective}]}
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    async def run_task(self, task_id: str, profile: RoutingProfile):
        task = self.db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = TaskStatus.RUNNING
        self.db.commit()

        try:
            # Simple one-step execution for now
            response, routing_attempts = await self.router.route_with_attempts(
                profile, task.context["messages"]
            )
        except Exception as e:
            # The router attaches every observed outcome to the terminal error.
            for routing_attempt in getattr(e, "attempts", []):
                self.db.add(
                    ModelAttempt(
                        task_id=task.id,
                        model_id=routing_attempt.model_id,
                        provider_id=routing_attempt.provider_id,
                        status=routing_attempt.status,
                        error_code=routing_attempt.error_code,
                    )
                )
            task.status = TaskStatus.FAILED
            self.db.commit()
            raise

        for routing_attempt in routing_attempts:
            self.db.add(
                ModelAttempt(
                    task_id=task.id,
                    model_id=routing_attempt.model_id,
                    provider_id=routing_attempt.provider_id,
                    status=routing_attempt.status,
                    error_code=routing_attempt.error_code,
                    response=(response if routing_attempt.status == "success" else None),
                )
            )

        # Update task
        task.status = TaskStatus.COMPLETED
        task.context["messages"].append(response["choices"][0]["message"])
        self.db.commit()

        return response
