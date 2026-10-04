.PHONY: setup build test backtest sensitivity robustness parameters replay profile bench docker-build clean

PYTHON ?= python3
BUILD_DIR ?= build

setup:
	$(PYTHON) -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip && pip install -e '.[full]'

build:
	cmake -S . -B $(BUILD_DIR) -DCMAKE_BUILD_TYPE=Release
	cmake --build $(BUILD_DIR) --parallel

test:
	$(PYTHON) -m pytest -q
	ctest --test-dir $(BUILD_DIR) --output-on-failure

backtest:
	$(PYTHON) scripts/run_backtest.py

sensitivity:
	$(PYTHON) scripts/sensitivity_backtest.py

robustness:
	$(PYTHON) scripts/robustness_backtest.py

parameters:
	$(PYTHON) scripts/parameter_sensitivity.py

replay:
	$(PYTHON) scripts/generate_sample_telemetry_db.py --ticks 5000
	$(PYTHON) scripts/replay_duckdb.py --db results/sample_telemetry.duckdb

profile:
	$(PYTHON) scripts/system_profile.py

bench: build
	./$(BUILD_DIR)/sentinel/sentinel_engine_bench 200000
	./$(BUILD_DIR)/sentinel/sentinel_spsc_bench
	$(PYTHON) scripts/benchmark_duckdb.py --ticks 1000000 --batch 100000

docker-build:
	docker build -t sentinel-statarb .

clean:
	rm -rf $(BUILD_DIR) build-san .pytest_cache
