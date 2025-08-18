from .base import BaseConfig

DEFAULT_CONFIG: BaseConfig = {
    "RETRIEVER": "tavily",
    "EMBEDDING": "openai:text-embedding-3-small",
    "SIMILARITY_THRESHOLD": 0.42,
    # Use GPT-4.1-nano for test runs (low cost, low latency)
    "FAST_LLM": "openai:gpt-4.1-nano",
    "SMART_LLM": "openai:gpt-4.1-nano",
    "STRATEGIC_LLM": "openai:gpt-4.1-nano",
    # Reduced token limits for tests to minimize cost
    "FAST_TOKEN_LIMIT": 512,
    "SMART_TOKEN_LIMIT": 1024,
    "STRATEGIC_TOKEN_LIMIT": 512,
    "BROWSE_CHUNK_MAX_LENGTH": 4096,
    "CURATE_SOURCES": False,
    "SUMMARY_TOKEN_LIMIT": 512,
    "TEMPERATURE": 0.0,  # deterministic for tests
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "MAX_SEARCH_RESULTS_PER_QUERY": 1,
    "MEMORY_BACKEND": "local",
    "TOTAL_WORDS": 200,
    "REPORT_FORMAT": "APA",
    "MAX_ITERATIONS": 1,
    "AGENT_ROLE": None,
    "SCRAPER": "bs",
    "MAX_SCRAPER_WORKERS": 1,
    "MAX_SUBTOPICS": 1,
    "LANGUAGE": "english",
    "REPORT_SOURCE": "local",  # avoid web crawling during tests
    "DOC_PATH": "./test/mdinputs",
    "PROMPT_FAMILY": "default",
    "LLM_KWARGS": {},
    "EMBEDDING_KWARGS": {},
    # Deep research specific settings (kept minimal for tests)
    "DEEP_RESEARCH_BREADTH": 1,
    "DEEP_RESEARCH_DEPTH": 1,
    "DEEP_RESEARCH_CONCURRENCY": 1,
    "REASONING_EFFORT": "low",
}
