from fastapi import FastAPI

from app.api.v1.jobs import router as jobs_router

app = FastAPI(title="Document Processing Gateway")

app.include_router(jobs_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
