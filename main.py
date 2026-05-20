import asyncio
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import List, Dict, Optional, Set
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
    def __init__(self, batch_size: int = 50):
        self.embedding_service: Optional[EmbeddingService] = None
        self.supabase_client: Optional[SupabaseClient] = None
        self.batch_size = batch_size
        self.stats = {
            "new_products": 0,
            "products_updated": 0,
            "products_unchanged": 0,
            "products_deleted": 0,
            "errors": 0
        }
        self.seen_product_urls: Set[str] = set()
        self.previous_product_urls: Set[str] = set()
        self.existing_products: Dict[str, dict] = {}

    def _init_services(self):
        if not self.embedding_service:
            logger.info("Initializing embedding service...")
            self.embedding_service = EmbeddingService()
        
        if not self.supabase_client:
            logger.info("Initializing Supabase client...")
            self.supabase_client = SupabaseClient()
            self._load_previous_products()

    def _load_previous_products(self):
        logger.info("Loading existing products from database...")
        result = self.supabase_client.client.table("products").select(
            "product_url, title, price, sale, image_url, additional_images, metadata"
        ).eq("source", "scraper-noclout").execute()
        
        for p in result.data:
            self.previous_product_urls.add(p["product_url"])
            self.existing_products[p["product_url"]] = p
        
        logger.info(f"Loaded {len(self.existing_products)} existing products")

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

    def _check_product_changed(self, scraped: dict, existing: dict) -> bool:
        if not existing:
            return True
        
        if scraped.get("title") != existing.get("title"):
            return True
        if scraped.get("price") != existing.get("price"):
            return True
        if scraped.get("sale") != existing.get("sale"):
            return True
        if scraped.get("image_url") != existing.get("image_url"):
            return True
        if scraped.get("additional_images") != existing.get("additional_images"):
            return True
        
        scraped_meta = json.loads(scraped.get("metadata", "{}")) if scraped.get("metadata") else {}
        existing_meta = existing.get("metadata")
        if isinstance(existing_meta, str):
            existing_meta = json.loads(existing_meta)
        
        if scraped_meta.get("description") != existing_meta.get("description"):
            return True
        
        return False

    def _build_product_for_db(self, product_data: Dict, regenerate_embeddings: bool = False) -> Dict:
        product_url = product_data.get("product_url", "")
        product_id = self._generate_product_id(product_url)
        
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
            "source_url": product_url
        }
        
        if product_data.get("metadata"):
            metadata["additional_info"] = product_data["metadata"]
        
        db_product = {
            "id": product_id,
            "source": "scraper-noclout",
            "product_url": product_url,
            "brand": "Noclout",
            "affiliate_url": product_data.get("affiliate_url", "https://noclout.fr/THEFINDSAPP"),
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
            "additional_images": product_data.get("additional_images", "")
        }
        
        if regenerate_embeddings:
            db_product["image_embedding"] = [0.0] * 768
            db_product["info_embedding"] = [0.0] * 768
        
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
            if product_data.get("price"):
                text_parts.append(product_data["price"])
            if product_data.get("size"):
                text_parts.append(product_data["size"])
            
            combined_text = " ".join(text_parts)
            await asyncio.sleep(0.5)  # Stagger API calls
            return self.embedding_service.get_text_embedding(combined_text)
        except Exception as e:
            logger.error(f"Error getting info embedding: {e}")
            return [0.0] * 768

    def _insert_batch_with_retry(self, products: List[dict], max_retries: int = 3) -> tuple:
        for attempt in range(max_retries):
            try:
                result = self.supabase_client.insert_products_batch(products)
                return len(products), 0
            except Exception as e:
                logger.warning(f"Batch insert attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    failed_log = f"Failed products: {[p.get('product_url', p.get('id')) for p in products]}\nError: {e}\n"
                    with open("failed_products.log", "a") as f:
                        f.write(f"{datetime.now().isoformat()} - {failed_log}")
                    return 0, len(products)
                time.sleep(1)
        return 0, len(products)

    async def process_single_product(self, url: str) -> Optional[Dict]:
        try:
            logger.info(f"Processing: {url}")
            
            product_data = await scrape_product_details(url)
            self.seen_product_urls.add(url)
            
            existing = self.existing_products.get(url)
            is_new = existing is None
            has_changed = self._check_product_changed(product_data, existing)
            
            if is_new:
                self.stats["new_products"] += 1
                regenerate_embeddings = True
            elif has_changed:
                self.stats["products_updated"] += 1
                existing_image = existing.get("image_url", "") if existing else ""
                regenerate_embeddings = product_data.get("image_url") != existing_image
            else:
                self.stats["products_unchanged"] += 1
                return None
            
            db_product = self._build_product_for_db(product_data, regenerate_embeddings=regenerate_embeddings)
            
            if regenerate_embeddings:
                logger.info(f"Regenerating embeddings for: {db_product['title']}")
                db_product["image_embedding"] = await self._get_image_embedding(db_product["image_url"])
                await asyncio.sleep(0.5)
                db_product["info_embedding"] = await self._get_info_embedding(product_data)
            
            return db_product
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            self.stats["errors"] += 1
            return None

    async def run_full_scrape(self, batch_size: int = 50):
        self.batch_size = batch_size
        logger.info("=" * 50)
        logger.info("Starting Noclout Scraper")
        logger.info("=" * 50)
        
        self._init_services()
        
        logger.info("Step 1: Collecting all product URLs...")
        product_urls = await get_all_product_urls()
        logger.info(f"Found {len(product_urls)} product URLs")
        
        logger.info(f"Step 2: Processing products in batches of {batch_size}...")
        
        batch = []
        for url in product_urls:
            product = await self.process_single_product(url)
            if product:
                batch.append(product)
            
            await asyncio.sleep(1.5)
            
            if len(batch) >= batch_size:
                inserted, failed = self._insert_batch_with_retry(batch)
                batch = []
                await asyncio.sleep(2)
        
        if batch:
            inserted, failed = self._insert_batch_with_retry(batch)
        
        logger.info("Step 3: Cleaning up stale products...")
        stale_products = self.previous_product_urls - self.seen_product_urls
        
        if stale_products:
            logger.info(f"Found {len(stale_products)} stale products from previous run")
            
            result = self.supabase_client.client.table("products").select(
                "id, product_url"
            ).eq("source", "scraper-noclout").execute()
            
            all_current_urls = set(p["product_url"] for p in result.data)
            
            truly_stale = self.previous_product_urls - all_current_urls
            
            if truly_stale:
                logger.info(f"Deleting {len(truly_stale)} stale products...")
                for url in list(truly_stale):
                    product_id = self._generate_product_id(url)
                    try:
                        self.supabase_client.client.table("products").delete().eq("id", product_id).execute()
                        self.stats["products_deleted"] += 1
                    except Exception as e:
                        logger.error(f"Error deleting {product_id}: {e}")
        
        logger.info("=" * 50)
        logger.info("Scraping Complete!")
        logger.info(f"New products added: {self.stats['new_products']}")
        logger.info(f"Products updated: {self.stats['products_updated']}")
        logger.info(f"Products unchanged (skipped): {self.stats['products_unchanged']}")
        logger.info(f"Stale products deleted: {self.stats['products_deleted']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("=" * 50)


async def main():
    orchestrator = NocloutScraperOrchestrator(batch_size=50)
    await orchestrator.run_full_scrape(batch_size=50)


if __name__ == "__main__":
    asyncio.run(main())