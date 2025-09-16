from fastapi import FastAPI

from app.routes import admin, webhooks


def create_app() -> FastAPI:
    application = FastAPI(title="Autoclipper", version="0.1.0")

    @application.get("/health")
    def health():
        return {"ok": True}

    @application.get("/healthz")
    def healthz():
        return {"ok": True}

    application.include_router(admin.router)
    application.include_router(webhooks.router)
    return application


app = create_app()
