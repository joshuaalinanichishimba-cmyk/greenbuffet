from fastapi import APIRouter

from app.api.v1 import (
    admin, auth, books, customers, dashboard,
    home, health, kitchen, menu, people, reports,
    it, sales, settings_api, stock, team,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(menu.router)
api_router.include_router(sales.router)
api_router.include_router(kitchen.router)
api_router.include_router(stock.router)
api_router.include_router(books.router)
api_router.include_router(people.router)
api_router.include_router(reports.router)
api_router.include_router(settings_api.router)
api_router.include_router(customers.router)
api_router.include_router(dashboard.router)
api_router.include_router(home.router)
api_router.include_router(team.router)
api_router.include_router(it.router)
