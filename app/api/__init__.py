"""
API Router
"""
from fastapi import APIRouter

from app.api.endpoints import (
    auth,
    users,
    children,
    vocabulary,
    categories,
    stories,
    bedtime_stories,
    games,
    missions,
    progress,
    analytics,
    adaptive_learning,
    parent_dashboard,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(children.router, prefix="/children", tags=["Children"])
api_router.include_router(vocabulary.router, prefix="/vocabulary", tags=["Vocabulary"])
api_router.include_router(categories.router, prefix="/categories", tags=["Categories"])
api_router.include_router(stories.router, prefix="/stories", tags=["Stories"])
api_router.include_router(bedtime_stories.router, prefix="/bedtime-stories", tags=["Bedtime Stories"])
api_router.include_router(games.router, prefix="/games", tags=["Games"])
api_router.include_router(missions.router, prefix="/missions", tags=["Missions"])
api_router.include_router(progress.router, prefix="/progress", tags=["Progress"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(adaptive_learning.router, prefix="/adaptive", tags=["Adaptive Learning"])
api_router.include_router(parent_dashboard.router)
