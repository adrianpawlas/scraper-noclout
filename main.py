import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp

from scraper import get_all_product_urls, scrape_product_details
from embeddings import EmbeddingService
from supabase_client import SupabaseClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NocloutScraperOrchestrator:
    def __init__(self):
        self.embedding_service: Optional[EmbeddingService] = None
        self.supabase_client: Optional[SupabaseClient] = None
        self.stats = {
            "total_products": 0,
            "scraped": 0,
            "embedded": 0,
            "uploaded": 0,
            "errors": 0
        }

    def _init_services(self):
        if not self.embedding_service:
            logger.info("Initializing embedding service...")
            self.embedding_service = EmbeddingService()
        
        if not self.supabase_client:
            logger.info("Initializing Supabase client...")
            self.supabase_client = SupabaseClient()

    def _generate_product_id(self, url: str) -> str:
        handle = url.split('/products/')[-1].split('?')[0]
        return f"noclout-{handle[:20]}"

    def _format_price(self, price_text: str) -> str:
        if not price_text:
            return ""
        
        price_text = str(price_text).strip()
        
        match = re.search(r'([\d.,]+)', price_text)
        if match:
            amount = match.group(1).replace(',', '.')
            if "USD" in price_text.upper() or "$" in price_text:
                return f"{amount}USD"
            elif "GBP" in price_text.upper() or "£" in price_text:
                return f"{amount}GBP"
            elif "CZK" in price_text.upper():
                return f"{amount}CZK"
            elif "PLN" in price_text.upper():
                return f"{amount}PLN"
            else:
                return f"{amount}EUR"
        
        return price_text

    def _build_product_for_db(self, product_data: Dict) -> Dict:
        product_id = self._generate_product_id(product_data.get("product_url", ""))
        
        title = product_data.get("title", "")
        price = self._format_price(product_data.get("price", ""))
        sale = self._format_price(product_data.get("sale", price))
        
        metadata = {
            "name": title,
            "description": product_data.get("description", ""),
            "category": product_data.get("category", ""),
            "gender": product_data.get("gender", ""),
            "price": price,
            "sale": sale,
            "size": product_data.get("size", ""),
            "country": None,
            "brand": "Noclout",
            "source_url": product_data.get("product_url", "")
        }
        
        if product_data.get("metadata"):
            metadata["additional_info"] = product_data["metadata"]
        
        db_product = {
            "id": product_id,
            "source": "scraper-noclout",
            "brand": "Noclout",
            "product_url": product_data.get("product_url", ""),
            "affiliate_url": product_data.get("affiliate_url", ""),
            "image_url": product_data.get("image_url", ""),
            "title": title,
            "description": product_data.get("description", ""),
            "category": product_data.get("category", ""),
            "gender": None,
            "size": product_data.get("size", ""),
            "second_hand": False,
            "country": None,
            "metadata": json.dumps(metadata),
            "price": price,
            "sale": sale if sale != price else "",
            "additional_images": product_data.get("additional_images", ""),
            "created_at": datetime.utcnow().isoformat()
        }
        
        return db_product

    async def _get_image_embedding(self, image_url: str) -> List[float]:
        if not image_url:
            return [0.0] * 768
        
        try:
            return self.embedding_service.get_image_embedding(image_url)
        except Exception as e:
            logger.error(f"Error getting image embedding: {e}")
            return [0.0] * 768

    async def _get_info_embedding(self, product_data: Dict) -> List[float]:
        try:
            text_parts = []
            
            if product_data.get("title"):
                text_parts.append(product_data["title"])
            if product_data.get("description"):
                text_parts.append(product_data["description"])
            if product_data.get("category"):
                text_parts.append(product_data["category"])
            if product_data.get("gender"):
                text_parts.append(product_data["gender"])
            if product_data.get("price"):
                text_parts.append(product_data["price"])
            if product_data.get("size"):
                text_parts.append(product_data["size"])
            
            combined_text = " ".join(text_parts)
            return self.embedding_service.get_text_embedding(combined_text)
        except Exception as e:
            logger.error(f"Error getting info embedding: {e}")
            return [0.0] * 768

    async def process_single_product(self, url: str) -> Optional[Dict]:
        try:
            logger.info(f"Processing: {url}")
            
            product_data = await scrape_product_details(url)
            self.stats["scraped"] += 1
            
            db_product = self._build_product_for_db(product_data)
            
            logger.info(f"Generating embeddings for: {db_product['title']}")
            image_embedding = await self._get_image_embedding(db_product["image_url"])
            db_product["image_embedding"] = image_embedding
            
            info_embedding = await self._get_info_embedding(product_data)
            db_product["info_embedding"] = info_embedding
            
            self.stats["embedded"] += 1
            
            try:
                self.supabase_client.insert_product(db_product)
                self.stats["uploaded"] += 1
                logger.info(f"Uploaded: {db_product['title']}")
            except Exception as e:
                logger.error(f"Error uploading to DB: {e}")
                self.stats["errors"] += 1
            
            return db_product
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            self.stats["errors"] += 1
            return None

    async def run_full_scrape(self, batch_size: int = 10):
        logger.info("=" * 50)
        logger.info("Starting Noclout Scraper")
        logger.info("=" * 50)
        
        self._init_services()
        
        logger.info("Step 1: Collecting all product URLs...")
        product_urls = await get_all_product_urls()
        self.stats["total_products"] = len(product_urls)
        logger.info(f"Found {len(product_urls)} product URLs")
        
        logger.info(f"Step 2: Processing products in batches of {batch_size}...")
        
        for i in range(0, len(product_urls), batch_size):
            batch = product_urls[i:i + batch_size]
            logger.info(f"Processing batch {i // batch_size + 1}: products {i+1}-{min(i+batch_size, len(product_urls))}")
            
            tasks = [self.process_single_product(url) for url in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Batch error: {result}")
            
            await asyncio.sleep(1)
        
        logger.info("=" * 50)
        logger.info("Scraping Complete!")
        logger.info(f"Total products found: {self.stats['total_products']}")
        logger.info(f"Scraped: {self.stats['scraped']}")
        logger.info(f"Embedded: {self.stats['embedded']}")
        logger.info(f"Uploaded: {self.stats['uploaded']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("=" * 50)


async def main():
    orchestrator = NocloutScraperOrchestrator()
    await orchestrator.run_full_scrape(batch_size=5)


if __name__ == "__main__":
    asyncio.run(main())