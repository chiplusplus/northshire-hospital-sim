.PHONY: gen-data

PY=python3

gen-data:
	$(PY) -m generators.generate_data