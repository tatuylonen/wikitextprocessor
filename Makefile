# Run "make test" to run tests
# Run "make clean" to remove automatically generated files
ruff:
	python -m ruff check --diff src/wikitextprocessor
	python -m ruff check --diff tests
test:
	python -m unittest discover -b -s tests
test_coverage:
	python -m coverage erase
	python -m coverage run -m unittest discover -b -s tests
coverage_report:
	python -m coverage html
clean:
	python -m coverage erase
	rm -rf __pycache__ htmlcov
