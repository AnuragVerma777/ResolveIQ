"""FastAPI routes for ResolveIQ."""
from backend.api.documents import router as documents_router
from backend.api.disputes import router as disputes_router
from backend.api.resolution import router as resolution_router

__all__ = ["documents_router", "disputes_router", "resolution_router"]
