import asyncio
import logging
from supabase_client import SupabaseClient
from image_compressor import ImageCompressor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def compress_all_images(batch_size: int = 10):
    client = SupabaseClient()
    compressor = ImageCompressor(quality=85)
    
    logger.info("Fetching all products with image_url...")
    result = client.client.table("products").select(
        "id, image_url, compressed_image_url"
    ).eq("source", "scraper-noclout").execute()
    
    products = result.data
    logger.info(f"Found {len(products)} products")
    
    compressed_count = 0
    skipped_count = 0
    error_count = 0
    
    for i, product in enumerate(products):
        if product.get("compressed_image_url"):
            logger.info(f"Skipping {product['id']} - already compressed")
            skipped_count += 1
            continue
        
        image_url = product.get("image_url")
        if not image_url:
            logger.warning(f"No image_url for {product['id']}")
            skipped_count += 1
            continue
        
        logger.info(f"Compressing {i+1}/{len(products)}: {product['id']}")
        
        compressed_url = compressor.compress_image(image_url)
        
        if compressed_url:
            try:
                client.client.table("products").update(
                    {"compressed_image_url": compressed_url}
                ).eq("id", product["id"]).execute()
                compressed_count += 1
                logger.info(f"Updated {product['id']} with compressed URL")
            except Exception as e:
                logger.error(f"Error updating {product['id']}: {e}")
                error_count += 1
        else:
            error_count += 1
        
        await asyncio.sleep(0.5)
    
    logger.info("=" * 50)
    logger.info(f"Compression complete!")
    logger.info(f"Compressed: {compressed_count}")
    logger.info(f"Skipped: {skipped_count}")
    logger.info(f"Errors: {error_count}")
    logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(compress_all_images())