# Backend: MedAgent for German Medical Guidelines

The backend is the main integration layer for guideline storage, retrieval-source preparation, graph and vector infrastructure, workflow execution, and chat-based testing. It is implemented with FastAPI and organized around a model-service-controller structure.

## Swagger-First Usage

Use Swagger UI and the generated OpenAPI schema as the primary way to test and inspect the backend:

- Swagger UI: `http://localhost:5000/docs`
- OpenAPI schema: `http://localhost:5000/openapi.json`

The Swagger groups cover the full backend surface without this README needing to document individual endpoints:

- `Auth`
- `Guidelines`
- `GuidelineReferences`
- `VectorEmbeddings`
- `WeaviateVectorStore`
- `Neo4jGraph`
- `Keywords`, `SNOMED`, `LLM`, `GuidelineContextFilter`, `GuidelineExpander`
- `WorkflowSystems`

In practice, the README should explain what each area is for, while Swagger shows the exact request and response shapes.

## Architectural Principles

| Layer | Role | Typical contents |
| --- | --- | --- |
| **Model** | Defines the application's data structures | Pydantic request and response models, domain models, workflow configs, vector and graph settings |
| **Service** | Contains business logic | Guideline handling, retrieval-source setup, vector and graph integration, workflow execution, prompt loading |
| **Controller** | Exposes the FastAPI HTTP layer | Routers, request validation, response formatting, dependency injection |
| **Exception** | Cross-cutting error handling | Domain-specific exceptions raised in services and translated into consistent HTTP responses |

The important boundary is that controllers stay thin and delegate behavior to services, while models define the shapes shared across the system.

## Project Structure

The backend is easier to understand by looking at the main folders rather than individual files:

```text
backend/
|-- src/app/
|   |-- constants/          # Environment-backed configuration and shared constants
|   |-- controllers/        # FastAPI routers grouped into auth, knowledge, system, and tools
|   |-- exceptions/         # Domain-specific error types translated into HTTP responses
|   |-- models/             # Pydantic models for auth, guidelines, vectors, graphs, tools, chats, and workflows
|   |-- services/
|   |   |-- auth/           # Authentication and token handling
|   |   |-- knowledge/      # Guideline storage, chunking, vectors, and graphs
|   |   |-- system/         # Workflow runtime, components, prompt store, and chat orchestration
|   |   `-- tools/          # Reusable helper services such as LLM, SNOMED, filters, and expanders
|   |-- utils/              # Logging, Mongo setup, templating, and component resolution helpers
|   `-- main.py             # FastAPI app startup and router registration
|-- tests/assets/           # Example workflows and example retrieval-source specifications
`-- README.md
```

Two folders are especially relevant for workflow work:

- [`src/app/services/system/components`](./src/app/services/system/components): workflow component implementations and registration
- [`src/app/services/system/prompts`](./src/app/services/system/prompts): shared prompt templates referenced by `prompt_key`

## Workflow Component Variants

Workflow node types are either single-token structure nodes such as `start` and `merge`, or `family/variant` types such as `retriever/vector_retriever`.

The currently available variants are:

| Type | Family | Purpose |
| --- | --- | --- |
| `start` | Structure | Entry point for user input, chat state, and normalized previous interactions |
| `end` | Structure | Maps workflow data to the final answer, retrieval items, and retrieval latency |
| `list` | Structure | Runs one component template repeatedly over a list of items |
| `merge` | Structure | Flattens and optionally deduplicates outputs from iterative or parallel-like stages |
| `decider` | Structure | Branches to different next components based on a resolved case |
| `decision/expression` | Decision | Resolves a template or expression into a branchable decision value |
| `decision/is_within_scope` | Decision | LLM-based scope gate for in-scope vs. out-of-scope routing |
| `query_transformer/query_context_merger` | Query transformer | Turns a follow-up question plus recent chat context into one standalone query |
| `query_transformer/rewrite` | Query transformer | Rewrites or normalizes a query according to configured instructions |
| `query_transformer/query_augmenter` | Query transformer | Produces multiple subqueries or alternative phrasings |
| `query_transformer/keyword_extractor` | Query transformer | Extracts keywords with YAKE or an LLM and can expand them through SNOMED |
| `query_transformer/hyde` | Query transformer | Generates HyDE-style hypothetical documents for retrieval |
| `retriever/vector_retriever` | Retriever | Runs a single-query search against a Weaviate collection |
| `retriever/multi_queries_vector_retriever` | Retriever | Runs multiple weighted vector or hybrid searches and merges the results |
| `retriever/graph_retriever` | Retriever | Retrieves through Neo4j starting from the user query |
| `expander/neighborhood_references` | Context expander | Adds nearby references from the same ordered reference stream |
| `expander/hierarchy_references` | Context expander | Expands references to larger hierarchy sections using a persisted hierarchy index |
| `expander/graph_references` | Context expander | Expands seed references through the Neo4j graph |
| `filter/deduplicate_references` | Filter | Removes duplicates or near-duplicates from a reference list |
| `filter/relevance_filter_references` | Filter | Keeps the most relevant references using score, cross-encoder, or LLM judging |
| `generator` | Generator | Produces the final response from workflow context and prompt settings |

## Component Notes

### Query transformer

Query transformers are the main place to improve retrieval before the first retriever runs.

- `query_context_merger` should usually come right after `start`. It resolves follow-up questions into one standalone query by using recent chat context.
- `rewrite` is best for typo cleanup, terminology normalization, or light reformulation without changing intent.
- `query_augmenter` is for query decomposition or alternative phrasings.
- `keyword_extractor` supports both YAKE and LLM-based extraction. If SNOMED expansion is enabled, extracted keywords are expanded into synonym-aware retrieval terms.
- `hyde` generates hypothetical guideline-style documents that can improve semantic retrieval.

Useful example workflows:

- [`tests/assets/example_query_transformer_workflow.json`](./tests/assets/example_query_transformer_workflow.json)
- [`tests/assets/example_query_decomposition_flow_workflow.json`](./tests/assets/example_query_decomposition_flow_workflow.json)

### Retriever options

There are three retriever patterns in the current backend.

- `vector_retriever` is the default when one query and one named vector are enough.
- `multi_queries_vector_retriever` is the better choice when several retrieval views should contribute to one merged ranking.
- `graph_retriever` starts directly from the query and retrieves through Neo4j.

Multi-query with hybrid retrieval works as follows:

- each configured subquery runs independently
- each subquery can choose its own named vector
- each subquery can be pure vector or hybrid
- in hybrid mode, Weaviate combines embedding similarity with BM25 over the configured keyword properties
- `alpha` controls the keyword vs. vector balance inside that subquery
- `weight` controls how strongly that subquery contributes to the final merged score
- duplicate references are merged before final ranking

This is especially useful when combining chunk text, heading vectors, and one keyword-assisted fallback query.

For retriever setup, the usual dependency chain is:

1. choose or create the reference group
2. optionally create a chunked reference-group copy
3. create the Weaviate collection linked to that group
4. ingest the group into Weaviate
5. point the workflow retriever to that collection

The full setup flow is described further below under "From guideline to retrieval source and graph".

Useful example files:

- [`tests/assets/example_vector_retriever_workflow.json`](./tests/assets/example_vector_retriever_workflow.json)
- [`tests/assets/example_multi_queries_vector_retriever_workflow.json`](./tests/assets/example_multi_queries_vector_retriever_workflow.json)
- [`tests/assets/example_vector_collection_ref_spec.json`](./tests/assets/example_vector_collection_ref_spec.json)

### Graph retriever

The graph layer can be used in two ways:

- `retriever/graph_retriever`: query -> graph retrieval
- `expander/graph_references`: seed references -> graph expansion

The second pattern is often easier to reason about because vector retrieval stays the explicit seed stage and the graph acts as a second-stage relevance expansion.

Graph setup is straightforward conceptually:

1. choose the reference group that should become the graph source
2. sync that group into Neo4j
3. optionally include keyword edges and similarity edges
4. reference the resulting `graph_name` in the workflow

Important graph controls are:

- `graph_name`
- `neighbor_depth`
- `include_section_references`
- `section_max_children`
- `include_keyword_matches`
- `keyword_overlap_min`
- `keyword_overlap_ratio_min`
- `include_similarity_matches`
- `similarity_threshold`
- `limit`

Graph visualization is best done directly in Neo4j Browser or Bloom by filtering on `graph_name`. For workflow-level understanding, the returned `graph_hits` are the most useful explanation because they show why a reference was included.

For expanding from the graph, the typical pattern is:

1. retrieve vector seeds
2. expand them with `expander/graph_references`
3. optionally deduplicate or relevance-filter
4. generate from the expanded set

Useful example workflow:

- [`tests/assets/example_graph_retriever_workflow.json`](./tests/assets/example_graph_retriever_workflow.json)

### Guideline context filter

The filter family works on `GuidelineReference` lists, not only on retriever outputs. This makes it useful after retrieval, after graph expansion, or even after some generation stage if you want to compare output against context.

The key inputs are:

- the references to inspect
- the `filter_input`
- the filter settings

`filter_input` can be:

- the raw user query
- a merged or rewritten query
- a decomposition subquery
- a generated draft answer or other workflow output

There are two filter variants:

- `deduplicate_references`
- `relevance_filter_references`

For relevance filtering, the backend supports score-based filtering, cross-encoder reranking, and LLM judging. The selected reference properties decide what the filter actually sees, so typical combinations are `content`, `heading_path`, `associated_keywords`, and `type`.

Useful example workflows:

- [`tests/assets/example_guideline_context_filter_all_in_one_workflow.json`](./tests/assets/example_guideline_context_filter_all_in_one_workflow.json)
- [`tests/assets/example_expander_workflow.json`](./tests/assets/example_expander_workflow.json)

### Guideline context expansion

Context expansion means adding supporting evidence after an initial seed set already exists.

The current expansion options are:

- `neighborhood_references`: local neighboring context from the ordered reference stream
- `hierarchy_references`: larger structural context from the hierarchy index
- `graph_references`: graph-based contextual expansion through structure, keywords, and similarity

Technically, graph expansion is also a context expansion strategy. It is described separately here because it requires additional graph setup and often behaves more like a second-stage relevance layer than a purely structural expansion step.

Setup requirements differ by variant:

- neighborhood expansion only needs stored references with valid order
- hierarchy expansion requires a persisted hierarchy index for the reference group
- graph expansion requires a synced Neo4j graph

Useful example workflows:

- [`tests/assets/example_expander_workflow.json`](./tests/assets/example_expander_workflow.json)
- [`tests/assets/example_graph_retriever_workflow.json`](./tests/assets/example_graph_retriever_workflow.json)

### Generator prompt store

The generator can use inline prompts, stored prompt definitions, or a mix of both.

The prompt store lives under [`src/app/services/system/prompts`](./src/app/services/system/prompts). Prompt folders are referenced by `prompt_key`, and each key can provide:

- `prompt.md`
- optional `system_prompt.md`

The same mechanism is also reused by some query transformers, especially HyDE.

The most useful pattern is:

- keep stable, reusable instructions in the prompt store
- keep workflow-specific context assembly in the workflow JSON

Useful example workflows:

- [`tests/assets/example_multi_queries_vector_retriever_prompt_store_workflow.json`](./tests/assets/example_multi_queries_vector_retriever_prompt_store_workflow.json)
- [`tests/assets/example_query_transformer_workflow.json`](./tests/assets/example_query_transformer_workflow.json)

## From Guideline to Retrieval Source and Graph

The full setup path is easiest to understand as a dependency chain.

### 1. Create the guideline entry

Start with the guideline metadata and, if needed, link the PDF. This is the document-level source object everything else refers back to.

### 2. Create the source reference group

Reference groups are the base container for extracted or curated references. This is the level later used by chunking, keyword enrichment, hierarchy indexing, vector ingestion, and graph sync.

### 3. Add or curate the references

Once the reference group exists, the actual `GuidelineReference` items are stored there. At this point, you have a usable reference source, but not yet an optimized retrieval source.

### 4. Optional but important: chunking

Chunking is usually the first real retrieval-preparation step.

- only `text` references are split
- non-text references are copied unchanged
- chunked references preserve their relation to the original guideline and hierarchy
- bounding boxes are recalculated for the resulting chunks when possible

The available chunking strategies are:

- `fixed_characters`
- `sentence`
- `paragraph`

In practice:

- `fixed_characters` is usually the best first choice for retrieval
- `sentence` is useful when very fine-grained evidence is needed
- `paragraph` is useful when paragraph boundaries already match meaningful context units

If retrieval, graph expansion, or reranking should work on smaller evidence units, use the chunked reference-group copy rather than the original source group.

### 5. Optional: keyword enrichment

Keyword enrichment writes extracted keywords into `associated_keywords`.

This becomes useful when:

- graph keyword edges should be created
- filters should inspect keywords
- vector collection metadata should include keyword fields

If SNOMED expansion is enabled, the stored keyword set becomes more retrieval-oriented and synonym-aware.

### 6. Optional: hierarchy index

Hierarchy expansion depends on a persisted hierarchy index for a reference group. If `expander/hierarchy_references` should be part of the workflow, this index has to exist first.

### 7. Create the Weaviate collection

The vector collection links a reference group to:

- stored Weaviate properties
- named vectors
- the ingestion mapping from references into vector objects

The best starting point is:

- a chunked reference group
- one main text vector
- optional additional structure-aware vectors such as headings

Useful setup reference:

- [`tests/assets/example_vector_collection_ref_spec.json`](./tests/assets/example_vector_collection_ref_spec.json)

### 8. Ingest the reference group into Weaviate

After the collection exists, ingest the linked group so workflow retrievers can use it. This step is required for both `vector_retriever` and `multi_queries_vector_retriever`.

### 9. Sync the same reference group into Neo4j

If graph retrieval or graph expansion should be available, sync the chosen reference group into Neo4j.

Typical dependency notes:

- graph components require the synced graph
- keyword-based graph expansion is only useful if keyword enrichment has already been done
- similarity-based graph expansion depends on similarity edges being created during graph sync

### 10. Build the workflow

Once the data sources exist, the components compose naturally:

1. query transformers improve the query
2. retrievers create a seed set
3. expanders add context
4. filters remove noise
5. the generator answers from the final evidence set

Useful end-to-end workflow examples:

- [`tests/assets/example_vector_retriever_workflow.json`](./tests/assets/example_vector_retriever_workflow.json)
- [`tests/assets/example_multi_queries_vector_retriever_workflow.json`](./tests/assets/example_multi_queries_vector_retriever_workflow.json)
- [`tests/assets/example_graph_retriever_workflow.json`](./tests/assets/example_graph_retriever_workflow.json)
- [`tests/assets/example_expander_workflow.json`](./tests/assets/example_expander_workflow.json)

## Current Scope

The current backend already covers:

- authentication and role-aware access control
- guideline and reference-group persistence
- chunking, keyword enrichment, and hierarchy indexing
- embedding-provider inspection and direct embedding tests
- Weaviate collection setup, ingestion, search, and per-guideline replacement
- Neo4j graph sync, graph retrieval, and graph expansion
- reusable prompt storage
- workflow storage, chat execution, branching, iteration, merging, filtering, and generation

## What Comes Next

The next useful work areas are:

- smoother ingestion from PDFs into structured reference groups
- broader evaluation and benchmarking of workflow variants
- stronger frontend support for workflow authoring and retrieval-source management
- additional workflow components once the current retrieval and graph patterns stabilize
