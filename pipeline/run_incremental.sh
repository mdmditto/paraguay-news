#!/usr/bin/env bash
set -euo pipefail

cd /home/marcos/projects/paraguay_news

PYTHON="/home/marcos/projects/paraguay_news/.venv/bin/python"

echo "===== COLLECTOR START: $(date) ====="

$PYTHON run_collector.py

echo "===== PIPELINE START: $(date) ====="

$PYTHON -m pipeline.process_new_articles \
    --stage all \
    --limit 100 \
    --skip-drafts

echo "===== COMPLETED: $(date) ====="