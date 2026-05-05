from fastapi import FastAPI

app = FastAPI(
    title="Workflow Automation API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/v1/openapi.json",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
