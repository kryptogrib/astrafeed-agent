from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AstraFeed Token Brief")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
