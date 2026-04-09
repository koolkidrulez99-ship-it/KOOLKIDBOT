# Deploy Notes

## Runtime rule
- Run the app as a single Gunicorn worker.
- Current Procfile:
  - `web: gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT serverapp:application`
- Repo files that make deploy more tolerant:
  - `Procfile`
  - `serverapp.py`

## Why single worker matters
- This bot keeps live trading state in memory.
- Profile state, active contracts, martingale progress, and auto-trade flow can drift or break if multiple workers handle the same browser session.
- Local works like a single process, so deploy should mirror that.

## Frontend cache-busting
- The main dashboard now passes an asset version into `index.html`.
- Profile scripts are loaded with `?v=<asset_version>` so deploys pick up fresh JS instead of stale cached files.

## If deploy behaves differently from local
1. Confirm the platform is actually using the repo Procfile.
2. Confirm it is starting `serverapp:application` or `server:app`.
3. Confirm it is using one worker.
4. Hard refresh the browser after deploy.
