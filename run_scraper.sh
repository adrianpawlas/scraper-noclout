#!/bin/bash
# Noclout Scraper Runner
# Location: /Users/adrianpawlas/Finds/Scrapers/scraper-noclout/run_scraper.sh

cd "$(dirname "$0")"

# Set environment variables
export SUPABASE_URL="https://yqawmzggcgpeyaaynrjk.supabase.co"
export SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlxYXdtemdnY2dwZXlhYXlucmprIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NTAxMDkyNiwiZXhwIjoyMDcwNTg2OTI2fQ.XtLpxausFriraFJeX27ZzsdQsFv3uQKXBBggoz6P4D4"

# Run the scraper
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting scraper..." >> scraper.log
python3 main.py >> scraper.log 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Scraper completed successfully" >> scraper.log
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Scraper failed with exit code $EXIT_CODE" >> scraper_error.log
fi

exit $EXIT_CODE