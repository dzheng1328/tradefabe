import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tradefabe import dashboard

app = FastAPI(title="tradefabe dashboard API")

# Vite's dev server -- the only origin that ever calls this locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/books/summary")
def books_summary():
    psum, _phist = dashboard.load_paper_state()
    if psum is None:
        return []
    return psum.astype(object).fillna(None).to_dict(orient="records")


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
