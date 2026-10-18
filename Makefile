PYTHON ?= $(UV) run --no-sync python
PYTHONPATH ?= src
UV ?= uv
CARGO ?= $(HOME)/.cargo/bin/cargo

.PHONY: setup-app setup-dev check test compile build bump-version clean

setup-app:
	@if [ "$$(uname -m)" = aarch64 ] && [ -f runtime/gx10-cuda13/build-receipt.json ]; then \
		$(PYTHON) scripts/setup_gpu_runtime.py --sync; \
	else \
		$(UV) sync --locked --extra cli --extra gui --extra capture --extra server --extra punctuation --inexact; \
	fi
	$(MAKE) install-capture

.PHONY: setup-client build-capture install-capture check-capture
setup-client:
	$(UV) sync --locked
	$(MAKE) install-capture

build-capture:
	$(CARGO) build --release --locked --manifest-path native/aura-capture/Cargo.toml

install-capture: build-capture
	install -m 755 native/aura-capture/target/release/aura-capture .venv/bin/aura-capture

check-capture:
	$(CARGO) fmt --manifest-path native/aura-capture/Cargo.toml -- --check
	$(CARGO) clippy --locked --manifest-path native/aura-capture/Cargo.toml --all-targets -- -D warnings
	$(CARGO) test --locked --manifest-path native/aura-capture/Cargo.toml

setup-dev:
	$(UV) sync --locked --all-extras

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

.PHONY: architecture-setup architecture-check architecture-build architecture-serve
architecture-setup:
	python3 scripts/architecture.py setup

architecture-check:
	python3 scripts/architecture.py check

architecture-build:
	python3 scripts/architecture.py build

architecture-serve:
	python3 scripts/architecture.py serve
