# pylogikcs - high-level commands
# Usage: just [recipe] [args...]
# Run `just` with no arguments to list recipes.

inspect file="assets/Default.logikcs":
    @PYTHONPATH=src python3 -m pylogikcs._cli inspect {{file}}

list file="assets/Default.logikcs":
    @PYTHONPATH=src python3 -m pylogikcs._cli list {{file}}

set-color file command_id color output="":
    @PYTHONPATH=src python3 -m pylogikcs._cli set-color {{file}} {{command_id}} {{color}} {{ if output != "" { "-o " + output } else { "" } }}

set-binding file index key-code flags output="":
    @PYTHONPATH=src python3 -m pylogikcs._cli set-binding {{file}} {{index}} --key-code {{key-code}} --flags {{flags}} {{ if output != "" { "-o " + output } else { "" } }}

lint:
    @ruff check src/ tests/

fmt:
    @ruff format src/ tests/

test: lint
    @python3 -m unittest tests.test_logikcs -v

install:
    @pip install -e .

clean:
    @find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
    @find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null; true
    @rm -rf build dist .pytest_cache 2>/dev/null; true
