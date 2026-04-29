from typing import Any, Protocol


class ExtractionProvider(Protocol):
    async def extract(self, content: str, document_type: str) -> dict[str, Any]: ...


class AnalysisProvider(Protocol):
    async def analyze(self, extracted: dict[str, Any]) -> dict[str, Any]: ...


class EnrichmentProvider(Protocol):
    async def enrich(
        self, extracted: dict[str, Any], analyzed: dict[str, Any]
    ) -> dict[str, Any]: ...
