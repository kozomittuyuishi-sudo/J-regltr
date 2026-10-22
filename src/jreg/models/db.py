from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class TaskStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    objective = Column(String, nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    context = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    attempts = relationship("ModelAttempt", back_populates="task")
    tool_actions = relationship("ToolAction", back_populates="task")

class ModelAttempt(Base):
    __tablename__ = "model_attempts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.id"))
    model_id = Column(String)
    provider_id = Column(String)
    status = Column(String) # success, failure, fallback
    error_code = Column(String, nullable=True)
    response = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task", back_populates="attempts")

class ToolActionStatus(enum.Enum):
    PROPOSED = "proposed"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ToolAction(Base):
    __tablename__ = "tool_actions"
    
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("tasks.id"))
    action_name = Column(String)
    arguments = Column(JSON)
    status = Column(SQLEnum(ToolActionStatus), default=ToolActionStatus.PROPOSED)
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    task = relationship("Task", back_populates="tool_actions")
