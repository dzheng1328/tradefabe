import json

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
    # astype(object).fillna(None) raises ValueError on pandas 2.x ("Must specify a fill
    # 'value' or 'method'") even though it works on pandas 3.x, and pandas has no version
    # floor in pyproject.toml. to_json has serialized NaN as JSON null consistently across
    # pandas versions for years, so round-tripping through it sidesteps that fragility.
    return json.loads(psum.to_json(orient="records"))


def run():
    """Entry point for the `tradefabe-api` console script."""
    import uvicorn
    uvicorn.run("tradefabe.api.main:app", host="127.0.0.1", port=8000, reload=True)
