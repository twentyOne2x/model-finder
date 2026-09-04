.PHONY: test build demo render clean-help
PYTHON ?= python3

test:
	$(PYTHON) -m unittest discover -s tests -v

build:
	$(PYTHON) model_finder.py build

demo:
	$(PYTHON) model_finder.py demo

render:
	$(PYTHON) model_finder.py render model-finder.example.json --no-cursor

clean-help:
	@echo 'Generated files are isolated in .build/, .cache/, and dist/; remove those directories only when no watcher or export is running.'
