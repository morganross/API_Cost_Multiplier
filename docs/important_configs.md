# Important Configs

This document lists the project's most important configuration files, environment variables

these list the values that will be configurable from the gui

the gui will edit the config files.



## Key config files (locations relative to repository root)
- `process_markdown/config.yaml`
- `process_markdown/FilePromptForge/default_config.yaml`
- `process_markdown/gpt-researcher/config/variables/default.py` 
- `process_markdown/gpt-researcher/multi)agent/task.json`
- `process_markdown/.env`

## Key config files (locations relative to repository root)
- `process_markdown/config.yaml`
ALL
- `process_markdown/FilePromptForge/default_config.yaml`
grounding:enabled
grounding:max results
provider
google:max tokens
- `process_markdown/gpt-researcher/config/variables/default.py` 
    "RETRIEVER": "tavily",
    "FAST_LLM": 
    "SMART_LLM": 
    "STRATEGIC_LLM": 
    "FAST_TOKEN_LIMIT": 300,
    "SMART_TOKEN_LIMIT": 600,
    "STRATEGIC_TOKEN_LIMIT": 400,
    "BROWSE_CHUNK_MAX_LENGTH": 892,
    "SUMMARY_TOKEN_LIMIT": 700,
    "TEMPERATURE": 0.4,
    "MAX_SEARCH_RESULTS_PER_QUERY": 5,
    "TOTAL_WORDS": 100,
    "REPORT_FORMAT": "APA",
    "MAX_ITERATIONS": 1,
    "MAX_SCRAPER_WORKERS": 3,
    "MAX_SUBTOPICS": 1,
    "DEEP_RESEARCH_BREADTH": 1,
    "DEEP_RESEARCH_DEPTH": 1,
    "DEEP_RESEARCH_CONCURRENCY": 1,
    "REASONING_EFFORT": "low",
- `process_markdown/gpt-researcher/multi)agent/task.json`
  "max_sections"
  model
- `process_markdown/.env`



GUI SLIDER SECTION:
WE NEED A SLIDER FOR EACH OF THE FOLLOWING

- `process_markdown/config.yaml`
iterations
- `process_markdown/FilePromptForge/default_config.yaml`

grounding:max results

google:max tokens
- `process_markdown/gpt-researcher/config/variables/default.py` 


    "FAST_TOKEN_LIMIT": 300,
    "SMART_TOKEN_LIMIT": 600,
    "STRATEGIC_TOKEN_LIMIT": 400,
    "BROWSE_CHUNK_MAX_LENGTH": 892,
    "SUMMARY_TOKEN_LIMIT": 700,
    "TEMPERATURE": 0.4,
    "MAX_SEARCH_RESULTS_PER_QUERY": 5,
    "TOTAL_WORDS": 100,

    "MAX_ITERATIONS": 1,
    "MAX_SCRAPER_WORKERS": 3,
    "MAX_SUBTOPICS": 1,
    "DEEP_RESEARCH_BREADTH": 1,
    "DEEP_RESEARCH_DEPTH": 1,
    "DEEP_RESEARCH_CONCURRENCY": 1,
    "REASONING_EFFORT": "low",
- `process_markdown/gpt-researcher/multi)agent/task.json`
  "max_sections"

