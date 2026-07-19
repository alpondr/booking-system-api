from fastapi import FastAPI

from app.routers import appointments, auth, services

app = FastAPI(title="Booking System API")

app.include_router(auth.router)
app.include_router(services.router)
app.include_router(appointments.router)


# Simple health check, useful to confirm the server is up
@app.get("/")
def root():
    return {"message": "Booking System API is running"}
