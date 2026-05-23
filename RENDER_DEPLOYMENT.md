# Render Deployment Guide

## Prerequisites
1. GitHub repository with all files pushed (including models in `backend/models/`)
2. Render.com account (free tier available)
3. Frontend deployed on Vercel (or another hosting service)

## Deployment Steps

### 1. Connect Render to GitHub
1. Go to [render.com](https://render.com)
2. Click "New +" → "Blueprint"
3. Connect your GitHub repository
4. Select the repository containing this project

### 2. Deploy using render.yaml
- Render will automatically detect and use the `render.yaml` file
- It will create:
  - PostgreSQL database (free tier)
  - FastAPI backend service (free tier)
  - Persistent disk for model storage

### 3. Configure CORS for Frontend
After deployment, update the `ALLOWED_ORIGINS` environment variable:

1. Go to Render Dashboard → lens-detection-backend → Environment
2. Update the `ALLOWED_ORIGINS` variable to include your Vercel/frontend domain:
   ```
   https://your-frontend-domain.vercel.app
   ```
3. Click "Deploy" to redeploy with new settings

### 4. Get Backend URL
After deployment, your backend URL will be:
```
https://lens-detection-backend.onrender.com
```

### 5. Update Frontend API Client
Update the frontend API client to use the Render backend URL:

In `frontend/src/api/client.js`:
```javascript
const API_BASE_URL = process.env.VITE_API_URL || 'https://lens-detection-backend.onrender.com';
```

Create `.env.production` in the frontend:
```
VITE_API_URL=https://lens-detection-backend.onrender.com
```

## Important Notes

### Free Tier Limitations
- **Memory**: 512 MB (may be tight for YOLO inference)
- **CPU**: Shared CPU (slow)
- **Inactivity**: Service suspends after 15 minutes of inactivity
- **Build time**: Limited to 30 minutes
- **Disk**: 10 GB persistent disk for models

### Model Storage
- Models are copied to `backend/models/` during build
- The persistent disk (`/app/data`) is for runtime data/outputs
- Total project size should be under 100 MB for free tier

### Database
- PostgreSQL 14 on free tier
- No backup/replication
- 256 MB storage

### Cold Starts
- First request after inactivity takes 30-60 seconds
- Model loading adds 20-40 seconds
- Total: ~60-100 seconds for first inference after cold start

## Troubleshooting

### Models fail to load
- Check build logs for torch/YOLO download issues
- Pre-commit models to repository if build fails

### Database connection errors
- Verify `DATABASE_URL` environment variable is set
- Check database service is running in Render dashboard

### Frontend can't reach backend
- Verify CORS is configured with frontend domain
- Check backend URL is correct in frontend API client
- Use browser dev tools to inspect network errors

### Performance issues
- Consider upgrading from free tier (recommended for production)
- Use model quantization to reduce size
- Implement caching for repeated inferences

## Deployment Script (Optional)
Create a GitHub Actions workflow to auto-deploy on push:

```yaml
name: Deploy to Render

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to Render
        run: |
          curl -X POST https://api.render.com/deploy/srv-${{ secrets.RENDER_SERVICE_ID }}?key=${{ secrets.RENDER_DEPLOY_KEY }}
```

Get the service ID and deploy key from Render → Settings
