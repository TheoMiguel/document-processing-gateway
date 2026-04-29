import asyncio
from typing import Any


class FastExtractor:
    async def extract(self, content: str, document_type: str) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        words = content.split()
        return {
            "text": content,
            "word_count": len(words),
            "document_type": document_type,
            "language": "en",
        }


class SlowExtractor:
    async def extract(self, content: str, document_type: str) -> dict[str, Any]:
        await asyncio.sleep(2.0)
        words = content.split()
        return {
            "text": content,
            "word_count": len(words),
            "document_type": document_type,
            "language": "en",
        }
