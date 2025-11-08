# Makefile tasks for common BioSignal-AI workflows

.PHONY: install test lint run-app

install:
	python -m venv .venv
	.venv\Scripts\activate && pip install --upgrade pip && pip install -r requirements.txt

test:
	.venv\Scripts\activate && pytest

lint:
	.venv\Scripts\activate && ruff check src

run-app:
	.venv\Scripts\activate && streamlit run src/app/streamlit_app.py
