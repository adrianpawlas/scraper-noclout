import requests
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ImageCompressor:
    def __init__(self, quality: int = 85):
        self.quality = quality
        self.api_url = "https://api.resmush.it/ws.php"
    
    def compress_image(self, image_url: str, max_retries: int = 3) -> Optional[str]:
        if not image_url:
            return None
        
        for attempt in range(max_retries):
            try:
                params = {
                    "img": image_url,
                    "qlty": self.quality
                }
                headers = {
                    "User-Agent": "NocloutScraper/1.0",
                    "Referer": "https://noclout.fr"
                }
                
                response = requests.get(self.api_url, params=params, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("error"):
                        logger.warning(f"reSmush.it error for {image_url}: {data.get('error')}")
                        return None
                    
                    compressed_url = data.get("dest")
                    if compressed_url:
                        logger.info(f"Compressed {image_url} -> {compressed_url}")
                        return compressed_url
                else:
                    logger.warning(f"Failed to compress {image_url}: HTTP {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error compressing {image_url}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(1)
        
        return None


async def compress_image_async(image_url: str) -> Optional[str]:
    compressor = ImageCompressor()
    return compressor.compress_image(image_url)


if __name__ == "__main__":
    test_url = "https://cdn.shopify.com/s/files/1/0654/3828/6065/files/OG_Zip_Face.jpg"
    compressor = ImageCompressor()
    result = compressor.compress_image(test_url)
    print(f"Original: {test_url}")
    print(f"Compressed: {result}")