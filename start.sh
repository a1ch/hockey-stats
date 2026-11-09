#!/bin/sh
# Container entry point on Azure Container Apps. The container pulls this repo's
# main branch at startup, so deploying = push to main, then restart the app.
set -e
cd /app
pip install --quiet --disable-pip-version-check --root-user-action=ignore --cache-dir /data/.pipcache -r requirements.txt
mkdir -p "${BJ_DATA_DIR:-/data/bj}"
exec python -m streamlit run app.py --server.port 8501 --server.address 0.0.0.0 \
  --server.headless true --browser.gatherUsageStats false
