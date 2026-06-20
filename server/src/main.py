from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers.traffic import router as traffic_router

app = FastAPI(title="Chennai Traffic Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(traffic_router)

@app.get("/")
def root():
    return {"status": "ok", "system": "Chennai Traffic Management"}
