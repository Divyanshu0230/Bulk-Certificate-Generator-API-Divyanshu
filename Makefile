.PHONY: run test preview

run:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	pytest

preview:
	python -m app.preview
