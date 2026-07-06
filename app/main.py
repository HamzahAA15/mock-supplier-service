from fastapi import FastAPI

from app.routers import auth, flight

app = FastAPI(
    title="Mock Supplier Service",
    description="Deterministic mock of a Traveloka flight supplier (partner API server).",
    version="1.0.0",
)

app.include_router(auth.router)
app.include_router(flight.router)
