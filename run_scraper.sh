#!/bin/bash
# Noclout Scraper Runner
# Run from project directory

cd "$(dirname "$0")"

# Load virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Run the scraper
python3 main.py

# Log output with timestamp
echo "$(date): Scraper completed" >> scraper.log