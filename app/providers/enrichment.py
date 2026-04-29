import asyncio
from typing import Any


class FastEnricher:
    async def enrich(self, extracted: dict[str, Any], analyzed: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "entities": [],
            "categories": [extracted.get("document_type", "unknown")],
            "confidence": analyzed.get("score", 0.0),
            "tags": [],
        }


class SlowEnricher:
    async def enrich(self, extracted: dict[str, Any], analyzed: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(2.0)
        return {
            "entities": [],
            "categories": [extracted.get("document_type", "unknown")],
            "confidence": analyzed.get("score", 0.0),
            "tags": [],
        }
