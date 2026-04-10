import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)
load_dotenv()


class SupabaseClient:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
        
        self.client: Client = create_client(self.url, self.key)
        logger.info("Supabase client initialized")

    def insert_product(self, product_data: dict) -> dict:
        product_data["created_at"] = "now()"
        
        if product_data.get("metadata") and isinstance(product_data["metadata"], dict):
            product_data["metadata"] = json.dumps(product_data["metadata"])
        
        if product_data.get("additional_images"):
            if isinstance(product_data["additional_images"], list):
                product_data["additional_images"] = " , ".join(product_data["additional_images"])
        
        if "search_vector" in product_data:
            del product_data["search_vector"]
        
        try:
            result = self.client.table("products").upsert(
                product_data,
                on_conflict="id"
            ).execute()
            logger.info(f"Upserted product: {product_data.get('title')}")
            return result
        except Exception as e:
            logger.error(f"Error upserting product: {e}")
            raise

    def insert_products_batch(self, products: list) -> dict:
        for product in products:
            if product.get("metadata") and isinstance(product["metadata"], dict):
                product["metadata"] = json.dumps(product["metadata"])
            
            if product.get("additional_images"):
                if isinstance(product["additional_images"], list):
                    product["additional_images"] = " , ".join(product["additional_images"])
            
            if "search_vector" in product:
                del product["search_vector"]
        
        try:
            result = self.client.table("products").upsert(
                products,
                on_conflict="source,product_url"
            ).execute()
            logger.info(f"Upserted {len(products)} products")
            return result
        except Exception as e:
            logger.error(f"Error upserting products: {e}")
            raise

    def check_product_exists(self, source: str, product_url: str) -> bool:
        try:
            result = self.client.table("products").select("id").eq("source", source).eq("product_url", product_url).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Error checking product existence: {e}")
            return False


async def insert_product_to_db(product_data: dict) -> dict:
    client = SupabaseClient()
    return client.insert_product(product_data)


async def insert_products_batch_to_db(products: list) -> dict:
    client = SupabaseClient()
    return client.insert_products_batch(products)


if __name__ == "__main__":
    test_product = {
        "id": "test-noclout-001",
        "source": "scraper-noclout",
        "brand": "Noclout",
        "product_url": "https://noclout.fr/products/test",
        "title": "Test Product",
        "image_url": "https://example.com/image.jpg",
        "price": "89.99EUR",
        "gender": "man",
        "second_hand": False,
        "country": None
    }
    
    client = SupabaseClient()
    result = client.insert_product(test_product)
    print(result)