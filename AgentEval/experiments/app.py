"""Standalone local experiment API, independent of online RAG/Memory/server keys.
Run with: PYTHONPATH=. python -m uvicorn experiments.app:app --host 127.0.0.1
"""
from contextlib import asynccontextmanager
import os
import asyncio
from .operations_api import router as operations_router
from .operations_scheduler import scheduler
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
from .calibration_api import router as calibration_router
from .calibration_service import CalibrationService
from .retrieval_background import close_background
from .learning_api import router as learning_router
from .workspaces import WorkspaceMiddleware, WorkspaceRegistry, request_service
from .analytics import AnalyticsStore, AnalyticsMiddleware

@asynccontextmanager
async def lifespan(app):
    root = Path(__file__).resolve().parents[1]
    app.state.retrieval_slots=asyncio.Semaphore(2)
    analytics_dir = os.getenv('AGENTEVAL_ANALYTICS_DIR')
    app.state.analytics = AnalyticsStore(analytics_dir, os.getenv('AGENTEVAL_ANALYTICS_TOKEN_FILE')) if analytics_dir else None
    if os.getenv('AGENTEVAL_ANONYMOUS_WORKSPACES') == '1':
        registry = WorkspaceRegistry(
            os.environ['AGENTEVAL_WORKSPACE_DIR'],
            os.getenv('AGENTEVAL_SKILL_TEMPLATE_DIR', str(root/'skills')),
            os.environ['AGENTEVAL_PUBLIC_ORIGIN'],
            secure=os.getenv('AGENTEVAL_COOKIE_SECURE', '1') == '1')
        app.state.workspaces = registry
        handoff=None
        if os.getenv('AGENTEVAL_HANDOFF_SOCKET'):
            from .memory_handoff import MemoryHandoff
            handoff=await MemoryHandoff(registry,os.environ['AGENTEVAL_HANDOFF_SOCKET']).start()
        def isolated_service():
            value = request_service.get()
            if value is None:
                raise ValueError('Workspace request required')
            return value
        configure(isolated_service)
        task=asyncio.create_task(scheduler(app))
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
            for service in list(registry.services.values()):
                if hasattr(service,'retrieval'):await close_background(service.retrieval)
            if handoff:await handoff.close()
            registry.close()
            app.state.workspaces = None
        return
    app.state.workspaces = None
    manager = SkillManager(os.getenv('AGENTEVAL_SKILL_DIR',str(root/'skills')))
    manager.load_strict()
    service = ExperimentService(JsonStore(os.getenv('AGENTEVAL_EXPERIMENT_DIR',str(root/'data/experiments'))),manager)
    service.retrieval = RetrievalService(service)
    service.calibration = CalibrationService(service)
    app.state.experiments = service
    configure(lambda:service)
    task=asyncio.create_task(scheduler(app))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        await close_background(service.retrieval)
        # Keys have no file lifecycle. Dropping this process vault makes surviving
        # public records unavailable; only explicit DELETE marks records deleted.
        service.providers._keys.clear()
        service.store.forbidden_values = ()

app = FastAPI(title='Agent Eval',lifespan=lifespan)
app.add_middleware(WorkspaceMiddleware)
app.add_middleware(AnalyticsMiddleware)
app.include_router(operations_router)
app.include_router(calibration_router)
app.include_router(learning_router)
app.include_router(career_router)
app.include_router(assist_router)
app.include_router(practice_router)
app.include_router(retrieval_router)
app.include_router(router)  # Historical generic GET route must follow explicit Retrieval routes.
install_validation_handler(app)
