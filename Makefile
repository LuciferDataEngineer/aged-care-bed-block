PYTHON ?= python3
export PYTHONPATH := src
export JAVA_HOME ?= /usr/lib/jvm/java-17-openjdk-amd64
DOCKER := $(shell if docker info >/dev/null 2>&1; then echo docker; else echo sudo docker; fi)
COMPOSE := $(DOCKER) compose -p agedcare -f docker-compose.yml

.PHONY: setup refresh up cdc lakehouse test lint dashboard bench down smoke-contracts

setup:
	$(PYTHON) -m pip install -r requirements.txt

refresh:
	$(PYTHON) -m agedcare.refresh

up:
	$(COMPOSE) up -d
	$(PYTHON) -m agedcare.stack

cdc: up
	$(PYTHON) -m agedcare.oltp

lakehouse:
	JAVA_HOME=$(JAVA_HOME) $(PYTHON) -m agedcare.lakehouse

test:
	$(PYTHON) -m pytest -q tests/unit

lint:
	$(PYTHON) -m ruff check src tests

smoke-contracts:
	$(PYTHON) -m agedcare.contracts

dashboard:
	$(PYTHON) -m agedcare.build_marts
	$(PYTHON) -m agedcare.sitebuild

bench: lakehouse
	@echo "Benchmarks written to docs/benchmarks.json"

down:
	$(COMPOSE) down -v --remove-orphans
