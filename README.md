# gptr-eval-process


the root/main script starts the process markdown script, and gets the files from process markdown

the main script then sends those files to eval

the main scirpt then writes that file to the correct location

the input folder and output folder are specifyed by a config file

THE PROCESS-MARKDOWN script is repsonsible for getting the query together, sending it to gpt-R and obtaining its results

the process markdown FOLDER contains the process markdown script and a config file AND a seperate file that contains the logic for creating output files and dir, becuase we use it from differnt places.

This project serves as a central orchestrator for integrating and managing workflows involving:
- `gpt-researcher`: For generating research reports.
- `llm-doc-eval`: For evaluating documents.
- `process_markdown`: A new module for markdown processing utilities.
- `review-revise`: A module for future review and revision functionalities.

All project dependencies are managed in the central `requirements.txt` file located in this root directory.

## Configuration Files

Key configuration files within this project include:

*   [`gptr-eval-process/llm-doc-eval/config.yaml`](gptr-eval-process/llm-doc-eval/config.yaml)
*   [`gptr-eval-process/llm-doc-eval/criteria.yaml`](gptr-eval-process/llm-doc-eval/criteria.yaml)
*   [`gptr-eval-process/gpt-researcher/.env.example`](gptr-eval-process/gpt-researcher/.env.example)
*   [`gptr-eval-process/gpt-researcher/gpt_researcher/config/variables/default.py`](gptr-eval-process/gpt-researcher/gpt_researcher/config/variables/default.py)
*   [`gptr-eval-process/process_markdown/config.md`](gptr-eval-process/process_markdown/config.md)

also the multi agent config in task.json

## Documentation

For more detailed information, please refer to the following documentation files:

*   [`gptr-eval-process/README.md`](gptr-eval-process/README.md) (Main project README)(this file)
*   [`gptr-eval-process/process-markdown/Readme-process-markdown.md`](gptr-eval-process/process-markdown/Readme-process-markdown.md) (Main project README)(this file)
*   [`gptr-eval-process/gpt-researcher/README.md`](gptr-eval-process/gpt-researcher/README.md) (GPT-Researcher project README)
*   [`gptr-eval-process/llm-doc-eval/README.md`](gptr-eval-process/llm-doc-eval/README.md) (LLM-Doc-Eval project README)



*   [`gptr-eval-process/gpt-researcher/backend/report_type/deep_research/README.md`](gptr-eval-process/gpt-researcher/backend/report_type/deep_research/README.md)
*   [`gptr-eval-process/gpt-researcher/backend/report_type/detailed_report/README.md`](gptr-eval-process/gpt-researcher/backend/report_type/detailed_report/README.md)



*   [`gptr-eval-process/gpt-researcher/docs/docs/welcome.md`](gptr-eval-process/gpt-researcher/docs/docs/welcome.md)


*   [`gptr-eval-process/gpt-researcher/docs/docs/contribute.md`](gptr-eval-process/gpt-researcher/docs/docs/contribute.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/examples/detailed_report.md`](gptr-eval-process/gpt-researcher/docs/docs/examples/detailed_report.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/examples/examples.md`](gptr-eval-process/gpt-researcher/docs/docs/examples/examples.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/examples/hybrid_research.md`](gptr-eval-process/gpt-researcher/docs/docs/examples/hybrid_research.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/faq.md`](gptr-eval-process/gpt-researcher/docs/docs/faq.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/azure-storage.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/azure-storage.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/data-ingestion.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/data-ingestion.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/filtering-by-domain.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/filtering-by-domain.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/local-docs.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/local-docs.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/tailored-research.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/context/tailored-research.md)
gpt-researcher/frontend/discord-bot.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/querying-the-backend.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/querying-the-backend.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/cli.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/cli.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/getting-started.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/getting-started.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/how-to-choose.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/how-to-choose.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/introduction.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/introduction.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/linux-deployment.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/getting-started/linux-deployment.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/automated-tests.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/automated-tests.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/config.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/config.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/deep_research.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/deep_research.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/example.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/example.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/npm-package.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/npm-package.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/pip-package.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/pip-package.md)

*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/scraping.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/scraping.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/troubleshooting.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/gptr/troubleshooting.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/handling-logs/all-about-logs.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/handling-logs/all-about-logs.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/handling-logs/langsmith-logs.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/handling-logs/langsmith-logs.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/handling-logs/simple-logs-example.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/handling-logs/simple-logs-example.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/llms.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/llms.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/running-with-azure.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/running-with-azure.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/running-with-ollama.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/running-with-ollama.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/supported-llms.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/supported-llms.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/testing-your-llm.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/llms/testing-your-llm.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/multi_agents/langgraph.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/multi_agents/langgraph.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/search-engines/retrievers.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/search-engines/retrievers.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/search-engines/test-your-retriever.md`](gptr-eval-process/gpt-researcher/docs/docs/gpt-researcher/search-engines/test-your-retriever.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/reference/config/config.md`](gptr-eval-process/gpt-researcher/docs/docs/reference/config/config.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/reference/config/singleton.md`](gptr-eval-process/gpt-researcher/docs/docs/reference/config/singleton.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/reference/processing/html.md`](gptr-eval-process/gpt-researcher/docs/docs/reference/processing/html.md)
*   [`gptr-eval-process/gpt-researcher/docs/docs/reference/processing/text.md`](gptr-eval-process/gpt-researcher/docs/docs/reference/processing/text.md)

