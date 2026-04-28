from fastapi import FastAPI

app = FastAPI(title="Document Processing Gateway")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
