import torch
from PIL import Image
import requests
from io import BytesIO
from typing import List
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, model_name: str = "google/siglip-base-patch16-384"):
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading model {model_name} on {self.device}")
        
        from transformers import SiglipModel, SiglipProcessor
        self.model = SiglipModel.from_pretrained(model_name).to(self.device)
        self.processor = SiglipProcessor.from_pretrained(model_name)
        logger.info("Model loaded successfully")

    def get_image_embedding(self, image_url: str) -> List[float]:
        try:
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")
            
            inputs = self.processor(images=image, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.get_image_features(**inputs)
                embedding = outputs.pooler_output.detach().cpu().numpy().flatten().tolist()
            
            return embedding
        except Exception as e:
            logger.error(f"Error getting image embedding for {image_url}: {e}")
            return [0.0] * 768

    def get_text_embedding(self, text: str) -> List[float]:
        try:
            text = text[:200]  # Truncate to avoid max length issues
            inputs = self.processor(text=text, return_tensors="pt", truncation=True, max_length=64)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.get_text_features(**inputs)
                embedding = outputs.pooler_output.detach().cpu().numpy().flatten().tolist()
            
            return embedding
        except Exception as e:
            logger.error(f"Error getting text embedding: {e}")
            return [0.0] * 768

    def get_combined_text_embedding(self, product_data: dict) -> List[float]:
        text_parts = []
        
        if product_data.get("title"):
            text_parts.append(f"Title: {product_data['title']}")
        if product_data.get("description"):
            text_parts.append(f"Description: {product_data['description']}")
        if product_data.get("category"):
            text_parts.append(f"Category: {product_data['category']}")
        if product_data.get("gender"):
            text_parts.append(f"Gender: {product_data['gender']}")
        if product_data.get("price"):
            text_parts.append(f"Price: {product_data['price']}")
        if product_data.get("metadata"):
            text_parts.append(f"Details: {product_data['metadata']}")
        if product_data.get("size"):
            text_parts.append(f"Sizes: {product_data['size']}")
        
        combined_text = " ".join(text_parts)
        
        try:
            inputs = self.processor(text=combined_text, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.model.get_text_features(**inputs)
                embedding = outputs.pooler_output.detach().cpu().numpy().flatten().tolist()
            
            return embedding
        except Exception as e:
            logger.error(f"Error getting combined text embedding: {e}")
            return [0.0] * 768


async def get_image_embedding_async(image_url: str) -> List[float]:
    service = EmbeddingService()
    return service.get_image_embedding(image_url)


async def get_text_embedding_async(text: str) -> List[float]:
    service = EmbeddingService()
    return service.get_text_embedding(text)


if __name__ == "__main__":
    import asyncio
    
    async def test():
        service = EmbeddingService()
        
        test_url = "https://cdn.shopify.com/s/files/1/0654/3828/6065/files/OG_Zip_Face.jpg"
        emb = service.get_image_embedding(test_url)
        print(f"Image embedding length: {len(emb)}")
        
        text_emb = service.get_text_embedding("Noclout OG Zip blue hoodie")
        print(f"Text embedding length: {len(text_emb)}")
    
    asyncio.run(test())