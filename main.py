from fastapi import FastAPI

from auth_router import router as auth_router
from db import init_db
from links_router import router as links_router


app = FastAPI(title="URL Shortener", version="1.0.0")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


app.include_router(auth_router)
app.include_router(links_router)

