# Optical Lens Defect Detection System

Real-time QA system: live camera → lens segmentation → OBB defect detection → Pass/Fail decision.

## Architecture

```
Camera (browser) → WebSocket → FastAPI backend
                                  ├── lens_segmentor.py   (YOLOv8n-seg, every 3s)
                                  ├── defect_detector.py  (best.pt OBB, every frame)
                                  ├── decision.py         (annotate + Pass/Fail)
                                  └── SQLite / PostgreSQL (throttled writes)
React frontend  ← WebSocket ← annotated JPEG + JSON metadata
```

## Quick Start (local)

```bash
# 1. Place your trained weights
cp path/to/best.pt backend/models/best.pt

# 2. (Optional) Train the lens segmentation model
pip install ultralytics roboflow
export ROBOFLOW_API_KEY=your_key
python scripts/train_lens_segmentation.py
# → writes backend/models/lens_seg.pt

# 3. Run with Docker Compose
docker compose -f docker/docker-compose.yml up --build

# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
```

## Deploy: Railway (backend) + Vercel (frontend)

### Backend → Railway

1. Push this repo to GitHub
2. Railway dashboard → New Project → Deploy from GitHub repo
3. Railway auto-detects `railway.json` and uses `docker/Dockerfile.backend`
4. Add environment variables in Railway dashboard (see `.env.example`):
   - `DATABASE_URL` — add Railway PostgreSQL plugin and copy the URL
   - `MODEL_PATH=models/best.pt`
   - `LENS_SEG_MODEL_PATH=models/lens_seg.pt` (after training)
   - `CONFIDENCE_THRESHOLD=0.3`
   - `SEG_INTERVAL=3.0`
5. Your backend URL will be: `https://your-project.railway.app`

> **Note:** `best.pt` must be committed to `backend/models/` (or mounted via Railway volume).
> The `lens_seg.pt` model is created by running the training script — commit it too.

### Frontend → Vercel

1. Vercel dashboard → New Project → Import from GitHub (select `frontend/` as root directory)
2. Add environment variable:
   - `VITE_API_URL=https://your-project.railway.app`
3. Deploy — Vercel auto-detects Vite and uses `vercel.json`

### CORS

The backend currently allows all origins (`allow_origins=["*"]`). For production,
replace this in `backend/main.py` with your Vercel domain:

```python
allow_origins=["https://your-app.vercel.app"],
```

## Lens Segmentation Model Training

Run `scripts/train_lens_segmentation.py` to fine-tune YOLOv8n-seg on real lens images:

```bash
# Get a free API key at roboflow.com
export ROBOFLOW_API_KEY=your_key
python scripts/train_lens_segmentation.py --epochs 60 --device 0
# Output: backend/models/lens_seg.pt
```

Without `lens_seg.pt`, the system falls back to a GrabCut + ellipse-fitting CV pipeline
which works well for clean lab setups (lens on flat surface with clear background).

## Pipeline Timing

| Stage | Frequency | Why |
|---|---|---|
| Lens segmentation | Every 3s (configurable) | ML model is slow; lens doesn't move fast |
| Defect detection | Every frame | Fast OBB model on small cached ROI |
| DB write | Every 5s | Avoid hammering SQLite under load |
| WS ping | Every 20s | Keep Railway proxy connection alive |

## Models

| File | Purpose | Size |
|---|---|---|
| `backend/models/best.pt` | OBB defect detection (bubble/crack/dots/scratch) | ~50MB |
| `backend/models/lens_seg.pt` | Custom lens segmentation (trained by you) | ~6MB |
| `backend/models/yolov8n-seg.pt` | Generic fallback segmentation (auto-downloaded) | ~6MB |

<img width="1600" height="900" alt="image" src="https://github.com/user-attachments/assets/4de23231-d874-49e0-9a5d-e6f9d2dc54d5" />

