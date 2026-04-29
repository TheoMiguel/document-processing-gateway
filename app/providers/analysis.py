import asyncio
from typing import Any


class FastAnalyzer:
    async def analyze(self, extracted: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        word_count = extracted.get("word_count", 0)
        return {
            "sentiment": "neutral",
            "score": 0.5,
            "complexity": "high" if word_count > 500 else "medium" if word_count > 100 else "low",
            "key_topics": [],
        }


class SlowAnalyzer:
    async def analyze(self, extracted: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(2.0)
        word_count = extracted.get("word_count", 0)
        return {
            "sentiment": "neutral",
            "score": 0.5,
            "complexity": "high" if word_count > 500 else "medium" if word_count > 100 else "low",
            "key_topics": [],
        }
