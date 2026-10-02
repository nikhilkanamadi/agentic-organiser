.PHONY: setup seed run test clean

VENV := .venv/bin
PYTHON := $(VENV)/python

setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PYTHON) "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.8" "httpx>=0.27" "pytest>=8.0"

seed:
	$(PYTHON) -m data.seed.generate_synthetic_data

run:
	$(VENV)/uvicorn apps.api.main:app --reload --port 8000

test:
	$(PYTHON) -m pytest tests/ -v

clean:
	rm -f data/synthetic.db data/operational.db
