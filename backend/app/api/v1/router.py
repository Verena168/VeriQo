from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    applications,
    auth,
    hackathons,
    reports,
    submissions,
    teams,
    telemetry,
)

api_router = APIRouter()
for module in (auth, hackathons, applications, teams, submissions, telemetry, reports, analytics):
    api_router.include_router(module.router)
