from fastapi import FastAPI

from app.routers import auth

app = FastAPI(title="Booking System API")

app.include_router(auth.router)


# Simple health check, useful to confirm the server is up
@app.get("/")
def root():
    return {"message": "Booking System API is running"}
