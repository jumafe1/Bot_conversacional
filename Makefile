.PHONY: install clean-data run test smoke-bot lint format clean frontend-install frontend-dev frontend-build

# Install all dependencies (runtime + dev)
install:
	pip install -r requirements-dev.txt

# Run the Excel → Parquet cleaning pipeline
clean-data:
	PYTHONPATH=. python scripts/clean_data.py

# Run EDA profiler and regenerate docs/data_quality_report.md
explore-data:
	PYTHONPATH=. python scripts/explore_data.py

# Start the FastAPI dev server with hot reload
run:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Run the full test suite
test:
	pytest

# Live smoke test against the real LLM provider. Spends API tokens.
# Pass CASES="1 3" to limit to specific cases.
smoke-bot:
	PYTHONPATH=. python scripts/smoke_test_bot.py --confirm-cost $(if $(CASES),--only $(CASES),)

# --- Frontend (Next.js + assistant-ui) ---------------------------------------

# Install Node dependencies
frontend-install:
	cd frontend && npm install

# Start the Next.js dev server on :3000 (requires backend running on :8000)
frontend-dev:
	cd frontend && npm run dev

# Production build of the frontend
frontend-build:
	cd frontend && npm run build

# Run linter (errors only, no warnings)
lint:
	ruff check .

# Auto-format all Python files
format:
	ruff format .

# Remove all build/cache artifacts
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name "*.pyo" -delete 2>/dev/null || true
