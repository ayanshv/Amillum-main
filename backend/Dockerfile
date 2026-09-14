FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/__init__.py backend/api.py backend/provider_engine.py backend/billing.py backend/catalog.py backend/
COPY core/__init__.py core/privacy.py core/
COPY services/__init__.py services/supabase.py services/email_drafting.py services/
COPY backend/config/plans.json backend/config/plans.json
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/healthz', timeout=3)"
CMD ["sh", "-c", "exec python -m uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
