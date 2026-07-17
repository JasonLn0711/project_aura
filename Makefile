PYTHON ?= python
PYTHONPATH ?= src
UV ?= uv

.PHONY: setup-app setup-dev check test compile build bump-version clean

setup-app:
	$(UV) sync --extra punctuation --inexact

setup-dev:
	$(UV) sync --all-extras

check: compile test

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -W error::ResourceWarning -m unittest discover -s tests

compile:
	$(PYTHON) -m compileall src tests

build:
	$(UV) build

bump-version:
ifndef VERSION
ifndef BUMP
	$(error VERSION or BUMP is required, for example make bump-version BUMP=minor)
endif
endif
	$(PYTHON) scripts/bump_version.py $(if $(VERSION),$(VERSION),--increment $(BUMP)) $(if $(RELEASE_DATE),--date $(RELEASE_DATE),)

clean:
	rm -rf build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
