import asyncio
import aiohttp
import ssl
import json
import logging
from typing import List, Optional
from playwright.async_api import async_playwright, Browser, Page

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ShopifyAPI:
    def __init__(self, domain: str = "noclout.fr"):
        self.domain = domain
        self.base_url = f"https://{domain}"
        self.api_url = f"https://{domain}/products"
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE
        self._connector = aiohttp.TCPConnector(ssl=self._ssl_context)
    
    async def fetch_product_json(self, product_handle: str, max_retries: int = 5) -> Optional[dict]:
        url = f"{self.api_url}/{product_handle}.json"
        for attempt in range(max_retries):
            try:
                await asyncio.sleep(1 + attempt * 0.5)
                async with aiohttp.ClientSession(connector=self._connector) as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            data = await response.json()
                            return data.get('product')
                        elif response.status == 403:
                            wait_time = 2 ** attempt
                            logger.warning(f"Rate limited on {url}, waiting {wait_time}s (attempt {attempt+1}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.warning(f"Failed to fetch {url}: {response.status}")
                            return None
            except Exception as e:
                logger.error(f"Error fetching {url}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
        return None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class CollectionScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

    async def scroll_and_collect_products(self, url: str, max_scrolls: int = 50) -> List[str]:
        logger.info(f"Loading collection page: {url}")
        await self.page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)

        product_urls = set()
        last_height = 0
        scroll_count = 0
        no_new_products_count = 0

        while scroll_count < max_scrolls:
            product_links = await self.page.query_selector_all("a[href*='/products/']")
            for link in product_links:
                href = await link.get_attribute("href")
                if href and '/products/' in href:
                    full_url = href if href.startswith('http') else f"https://noclout.fr{href}"
                    product_urls.add(full_url)

            logger.info(f"Found {len(product_urls)} unique product URLs so far")

            current_height = await self.page.evaluate("document.body.scrollHeight")
            if current_height == last_height:
                no_new_products_count += 1
                if no_new_products_count >= 3:
                    logger.info("No more content to scroll - reached end of page")
                    break
            else:
                no_new_products_count = 0

            last_height = current_height
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            scroll_count += 1

        logger.info(f"Total collected: {len(product_urls)} product URLs")
        return list(product_urls)


def normalize_url(url: str) -> str:
    if not url:
        return url
    url = url.split("?")[0]
    if url.startswith("//"):
        url = "https:" + url
    return url


def format_price(price: str, compare_at: str = None) -> tuple:
    import re
    price = price.strip() if price else ""
    compare_at = compare_at.strip() if compare_at else ""
    
    def extract_amount_curr(txt):
        if not txt:
            return "", ""
        match = re.search(r'([\d.,]+)\s*(EUR|USD|GBP|CZK|PLN|€|\$|£)?', txt.upper())
        if match:
            amount = match.group(1).replace(',', '.')
            curr = match.group(2) or 'EUR'
            curr = curr.replace('€', 'EUR').replace('$', 'USD').replace('£', 'GBP')
            return amount, curr
        return "", ""
    
    amt1, curr1 = extract_amount_curr(price)
    amt2, curr2 = extract_amount_curr(compare_at)
    
    # Price = current price (sale price if on sale), Sale = original price
    if amt2:  # There's a compare_at price (on sale)
        return f"{amt1}{curr1}" if amt1 else "", f"{amt2}{curr2}" if amt2 else ""
    else:  # Not on sale
        return f"{amt1}{curr1}" if amt1 else "", ""


async def scrape_product(handle: str) -> Optional[dict]:
    api = ShopifyAPI()
    product_json = await api.fetch_product_json(handle)
    
    if not product_json:
        return None
    
    product = {
        "source": "scraper-noclout",
        "brand": "Noclout",
        "product_url": f"https://noclout.fr/products/{handle}",
        "affiliate_url": f"https://noclout.fr/products/{handle}?ref=THEFINDSAPP",
        "title": product_json.get('title', ''),
        "description": product_json.get('body_html', ''),
        "category": "",
        "gender": "",
        "price": "",
        "sale": "",
        "image_url": "",
        "additional_images": "",
        "metadata": "",
        "size": "",
        "second_hand": False,
        "country": None
    }
    
    images = product_json.get('images', [])
    if images:
        product["image_url"] = normalize_url(images[0]['src'])
        additional = [normalize_url(img['src']) for img in images[1:6]]
        product["additional_images"] = " , ".join(additional)
    
    variants = product_json.get('variants', [])
    if variants:
        variant = variants[0]
        price = variant.get('price', '')
        compare_at = variant.get('compare_at_price', '')
        product["price"], product["sale"] = format_price(price, compare_at)
        
        option1 = variant.get('option1', '')
        option2 = variant.get('option2', '')
        option3 = variant.get('option3', '')
        sizes = [o for o in [option1, option2, option3] if o and o.upper() not in ['NFC', 'WHITE', 'BLUE', 'BLACK']]
        product["size"] = ", ".join(sizes)
    
    tags = product_json.get('tags', [])
    if tags:
        categories = []
        for tag in tags:
            if any(w in tag.lower() for w in ['hoodie', 'tee', 'pant', 'jacket', 'sweater', 'short', 'cap', 'shirt', 'zip', 'knit', 'pant', 'short', 'waffle']):
                categories.append(tag)
        product["category"] = ", ".join(categories) if categories else "Clothing"
        
        if any(w in ' '.join(tags).lower() for w in ['woman', 'women', 'female', 'dame', 'femme']):
            product["gender"] = "woman"
    
    product_type = product_json.get('product_type', '')
    if product_type and product_type not in product["category"]:
        product["category"] = product_type if not product["category"] else f"{product['category']}, {product_type}"
    
    import re
    desc_clean = re.sub(r'<[^>]+>', '', product.get('description', ''))
    desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
    product["description"] = desc_clean[:500]
    
    metadata = {
        "name": product["title"],
        "description": desc_clean,
        "category": product["category"],
        "gender": product["gender"],
        "price": product["price"],
        "sale": product["sale"],
        "size": product["size"],
        "country": None,
        "brand": "Noclout",
        "product_type": product_type,
        "tags": tags
    }
    product["metadata"] = json.dumps(metadata)
    
    logger.info(f"Scraped: {product['title']} - {product['price']}")
    return product


async def get_all_product_urls() -> List[str]:
    import ssl
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        urls = set()
        page = 1
        while page <= 20:  # Max 20 pages
            try:
                url = "https://noclout.fr/collections/tous-les-articles"
                async with session.get(url, params={"page": page}, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        break
                    
                    from bs4 import BeautifulSoup
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    links = soup.find_all('a', href=True)
                    found_on_page = 0
                    for link in links:
                        href = link['href']
                        if '/products/' in href:
                            if not href.startswith('http'):
                                href = f"https://noclout.fr{href}"
                            # Remove query params
                            href = href.split('?')[0]
                            if href not in urls:
                                urls.add(href)
                                found_on_page += 1
                    
                    if found_on_page == 0:
                        break
                    logger.info(f"Page {page}: found {found_on_page} products (total: {len(urls)})")
                    page += 1
            except Exception as e:
                logger.error(f"Error fetching collection page {page}: {e}")
                break
        
        result = list(urls)
        logger.info(f"Found {len(result)} unique product URLs")
        return result


async def scrape_product_details(url: str) -> dict:
    handle = url.split('/products/')[-1].split('?')[0]
    return await scrape_product(handle)


if __name__ == "__main__":
    async def test():
        urls = await get_all_product_urls()
        print(f"Found {len(urls)} product URLs")
        if urls:
            product = await scrape_product_details(urls[0])
            print(product)
    
    asyncio.run(test())