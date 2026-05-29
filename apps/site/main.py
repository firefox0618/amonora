import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from apps.shared.public_runtime import (
    SITE_STATIC_DIR,
    lifespan,
    setup_common_public_app,
)
from apps.site.routes import router as site_router


app = FastAPI(
    title="Amonora Site",
    description="Public site for the Amonora ecosystem.",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=str(SITE_STATIC_DIR)), name="static")
setup_common_public_app(app, redirect_public_hosts=True)
app.include_router(site_router)


def main() -> None:
    uvicorn.run(
        "apps.site.main:app",
        host="127.0.0.1",
        port=8091,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
