@echo off
echo Starting Datasette...
echo Open http://localhost:8001 in your browser
python -m datasette serve data/speeches.db --metadata metadata.yml --port 8001 --open
