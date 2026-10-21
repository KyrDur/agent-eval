"""App-local daily scheduler; each domain is dispatched to its own leased worker."""
import asyncio
from .operations_service import OperationsService

async def scheduler(app):
    while True:
        registry=getattr(app.state,'workspaces',None)
        services=list(registry.services.values()) if registry else [app.state.experiments]
        for service in services:
            if not hasattr(service,'operations'):service.operations=OperationsService(service)
            try:
                await service.operations.tick()
                service.operations.scheduler_error=None
            except Exception:service.operations.scheduler_error='OPERATIONS_SCHEDULER_FAILED'
        await asyncio.sleep(10)
