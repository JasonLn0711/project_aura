PYTHON ?= python
PYTHONPATH ?= src

.PHONY: check test compile build bump-version clean

check: compile test

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -W error::ResourceWarning -m unittest discover -s tests

compile:
	$(PYTHON) -m compileall src tests

build:
	$(PYTHON) -m pip install --upgrade build
	$(PYTHON) -m build

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
