import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.client.routes import router as client_router
from apps.shared.public_runtime import (
    CLIENT_STATIC_DIR,
    lifespan,
    setup_common_public_app,
)


app = FastAPI(
    title="Amonora Client",
    description="Public client subscription surface for the Amonora ecosystem.",
    lifespan=lifespan,
)
app.mount("/client-static", StaticFiles(directory=str(CLIENT_STATIC_DIR), check_dir=False), name="client-static")
setup_common_public_app(app, redirect_public_hosts=False)
app.include_router(client_router)


def main() -> None:
    uvicorn.run(
        "apps.client.main:app",
        host="127.0.0.1",
        port=8092,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
