FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY fantasyiq ./fantasyiq
COPY models ./models
COPY models/collaborative_recommender.joblib ./models/collaborative_recommender.joblib
COPY data/processed/player_gameweeks.csv.gz ./data/processed/player_gameweeks.csv.gz
COPY data/processed/next_gw_manifest.json ./data/processed/next_gw_manifest.json
COPY reports/player_profiles.csv ./reports/player_profiles.csv
COPY reports/player_profile_metrics.json ./reports/player_profile_metrics.json
COPY reports/transfer_rl_metrics.json ./reports/transfer_rl_metrics.json
COPY reports/hybrid_recommender_evaluation.json ./reports/hybrid_recommender_evaluation.json

RUN python -c "from pathlib import Path; required=['data/processed/player_gameweeks.csv.gz','data/processed/next_gw_manifest.json','models/next_gw_hist_gradient_boosting.joblib','reports/transfer_rl_metrics.json','reports/hybrid_recommender_evaluation.json']; missing=[name for name in required if not Path(name).is_file()]; assert not missing, f'Missing runtime assets: {missing}'"

EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
