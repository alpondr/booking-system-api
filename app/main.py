from fastapi import FastAPI

app = FastAPI(title="Booking System API")


# Simple health check, useful to confirm the server is up
@app.get("/")
def root():
    return {"message": "Booking System API is running"}
