.PHONY: install clean-data run test lint format clean

# Install all dependencies (runtime + dev)
install:
	pip install -r requirements-dev.txt

# Run the Excel → Parquet cleaning pipeline
clean-data:
	python scripts/clean_data.py

# Start the FastAPI dev server with hot reload
run:
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Run the full test suite
test:
	pytest

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
