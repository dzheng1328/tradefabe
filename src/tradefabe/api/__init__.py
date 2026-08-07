"""tradefabe.api -- thin FastAPI read layer over tradefabe.dashboard.

No business logic lives here: every response is built from tradefabe.dashboard /
tradefabe.engine data, so the API and the (still-live) Streamlit app read from one
place. Local-only -- binds to localhost, no auth, same trust boundary the paper-only
hard rule already gives the Streamlit app.
"""
