"""Standalone local experiment API, independent of online RAG/Memory/server keys.
Run with: PYTHONPATH=. python -m uvicorn experiments.app:app --host 127.0.0.1
"""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI
from core.skill_loader import SkillManager
from .service import ExperimentService
from .store import JsonStore
from .api import router, configure, install_validation_handler
from .retrieval_api import router as retrieval_router
from .retrieval_service import RetrievalService
from .career_api import router as career_router
from .practice_api import router as practice_router
from .assist_api import router as assist_router
from .workspaces import WorkspaceMiddleware, WorkspaceRegistry, request_service

@asynccontextmanager
async def lifespan(app):
    root = Path(__file__).resolve().parents[1]
    if os.getenv('AGENTEVAL_ANONYMOUS_WORKSPACES') == '1':
        registry = WorkspaceRegistry(
            os.environ['AGENTEVAL_WORKSPACE_DIR'],
            os.getenv('AGENTEVAL_SKILL_TEMPLATE_DIR', str(root/'skills')),
            os.environ['AGENTEVAL_PUBLIC_ORIGIN'],
            secure=os.getenv('AGENTEVAL_COOKIE_SECURE', '1') == '1')
        app.state.workspaces = registry
        def isolated_service():
            value = request_service.get()
            if value is None:
                raise ValueError('Workspace request required')
            return value
        configure(isolated_service)
        try:
            yield
        finally:
            registry.close()
            app.state.workspaces = None
        return
    app.state.workspaces = None
    manager = SkillManager(os.getenv('AGENTEVAL_SKILL_DIR',str(root/'skills')))
    manager.load_strict()
    service = ExperimentService(JsonStore(os.getenv('AGENTEVAL_EXPERIMENT_DIR',str(root/'data/experiments'))),manager)
    service.retrieval = RetrievalService(service)
    app.state.experiments = service
    configure(lambda:service)
    try:
        yield
    finally:
        # Keys have no file lifecycle. Dropping this process vault makes surviving
        # public records unavailable; only explicit DELETE marks records deleted.
        service.providers._keys.clear()
        service.store.forbidden_values = ()

app = FastAPI(title='Agent Eval',lifespan=lifespan)
app.add_middleware(WorkspaceMiddleware)
app.include_router(career_router)
app.include_router(assist_router)
app.include_router(practice_router)
app.include_router(retrieval_router)
app.include_router(router)  # Historical generic GET route must follow explicit Retrieval routes.
install_validation_handler(app)
