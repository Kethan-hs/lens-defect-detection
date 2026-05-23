# Deployment Checklist for Render

## Pre-Deployment Setup

### GitHub Repository
- [ ] All backend code committed (backend/ folder)
- [ ] All frontend code committed (frontend/ folder)
- [ ] Model files committed:
  - [ ] `backend/models/best.pt`
  - [ ] `backend/models/lens_seg.pt`
  - [ ] `yolov8n-seg.pt` (if needed at root)
- [ ] Docker files committed:
  - [ ] `docker/Dockerfile.backend`
  - [ ] `docker/Dockerfile.frontend`
- [ ] Configuration files committed:
  - [ ] `render.yaml`
  - [ ] `backend/requirements.txt`
  - [ ] `frontend/package.json`
- [ ] Local files NOT committed (should be in .gitignore):
  - [ ] `backend/lens_inspections.db`
  - [ ] `node_modules/` folders
  - [ ] `.env` files (except .env.production/.env.development)

### File Size Verification
```bash
# Check total repo size (should be <100 MB for free tier)
du -sh .

# Check model files size
du -sh backend/models/
du -sh yolov8n-seg.pt
```

If models are too large (>50 MB):
- Use `git-lfs` to store models
- OR split into multiple model files
- OR use model quantization

### GitHub Setup
- [ ] Repository is public (Render needs access)
- [ ] All files pushed to `main` branch
- [ ] Enable branch protection rules (optional)

## Render Deployment

### Create Render Account
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Grant Render access to your repository

### Deploy Using Blueprint
1. Click "New +" button in Render dashboard
2. Select "Blueprint"
3. Connect repository
4. Select the repository with lens-defect-detection-system
5. Render will read `render.yaml` and create:
   - PostgreSQL database
   - FastAPI backend service
   - Persistent disk for models

### Configuration After Deployment
1. Go to Render Dashboard
2. Click on "lens-detection-backend" service
3. Go to "Environment" tab
4. Update `ALLOWED_ORIGINS`:
   ```
   https://your-frontend.vercel.app,https://lens-detection-backend.onrender.com
   ```
5. Click "Deploy" button to redeploy

### Get Your URLs
- Backend API: `https://lens-detection-backend.onrender.com`
- Database: Check Render dashboard for connection details

## Frontend Deployment (Vercel)

### Create Vercel Project
1. Go to [vercel.com](https://vercel.com)
2. Import your GitHub repository
3. Select "frontend" folder as root
4. Environment variables:
   ```
   VITE_API_URL=https://lens-detection-backend.onrender.com
   ```

### Test Deployment
1. Frontend loads at: `https://<your-project>.vercel.app`
2. Check browser console for API connection errors
3. Test API endpoints (Health, Inspections, etc.)

## Post-Deployment Testing

### Backend Health Checks
```bash
# Check if backend is running
curl https://lens-detection-backend.onrender.com/health

# Expected response:
# {
#   "status": "ok",
#   "defect_model": "loaded",
#   "seg_model": "loaded"
# }
```

### Frontend API Tests
1. Open frontend in browser
2. Check Network tab in DevTools
3. Verify API calls go to Render backend (not localhost)
4. Test main features:
   - [ ] Load inspections list
   - [ ] View defect statistics
   - [ ] Export CSV
   - [ ] Export PDF

### Database Verification
1. Models created properly
2. Inspections can be saved
3. Data persists across requests

## Troubleshooting

### Build Fails
```
Error: torch installation failed
Fix: 
- Remove torch from requirements.txt
- Render provides pre-built torch packages
```

### Models Not Loading
```
Error: Could not load YOLOv8 model
Fix:
- Verify model files are in backend/models/
- Check Dockerfile copies models correctly
- Models should be under 50 MB each
```

### Database Connection Fails
```
Error: Could not connect to database
Fix:
- Check DATABASE_URL environment variable
- Verify PostgreSQL database is running
- Connection string should be: postgresql://user:pass@host:port/dbname
```

### Frontend Can't Reach Backend
```
Error: CORS error or network timeout
Fix:
- Check ALLOWED_ORIGINS includes frontend domain
- Verify backend URL in frontend API client
- Check Network tab in browser DevTools
- Wait 60-90 seconds for cold start
```

### Slow Response Times
```
Symptom: First request takes >60 seconds
Cause: Cold start + model loading
Solution:
- This is normal on free tier
- Consider upgrading to paid plan for production
- Implement request timeout handling in frontend
```

## Performance Optimization

### Reduce Model Size
```python
# Convert to FP16 (half precision)
from ultralytics import YOLO
model = YOLO('best.pt')
model.export(format='pt', device=0, half=True)
```

### Enable Caching
Add caching headers to API responses to reduce redundant processing

### Monitor Render Logs
Render Dashboard → Services → lens-detection-backend → Logs

## Maintenance

### Regular Updates
- [ ] Monitor disk usage on Render
- [ ] Check for model updates
- [ ] Review API logs for errors
- [ ] Update dependencies

### Backup Database
```bash
# Export PostgreSQL data
pg_dump postgresql://user:pass@host/dbname > backup.sql
```

### Rollback Procedure
If deployment fails:
1. Render Dashboard → Deployments → Select previous
2. Click "Redeploy"
3. Check logs and fix issues
4. Push fixes to GitHub
5. Trigger new deployment

## Cost Considerations

### Free Tier (Current)
- Backend: Free
- Database: Free (256 MB)
- Bandwidth: 100 GB/month included
- Duration: $0/month

### Upgrade Path
If you need better performance:
- **Starter**: $7/month - 512 MB RAM, 24/7 uptime
- **Standard**: $25+/month - More resources, better support
