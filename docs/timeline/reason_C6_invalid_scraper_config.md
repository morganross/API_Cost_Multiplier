# Timeline Failure Reason C6: Invalid Scraper Configuration

**Date:** November 1, 2025  
**Related Report:** `timeline_generation_failure_investigation.md`

## Description

A significant issue contributing to the incomplete timeline is an invalid scraper configuration in the `gpt-researcher` component. The default configuration specifies a scraper that is not recognized by the `Scraper` class, leading to "Scraper not found" errors for every web scraping attempt.

## Evidence

The `DEFAULT_CONFIG` in `api_cost_multiplier/gpt-researcher/gpt_researcher/config/variables/default.py` sets the default scraper to "requests":

```python
DEFAULT_CONFIG: BaseConfig = {
    ...
    "SCRAPER": "requests",
    ...
}
```

However, the `SCRAPER_CLASSES` dictionary in `api_cost_multiplier/gpt-researcher/gpt_researcher/scraper/scraper.py` does not include "requests" as a valid key:

```python
SCRAPER_CLASSES = {
    "pdf": PyMuPDFScraper,
    "arxiv": ArxivScraper,
    "bs": BeautifulSoupScraper,
    "web_base_loader": WebBaseLoaderScraper,
    "browser": BrowserScraper,
    "nodriver": NoDriverScraper,
    "tavily_extract": TavilyExtract,
    "firecrawl": FireCrawl,
}
```

This mismatch causes the `get_scraper` method to raise a "Scraper not found" exception for every web scraping attempt.

## Impact

Because the scraper is not found, no web content can be gathered for the GPT-Researcher runs. This leads to:
- Runs completing with empty or minimal content.
- Runs failing entirely due to a lack of research material.
- Missing `[GPTR_END]` entries for failed runs, which are then excluded from the timeline.

This issue is a direct cause of the "missing grounding" errors and contributes significantly to the incomplete timeline.

## Recommendations

To fix this issue, the `DEFAULT_CONFIG` in `api_cost_multiplier/gpt-researcher/gpt_researcher/config/variables/default.py` should be modified to use a valid scraper. A reasonable default would be `"bs"` (BeautifulSoupScraper) or `"tavily_extract"`. Given that "tavily" is already the default retriever, using `"tavily_extract"` for the scraper is a logical choice.

**Proposed change:**

In `api_cost_multiplier/gpt-researcher/gpt_researcher/config/variables/default.py`:

```python
# Change this:
"SCRAPER": "requests",

# To this:
"SCRAPER": "tavily_extract",
```

This change will align the default scraper with a recognized and functional option, resolving the "Scraper not found" errors and allowing GPT-Researcher runs to gather web content.
