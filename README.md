# Noclout Scraper

Automated scraper for Noclout fashion store (https://noclout.fr) that collects products and imports them to Supabase with embeddings.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Configure environment:
Copy `.env.example` to `.env` and add your Supabase credentials:
```
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
```

## Usage

### Run scraper manually:
```bash
python main.py
```

### Automated (cron - macOS/Linux):
```bash
crontab -e
# Add: 0 0 * * * /path/to/python /path/to/main.py
```

### Automated (launchd - macOS):
```bash
# Create ~/Library/LaunchAgents/com.scraper.noclout.plist
launchctl load ~/Library/LaunchAgents/com.scraper.noclout.plist
```

## Features

- Collects all products from Noclout collection pages
- Uses Playwright for infinite scroll detection
- Shopify API for product details
- Siglip-base-patch16-384 for 768-dim embeddings
- Supabase database with vector search support

## Files

- `scraper.py` - Collection & product scraping
- `embeddings.py` - Image & text embedding generation
- `supabase_client.py` - Database operations
- `main.py` - Orchestrator