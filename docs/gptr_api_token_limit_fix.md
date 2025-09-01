# GPT-Researcher: API Token Limit Exceeded Error

## Issue: `Requested X tokens, max Y tokens per request`

During the execution of `python API_Cost_Multiplier\generate.py`, errors related to API token limits were observed, specifically:

```
Error code: 400 - {'error': {'message': 'Requested 378510 tokens, max 300000 tokens per request', 'type': 'max_tokens_per_request', 'param': None, 'code': 'max_tokens_per_request'}}
```

This error indicates that the `gpt-researcher` component is attempting to send a request to the Large Language Model (LLM) API (likely OpenAI's embeddings API, given the traceback) with a payload exceeding the maximum allowed token limit per request. In this specific instance, the request was for 378,510 tokens, while the limit was 300,000 tokens.

The traceback points to the `gpt_researcher\skills\researcher.py`, `gpt_researcher\context\compression.py`, and `langchain_openai\embeddings\base.py` modules, indicating that the issue arises during the context compression and embedding generation phase within GPT-Researcher.

## Solution and Next Steps

To resolve this issue, the core problem is managing the volume of information passed to the LLM's embedding service. My investigation revealed that `gpt-researcher` utilizes `RecursiveCharacterTextSplitter` to break down documents into chunks (defaulting to 1000 characters) before sending them for embedding. Although chunks are created, the `langchain_openai` library might still combine these chunks into requests that exceed the model's token limit.

The `EMBEDDING_KWARGS` parameter in `API_Cost_Multiplier/gpt-researcher/gpt_researcher/config/variables/default.py` allows passing additional arguments directly to the embedding model initialization. The `langchain-openai` library's `OpenAIEmbeddings` class accepts a `chunk_size` parameter, which controls the number of input texts to embed in a single batch.

**Action Taken:**

I have modified `API_Cost_Multiplier/gpt-researcher/gpt_researcher/config/variables/default.py` to explicitly set `chunk_size` within `EMBEDDING_KWARGS`. This will instruct the embedding model to process content in smaller batches, preventing individual requests from exceeding the token limit.

**Change Implemented:**

```python
# Before:
# "EMBEDDING_KWARGS": {},

# After:
"EMBEDDING_KWARGS": {"chunk_size": 1000},
```

This ensures that the embedding requests are sent in batches that respect the LLM's token limit, specifically at the `langchain_openai` level. While redundant with the `RecursiveCharacterTextSplitter`'s chunk size, this ensures the size is explicitly passed to the embedding client as well.

This completes the investigation and initial fix for the API token limit issue as per your instructions.

## Further Research: Web Search Results on Token Limits and GPT-Researcher

As requested, I have conducted ten web searches to gather more information on token limits, embedding best practices, and related issues within GPT-Researcher. The results are summarized below:

### 1. Search Query: "OpenAI embedding token limits best practices"
- **Result 1:** `The Best Way to Chunk Text Data for Generating Embeddings with ...` (`https://dev.to/simplr_sh/the-best-way-to-chunk-text-data-for-generating-embeddings-with-openai-models-56c9`)
    - Highlights: "When working with OpenAI's embedding models... one of the most critical steps is chunking your text data... Use Token-Based Chunking..." Emphasizes token-based chunking for fitting within model limits while preserving context.
- **Result 2:** `Embedding model token limit exceeding limit while using batch ...` (`https://community.openai.com/t/embedding-model-token-limit-exceeding-limit-while-using-batch-requests/316546`)
    - Highlights: A user reporting exceeding the embedding model's limit even when not explicitly doing so, suggesting complexities in batch request token counting.

### 2. Search Query: "GPT-Researcher common token limit errors"
- **Result 1:** `smart_token_limit Exceeds Max Tokens · Issue #245 - GitHub` (`https://github.com/assafelovic/gpt-researcher/issues/245`)
    - Highlights: Direct GitHub issue for GPT-Researcher where `smart_token_limit` settings resulted in "max_tokens is too large" error. This issue specifically refers to generation (not embedding) but confirms token limit challenges in the project.
- **Result 2:** `Getting token exceed error while using OpenAI API - Stack Overflow` (`https://stackoverflow.com/questions/78574662/getting-token-exceed-error-while-using-openai-api`)
    - Highlights: General OpenAI API token exceed errors, often related to large inputs. Relevant for understanding the broader context of token management.

### 3. Search Query: "GPT-Researcher langchain_openai embeddings token overflow"
- **Result 1:** `LangChain: Reduce size of tokens being passed to OpenAI` (`https://stackoverflow.com/questions/76451997/langchain-reduce-size-of-tokens-being-passed-to-openai`)
    - Highlights: Discusses `max_tokens_limit` in LangChain `ConversationalRetrievalChain` to truncate input documents, emphasizing that input tokens + max\_tokens\_limit <= model token limit.
- **Result 2:** `Embedding model token limit exceeding limit while using batch ...` (`https://community.openai.com/t/embedding-model-token-limit-exceeding-limit-while-using-batch-requests/316546`)
    - (Duplicate from Search 1, confirms common nature of this specific error)

### 4. Search Query: "GPT-Researcher EMBEDDING_KWARGS chunk_size effect on token limits"
- **Result 1:** `Azure Embedding Quota Limit - assafelovic/gpt-researcher - GitHub` (`https://github.com/assafelovic/gpt-researcher/issues/936`)
    - Highlights: Mentions hitting quota limits with Azure OpenAI and large reports, indicating that raw token limits and rate limits are a common challenge in GPT-Researcher's usage, especially with `detailed report` generation.
- **Result 2:** `What happens in embedding document chunks when the ... - Reddit` (`https://www.reddit.com/r/Rag/comments/1ioc8u5/what_happens_in_embedding_document_chunks_when/`)
    - Highlights: Discusses that exceeding maximum token size for chunks will typically throw an error, reinforcing the need for proper chunk management.

### 5. Search Query: "GPT-Researcher `RecursiveCharacterTextSplitter` token limits"
- **Result 1:** `TEXT SPLITTERS IN LANGCHAIN-(RAG) | by Ayushi Gupta - Medium` (`https://medium.com/@ayushigupta9723/text-splitters-in-rag-langchain-984a64d2835e`)
    - Highlights: General overview of text splitters in LangChain for RAG applications, noting that LLMs have a maximum context window/token limit (e.g., GPT-3.5-turbo 4096, GPT-4 128K).
- **Result 2:** `smart_token_limit Exceeds Max Tokens · Issue #245 - GitHub` (`https://github.com/assafelovic/gpt-researcher/issues/245`)
    - (Duplicate from Search 2, relevant due to its discussion of `smart_token_limit` issues within GPT-Researcher context.)

### 6. Search Query: "OpenAI embeddings batch size limit"
- **Result 1:** `Default Batch size incompatible with Azure OpenAI text-embedding ...` (`https://github.com/langchain-ai/langchain/issues/13197`)
    - Highlights: An issue detailing that Azure OpenAI embedding models have a smaller maximum batch size (e.g., 16) than LangChain's hardcoded values, leading to incompatibility errors. This supports the importance of explicitly setting `chunk_size` for embedding API calls.
- **Result 2:** `Embeddings API Max Batch Size - OpenAI Developer Community` (`https://community.openai.com/t/embeddings-api-max-batch-size/655329`)
    - Highlights: States that the maximum batch size for OpenAI's embeddings API is typically 2048 texts, but context length can still cause issues if the total tokens exceed the limit.

### 7. Search Query: "langchain openai embedding max input size"
- **Result 1:** `LangChain: Reduce size of tokens being passed to OpenAI` (`https://stackoverflow.com/questions/76451997/langchain-reduce-size-of-tokens-being-passed-to-openai`)
    - (Duplicate from Search 3, reinforces the idea of reducing input size in LangChain context.)
- **Result 2:** `New Embedding model input size - OpenAI Developer Community` (`https://community.openai.com/t/new-embedding-model-input-size/602476`)
    - Highlights: Reports `BadRequestError` due to requested tokens exceeding model's context length (e.g., 8192 tokens), even for embedding input. Confirms that input to embedding API itself has a context length.

### 8. Search Query: "GPT-Researcher `sitecustomize.py` patches for OpenAI API"
- **Result 1:** `Error when using OPEN AI API - assafelovic/gpt-researcher - GitHub` (`https://github.com/assafelovic/gpt-researcher/issues/278`)
    - Highlights: Mentions missing `sitecustomize. patches`, indicating its intended role in modifying OpenAI API behavior, likely for streaming control.
- **Result 2:** `GPT Researcher - Tavily Docs` (`https://docs.tavily.com/examples/open-sources/gpt-researcher`)
    - Highlights: General documentation for GPT-Researcher, including its default usage of OpenAI for LLM calls and Tavily API.

### 9. Search Query: "Langchain `RecursiveCharacterTextSplitter` chunk_overlap strategy for embeddings"
- **Result 1:** `Intuition for selecting optimal chunk_size and chunk_overlap for ...` (`https://github.com/langchain-ai/langchain/issues/2026`)
    - Highlights: Discusses the importance of `chunk_overlap` for preserving context and coherence across chunks, particularly for language models. Mentions a common confusion around `chunk_size` being characters vs. tokens.
- **Result 2:** `7 Chunking Strategies for Langchain | by Anix Lynch, MBA, ex-VC` (`https://medium.com/@anixlynch/7-chunking-strategies-for-langchain-b50dac194813`)
    - Highlights: Provides various chunking strategies in LangChain, emphasizing their role in preparing text for LLMs.

### 10. Search Query: "GPT-Researcher `tiktoken` usage token counting"
- **Result 1:** `How to count tokens with Tiktoken - OpenAI Cookbook` (`https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken`)
    - Highlights: Provides programmatic examples for counting tokens with `tiktoken` for various GPT models, noting that message-based formats (like chat models) make token counting more complex.
- **Result 2:** `How to Count Tokens with Tiktoken programmatically - Vellum AI` (`https://www.vellum.ai/blog/count-openai-tokens-programmatically-with-tiktoken-and-vellum`)
    - Highlights: General guidance on using `tiktoken` for programmatic token counting.
