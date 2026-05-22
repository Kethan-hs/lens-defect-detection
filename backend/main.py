import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.stream      import router as stream_router
from routes.inspections import router as inspections_router
from routes.export      import router as export_router
from db.database        import engine, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Optical Lens Defect Detection API", version="1.1.0")

# In production set ALLOWED_ORIGINS to your Vercel domain, e.g.:
#   ALLOWED_ORIGINS=https://your-app.vercel.app
_origins_env = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in _origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stream_router)
app.include_router(inspections_router)
app.include_router(export_router)


@app.get("/")
def read_root():
    return {"message": "Lens Defect System API is running", "version": "1.1.0"}


@app.get("/health")
def health():
    """
    Health-check used by Railway and load balancers.
    Returns 200 as long as the process is alive.
    Model load status is included so ops can tell whether YOLO weights are ready.
    """
    from pipeline.defect_detector import _model as defect_model
    from pipeline.lens_segmentor  import _model as seg_model
    return {
        "status":       "ok",
        "defect_model": "loaded" if defect_model is not None else "not_loaded",
        "seg_model":    "loaded" if seg_model    is not None else "not_loaded",
    }