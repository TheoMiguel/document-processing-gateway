from unittest.mock import AsyncMock

import pytest

from app.providers.analysis import FastAnalyzer, SlowAnalyzer
from app.providers.enrichment import FastEnricher, SlowEnricher
from app.providers.extraction import FastExtractor, SlowExtractor

EXTRACTION_KEYS = {"text", "word_count", "document_type", "language"}
ANALYSIS_KEYS = {"sentiment", "score", "complexity", "key_topics"}
ENRICHMENT_KEYS = {"entities", "categories", "confidence", "tags"}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", AsyncMock())


async def test_fast_extractor_shape():
    result = await FastExtractor().extract("hello world", "pdf")
    assert set(result.keys()) == EXTRACTION_KEYS
    assert result["word_count"] == 2
    assert result["document_type"] == "pdf"
    assert result["text"] == "hello world"


async def test_slow_extractor_same_shape():
    result = await SlowExtractor().extract("one two three", "txt")
    assert set(result.keys()) == EXTRACTION_KEYS
    assert result["word_count"] == 3


async def test_fast_analyzer_low_complexity():
    result = await FastAnalyzer().analyze({"word_count": 10})
    assert set(result.keys()) == ANALYSIS_KEYS
    assert result["complexity"] == "low"


async def test_fast_analyzer_medium_complexity():
    result = await FastAnalyzer().analyze({"word_count": 150})
    assert result["complexity"] == "medium"


async def test_fast_analyzer_high_complexity():
    result = await FastAnalyzer().analyze({"word_count": 600})
    assert result["complexity"] == "high"


async def test_slow_analyzer_same_shape():
    result = await SlowAnalyzer().analyze({"word_count": 50})
    assert set(result.keys()) == ANALYSIS_KEYS


async def test_fast_enricher_shape():
    result = await FastEnricher().enrich({"document_type": "pdf"}, {"score": 0.9})
    assert set(result.keys()) == ENRICHMENT_KEYS
    assert "pdf" in result["categories"]
    assert result["confidence"] == 0.9


async def test_fast_enricher_missing_inputs():
    result = await FastEnricher().enrich({}, {})
    assert set(result.keys()) == ENRICHMENT_KEYS
    assert result["confidence"] == 0.0


async def test_slow_enricher_same_shape():
    result = await SlowEnricher().enrich({"document_type": "txt"}, {"score": 0.5})
    assert set(result.keys()) == ENRICHMENT_KEYS
    assert result["confidence"] == 0.5
