# BACKEND: MedAgent for German medical guidelines (simplified)

The backend contains the core application logic of **MedAgent**. It is responsible for
authentication, API endpoints, and later the integration of RAG workflows, databases,
and LLMs.

The backend is implemented using **FastAPI** and follows a clear
**Model–Service–Controller** architecture, inspired by:
https://medium.com/@jeremyalvax/fastapi-backend-architecture-model-controller-service-44e920567699

---

## Architectural principles

### Model layer

Defines data structures and schemas:

- request / response models
- internal domain models
- database schemas (added later)

### Service layer

Contains all business logic:

- authentication and token handling
- workflow execution logic
- interaction with external systems (LLMs, vector DBs, etc.)

Services should:

- be reusable
- not depend on FastAPI
- not import controllers
- avoid circular dependencies

### Controller layer

Defines the FastAPI routers and endpoints:

- validates and parses HTTP input
- delegates all logic to services
- formats HTTP responses and errors

Controllers should contain **minimal logic**.

### Exception layer (cross-cutting)

Defines domain-specific exceptions that can be raised from services and translated into
consistent HTTP errors in controllers.

---

## Project structure

```text
src/app/
├── constants/     # Centralized configuration (via environment variables)
│   ├── auth_config.py
│   ├── logging_constants.py
│   └── mongodb_config.py
├── controllers/   # FastAPI routers / HTTP endpoints
│   ├── auth /
│   │   ├── auth_router.py
│   │   └── __init__.py
│   ├── dependencies /
│   │   ├── auth_dependencies.py
│   │   └── __init__.py
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_router.py
│   │       ├── guideline_reference_router.py
│   │       └── __init__.py
│   ├── system /
│   │   ├── system_router.py
│   │   └── __init__.py
│   └── tools /
│       ├── tools_test_router.py
│       └── __init__.py
├── exceptions/    # Domain-specific exceptions
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_error.py
│   │       ├── guideline_reference_error.py
│   │       └── __init__.py
│   ├── system /
│   │   └── chat /
│   │       ├── chat_error.py
│   │       └── __init__.py
│   └── tools /
│       ├── llm_interaction_error.py
│       └── __init__.py
├── models/        # Pydantic models, schemas, domain objects
│   ├── auth /
│   │   ├── token.py
│   │   ├── user.py
│   │   └── __init__.py
│   ├── common /
│   │   ├── py_object_id.py
│   │   └── __init__.py
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_entry.py
│   │       ├── guideline_reference.py
│   │       └── __init__.py
│   ├── system /
│   │   ├── system_chat_interaction.py
│   │   ├── workflow_system.py
│   │   └── __init__.py
│   └── tools /
│       ├── keyword_interaction.py
│       ├── llm_interaction.py
│       └── __init__.py
├── services/      # Business logic (auth, workflows, evaluation, ...)
│   ├── service_registry.py
│   ├── auth /
│   │   ├── auth_service.py
│   │   ├── token_service.py
│   │   └── __init__.py
│   ├── knowledge /
│   │   └── guideline /
│   │       ├── guideline_service.py              # incl. PDF download
│   │       ├── guideline_reference_service.py    # incl. reference groups
│   │       └── __init__.py
│   ├── system /
│   │   ├── workflow_system_interaction_service.py
│   │   ├── workflow_system_storage_service.py
│   │   ├── chat /
│   │   │   ├── chat_service.py
│   │   │   └── __init__.py
│   │   └── components /
│   │       ├── abstract_component.py
│   │       ├── component_registry.py
│   │       └── structure /
│   │           ├── start_component.py
│   │           ├── end_component.py
│   │           └── __init__.py
│   └── tools /
│       ├── keyword_service.py
│       ├── llm_interaction_service.py
│       └── __init__.py
├── utils/         # Shared helpers (logging, service factories, etc.)
│   ├── llm_client.py
│   ├── logging.py
│   ├── mongo_collection_setup.py
│   └── system /
│       ├── render_template.py
│       ├── resolve_component_path.py
│       └── __init__.py
└── main.py        # FastAPI app setup and router registration
```

### Available system workflow components

System workflows are built from **components**. All components inherit from
[`AbstractComponent`](src/app/services/system/components/abstract_component.py) and are registered via:

- `AbstractComponent.variants = {"start": StartComponent, "end": EndComponent ...}`

The currently available component variants are:

| Variant name                               | Component class                                                                                                   | Description / Purpose                                                                                                                                                                                                                     |
|--------------------------------------------|-------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `start`                                    | [`StartComponent`](./src/app/services/system/components/structure/start_component.py)                             | Required as start to provide user input                                                                                                                                                                                                   |
| `end`                                      | [`EndComponent`](./src/app/services/system/components/structure/end_component.py)                                 | Required as end to define generator output (text) and retrieval result (references)                                                                                                                                                       |
| `generator`                                | [`LLMGenerator`](./src/app/services/system/components/generator/generator.py)                                     | Executes the actual text generation step by sending a resolved prompt to the configured LLM and returning the model response. The LLM is configured via [`LLMSettings`](./src/app/models/tools/llm_interaction.py).                       |
| `expander/neighborhood_references`         | [`NeighborhoodReferencesExpander`](./src/app/services/system/components/context_expander/reference_expander.py)   | Expands references to surrounding items inside the same guideline and reference group, using the stored guideline-reference heading order. Supports symmetric, preceding-only, or succeeding-only context windows.                        |
| `expander/hierarchy_references`            | [`HierarchyReferencesExpander`](./src/app/services/system/components/context_expander/reference_expander.py)      | Expands filtered references to a larger hierarchy section based on the selected reference group. The hierarchy index is persisted as JSON so later runs can reuse it.                                                                     |
| `expander/graph_references`                | [`GraphReferencesExpander`](./src/app/services/system/components/context_expander/reference_expander.py)          | Takes an existing seed list of guideline references and expands it through the Neo4j graph via neighbors, shared sections, and shared keywords, while still returning plain guideline references.                                         |
| `filter/deduplicate_references`            | [`DeduplicateReferencesFilter`](./src/app/services/system/components/filter/guideline_context_filter.py)          | Deduplicates a list of guideline references based on configured properties such as `content` and `heading_path`.                                                                                                                          |
| `filter/relevance_filter_references`       | [`RelevanceFilterReferences`](./src/app/services/system/components/filter/guideline_context_filter.py)            | Relevance-based filtering for guideline references. It can use numeric fields, a cross-encoder, or an LLM judge, and can combine multiple properties into one filter input.                                                               |
| `query_transformer/query_context_merger`   | [`QueryContextMergerTransformer`](./src/app/services/system/components/query_transformer/query_context_merger.py) | Builds one standalone query from the current user input plus the last `x` chat turns. It only considers prior user inputs and final generator outputs, so it works as a lightweight workflow-level context provider without tool routing. |
| `query_transformer/rewrite`                | [`QueryRewriteTransformer`](./src/app/services/system/components/query_transformer/query_rewriter.py)             | LLM-based query rewriting. Use `rewrite_instructions` to define the rewrite behavior, for example a clean-query rewrite that only fixes misspellings and spacing.                                                                         |
| `query_transformer/keyword_extractor`      | [`KeywordQueryTransformer`](./src/app/services/system/components/query_transformer/keyword_transformer.py)        | Extracts query keywords with either `yake` or `llm`, and can optionally expand them with SNOMED synonyms.                                                                                                                                 |
| `query_transformer/hyde`                   | [`HyDEQueryTransformer`](./src/app/services/system/components/query_transformer/hyde_query_transformer.py)        | Generates hypothetical retrieval documents from the query. The default HyDE prompt is available from the prompt store via `hyde_awmf_query_transform_v1`.                                                                                 |
| `retriever/graph_retriever`                | [`GraphRetriever`](./src/app/services/system/components/retriever/graph_retriever.py)                             | Convenience variant for Neo4j graph retrieval that discovers seeds internally. It is available, but for Graph-RAG workflows the preferred pattern is `retriever/...` for seed generation followed by `expander/graph_references`.         |
| `retriever/vector_retriever`               | [`VectorRetriever`](./src/app/services/system/components/retriever/vector_retriever.py)                           | Queries a Weaviate collection during workflow execution and returns workflow-native retrieval references. Search settings are validated through [`VectorRetrieverSettings`](./src/app/models/system/workflow_retriever.py).               |
| `retriever/multi_queries_vector_retriever` | [`MultiQueriesVectorRetriever`](./src/app/services/system/components/retriever/vector_retriever.py)               | Executes multiple weighted Weaviate searches, merges duplicate hits, and returns the combined retrieval references. Settings are validated through [`MultiQueryVectorRetrieverSettings`](./src/app/models/system/workflow_retriever.py).  |

Query transformer options at a glance:

- `query_transformer/query_context_merger`: requires `llm_settings`; configure `max_history_items` (= `x`) and optionally `max_output_chars`
- `query_transformer/rewrite`: requires `llm_settings`; use `rewrite_instructions` to define what "rewrite" means
- `query_transformer/keyword_extractor`: choose `extraction_method` = `yake` or `llm`; optionally set `expand_with_synonyms`
- `query_transformer/hyde`: requires `llm_settings`; supports `prompt_key`, `num_documents`, `target_tokens`, and few-shot `examples`

Logical placement:

- Put `query_transformer/query_context_merger` directly after `start` and before rewrite / keyword extraction / retrieval.
- That way the workflow first resolves follow-up context into one standalone query, and downstream components only have to work with that compressed
  query.
- The merger is intentionally stateless at the LLM layer, so each compression step sends only the last `x` interactions once instead of growing a long
  chat payload over time.
- `start` now exposes `start.previous_interactions`, which contains normalized prior `user_input` plus final `system_output` values for downstream
  use.

### Example workflow

Create a workflow by posting a JSON object to POST `<backend>/system/workflow` that looks like:

- [Generator-only workflow](./tests/assets/example_gen_workflow.json) (! need to configure LLM settings)
- [Query transformer workflow example](./tests/assets/example_query_transformer_workflow.json) (query rewrite with a clean query, keyword extraction
  after a context-merging step, without synonyms, and HyDE)
- [Vector retrieval + generator workflow](./tests/assets/example_vector_retriever_workflow.json) (! need to configure LLM settings and ensure the
  Weaviate collection exists)
- [Vector seeds + graph expansion + generator workflow](./tests/assets/example_graph_retriever_workflow.json) (! need to configure LLM settings, sync
  a Neo4j graph first, and provide seed references through the preceding retriever)
- [Vector retrieval + guideline context filter + generator workflow](./tests/assets/example_guideline_context_filter_workflow.json) (! need to
  configure LLM settings and ensure the Weaviate collection exists)
- [Vector retrieval + deduplicate + cross-encoder relevance + LLM relevance + generator workflow](./tests/assets/example_guideline_context_filter_all_in_one_workflow.json) (!
  need to configure LLM settings and ensure the Weaviate collection exists)
- [Vector retrieval + neighborhood expansion + cross-encoder filter + hierarchy expansion + LLM filter + generator workflow](./tests/assets/example_expander_workflow.json) (!
  need to configure LLM settings; expansion itself works on stored guideline references, need to setup hierarchy index in group on
  `POST /guideline_references/groups/{reference_group_id}/hierarchy-index`)
- [Multi-query vector retrieval + generator workflow](./tests/assets/example_multi_queries_vector_retriever_workflow.json) (! need to configure LLM
  settings and ensure the Weaviate collection exists)
- [Multi-query vector retrieval + prompt-store generator workflow](./tests/assets/example_multi_queries_vector_retriever_prompt_store_workflow.json) (!
  need to configure LLM settings and ensure the Weaviate collection exists)

### Retriever component notes

Shared outputs:

- `component_id.references`: list of retrieval references compatible with `RetrievalResult`

Most retrievers also expose:

- `component_id.latency`: elapsed retrieval time in seconds

Variant guidance:

`retriever/vector_retriever`

- Use this as the default seed retriever when one query and one vector space are enough.
- Required parameters: `query` plus `settings`.
- Main retrieval controls live in `settings`: `vector_name`, `mode`, `keyword_properties`, `alpha`, `minimum_score`, and `limit`.

Minimal settings shape:

```json
{
  "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
  "vector_name": "text",
  "limit": 5,
  "mode": "vector",
  "content_property": "text",
  "reference_id_property": "reference_id",
  "source_id_property": "guideline_id"
}
```

`retriever/multi_queries_vector_retriever`

- Use this when seed retrieval should combine several retrieval views, for example text plus heading vectors, or vector plus hybrid sub-queries.
- The top-level component `query` is not used here; each entry in `settings.queries` carries its own resolved query.
- Extra output: `component_id.queries`, which records the resolved query/vector combinations used during execution.
- `settings`: object validated by `MultiQueryVectorRetrieverSettings`
- `settings.queries`: list of weighted query definitions, each with `query`, `vector_name`, and optional hybrid-search knobs

`retriever/graph_retriever`

- This is a convenience query-to-graph retriever for Neo4j.
- Extra output: `component_id.graph_hits`, which explains the graph ranking.
- It is available, but for Graph-RAG workflows the preferred pattern is still explicit seed generation followed by graph expansion.

Preferred Graph-RAG pattern:

1. use `retriever/vector_retriever` or `retriever/multi_queries_vector_retriever` to create the seed set
2. pass those seed references into `expander/graph_references`
3. optionally apply `filter/deduplicate_references` and/or `filter/relevance_filter_references`
4. generate from the expanded set

That keeps the graph stage explicit: seed references in, expanded references out.

## Neo4j guideline graph

The backend now supports a lightweight Neo4j graph for guideline retrieval. The graph is intentionally brief and document-centric:

- `Guideline` nodes hold guideline-level metadata
- `Section` nodes capture the heading hierarchy
- `Reference` nodes point back to the original MongoDB guideline references
- `Keyword` nodes link normalized `associated_keywords`

Typical relations are `IN_GUIDELINE`, `PART_OF`, `SUBSECTION_OF`, `NEXT` / `PREV`, `HAS_KEYWORD`, and `SIMILAR`.

For inspection and visualization, Neo4j provides its own frontend, the Neo4j Browser. In the local Docker setup it is available at
`http://localhost:7474`. Log in with the configured Neo4j credentials from [`docker/.env`](../docker/.env), by default `neo4j` plus the configured
`NEO4J_PASSWORD`.

The preferred workflow integration is `expander/graph_references`, which takes a seed set of `GuidelineReference` items and returns an expanded list
of `GuidelineReference` items. This keeps the graph stage transparent and fits the intended "seed set first, graph expansion second" design better
than an all-in-one graph retriever.

Current graph expansion properties:

- `include_seed_references`: keep the original seed references in the final output so the generator still sees the anchor evidence.
- `neighbor_depth`: follow the `NEXT` / `PREV` chain around each seed. This is useful for immediately preceding or following chunks.
- `include_section_references`: add references with section overlap, meaning they connect to the same `Section` node as a seed through `PART_OF`.
- `section_max_children`: soft cap on how many same-section candidates are considered before final ranking when a section is large.
- `include_keyword_matches`: add references connected through shared `Keyword` nodes.
- `keyword_overlap_min`: absolute keyword-overlap shortcut. If at least this many normalized keywords overlap, the match is accepted directly.
- `keyword_overlap_ratio_min`: normalized keyword-overlap threshold based on the smaller keyword set. This helps when one side has only a few keywords but those are fully or almost fully covered.
- `include_similarity_matches`: add references connected through `SIMILAR` edges.
- `similarity_threshold`: minimum similarity-edge score required before a semantic match is accepted.
- `limit`: overall cap on the expanded result list.

How to read the two most important non-trivial signals:

- Section overlap: two references overlap by section when they are attached to the same heading section in the synced graph. In practice this means "same heading context", which is why it is usually the best expansion signal.
- Keywords: keyword expansion uses normalized `associated_keywords` from the source references. Matching is not purely absolute anymore: the graph also checks normalized overlap against the smaller keyword set, so a candidate can still match when a small keyword list is fully covered. This increases recall, but it is still noisier than section overlap because keyword quality depends on extraction quality and may connect content across different guidelines.
- Similarity: similarity expansion uses `SIMILAR` edges built during graph sync from dense embeddings over the reference text plus heading path. This is the strongest non-structural signal and is usually the best secondary expansion criterion after section overlap.

### Guideline context filter notes

Shared inputs:

- `references_key`: workflow key or template resolving to the retrieved references
- `filter_input`: query, response, or other text used for the keep/drop decision
- `settings`: object validated by [`GuidelineContextFilterSettings`](./src/app/models/tools/guideline_context_filter.py)

This component works on lists of `GuidelineReference` objects, not on `RetrievalResult`. That means it can also filter references that did not come
from Weaviate or any retriever component.

The service exposes two explicit operations, and the workflow system now mirrors them as two separate component variants:

- `deduplicate_references(...)`
- `relevance_filter_references(...)`

Filtering conditions you can define:

- `settings.kind`: `deduplicate` or `relevance`
- `settings.method`: for relevance filtering choose `score`, `cross_encoder`, or `llm`
- `settings.properties[].path`: choose which fields of each `GuidelineReference` are inspected, for example `content`, `heading_path`,
  `associated_keywords`, `type`, `guideline_id`, or any dotted path inside the model
- `settings.properties[].label`, `include_label`, `max_chars`: control how each selected field is serialized before relevance judging
- `settings.joiner` and `include_empty_properties`: control how the selected fields are combined into one per-reference string
- `settings.minimum_score`, `keep_top_k`, `sort_by_score`: define thresholding and final ordering
- `settings.score_field`: numeric field used when `method = "score"`
- `settings.deduplicate_keep_strategy`: choose whether duplicate groups keep the `highest_score` item or the `first`
- `settings.llm_system_prompt`, `llm_batch_size`, and `llm_settings`: define the LLM-based judging behavior when `method = "llm"`

To avoid a component explosion, the item input is defined through `settings.properties`. Each entry selects one property, for example `retrieval`,
`content`, `heading_path`, or any dotted path inside the reference model. These selected properties are merged into one per-item string before
cross-encoder or LLM judging.

Practical use after graph expansion:

- Deduplicate on `content` plus `heading_path` if section expansion can surface near-identical neighboring chunks.
- Relevance-filter on `content` plus `heading_path` to keep graph context tied to the current question.
- Add `associated_keywords` only if those keywords are curated well enough to help rather than add noise.

It accepts guideline references directly, so the same filtering logic can be used without going through the workflow system.

If you want one workflow that exercises both filter variants in sequence, use
[example_guideline_context_filter_all_in_one_workflow.json](./tests/assets/example_guideline_context_filter_all_in_one_workflow.json).
It runs:

- `filter/deduplicate_references`
- `filter/relevance_filter_references` with `method = "cross_encoder"`
- `filter/relevance_filter_references` with `method = "llm"`
- `generator`

### Expander notes

All expander variants expect:

- `references_key`: workflow key or template resolving to the input reference list
- `settings`: object validated by the variant-specific settings model

Neighborhood expansion:

- `type = "expander/neighborhood_references"`
- uses the reference group plus guideline-local heading order from stored `GuidelineReference.document_hierarchy`
- `context_window_size = 2` means two chunks before and two after when `direction = "both"`
- `direction` can be `preceding`, `succeeding`, or `both`

Hierarchy expansion:

- `type = "expander/hierarchy_references"`
- resolves the reference group from the input references, or from `settings.reference_group_id`
- builds or loads a persisted hierarchy index from `REFERENCE_GROUP_HIERARCHY_INDEX_FOLDER`
- `mode = "direct_parent"` expands to the immediate parent section
- `mode = "levels_up"` with `levels_up = x` expands higher ancestors
- `mode = "heading_level"` expands to the nearest ancestor at the configured heading level

Graph seed expansion:

- `type = "expander/graph_references"`
- takes the provided seed references as the graph entry points
- returns `component_id.references`, `component_id.added_references`, and `component_id.graph_hits`

Implemented expansion / filtering controls:

- `include_seed_references`: keep or drop the original seeds from the final output
- `neighbor_depth`: include immediate `NEXT` / `PREV` neighbors up to the configured hop distance
- `include_section_references`: include references that share a section with at least one seed
- `section_max_children`: soft cap on how many same-section candidates are considered before final ranking
- `include_keyword_matches`: include references connected through shared normalized keywords
- `keyword_overlap_min`: absolute keyword-overlap shortcut
- `keyword_overlap_ratio_min`: normalized keyword-overlap threshold based on the smaller keyword set, with a small shared-keyword floor so tiny one-keyword matches do not dominate
- `include_similarity_matches`: include references connected through `SIMILAR` edges
- `similarity_threshold`: require at least this similarity score before similarity-based expansion is allowed
- `limit`: global cap on the final expanded result size

Recommended starting profile:

```json
{
  "graph_name": "guideline_graph_v1",
  "limit": 8,
  "include_seed_references": true,
  "neighbor_depth": 1,
  "include_section_references": true,
  "section_max_children": 12,
  "include_keyword_matches": false,
  "keyword_overlap_min": 2,
  "keyword_overlap_ratio_min": 0.8,
  "include_similarity_matches": true,
  "similarity_threshold": 0.5
}
```

If keyword links are high quality and you want broader recall, turn `include_keyword_matches` on and start with `keyword_overlap_min = 2` plus `keyword_overlap_ratio_min = 0.8`.

Which expansion criteria make the most sense in practice:

- Strongest default signal: same section as the seed. In guideline documents this usually preserves the most meaningful local context.
- Strongest secondary signal: similarity edges with a threshold around `0.5-0.7`. They usually capture semantically related references better than plain keywords.
- Also useful: immediate neighbors with a small window, usually `neighbor_depth = 1` and sometimes `2`. This works well when references were chunked
  sequentially.
- Useful but more selective now: shared keywords. This should still usually be treated as a supplementary signal, not the only one, because keyword
  quality depends on extraction quality and may connect across guidelines. The normalized overlap check mainly helps when one side has only a few but
  highly relevant keywords.
- Usually best to keep: `include_seed_references = true`, so the generator still sees the original anchor evidence.
- Usually best to constrain: moderate `limit` such as `6-12`, and moderate `section_max_children`, so one broad section does not dominate the result.

Useful filtering directly after graph expansion:

- deduplicate on `content` and `heading_path` when section and neighbor expansion can surface overlapping chunks
- relevance-filter on `content` and `heading_path` to remove graph-adjacent but question-irrelevant references
- if keyword expansion is enabled, consider adding `associated_keywords` to the relevance filter input, but only when those keywords are trustworthy
- if similarity expansion is enabled, it often still helps to relevance-filter afterwards because semantic neighbors can be topically close while still
  being too broad for the current question

Criteria that are usually less sensible unless you have a strong reason:

- Large neighbor windows. They tend to reintroduce the same context bloat as naive Small2Big expansion.
- Keyword-only expansion with low thresholds. This can become noisy quickly, especially across multiple guidelines.
- Very large section fan-out. It reduces transparency and often dilutes the seed evidence.

Criteria that would also make sense as future extensions, but are not implemented yet:

- restricting expansion to certain reference types such as `recommendation` or `statement`
- a same-guideline-only vs. cross-guideline toggle for keyword expansion
- a minimum shared-keyword ratio relative to the seed keyword set, which is often better than a pure absolute count

API endpoints:

- `POST /guideline_references/groups/{reference_group_id}/hierarchy-index` builds or refreshes the persisted hierarchy index for one reference group
- `POST /tools/guideline-expander` runs neighborhood- or hierarchy-based expansion directly on provided `GuidelineReference` items

### Prompt store workflow example

Stored prompts now use typed prompt definitions with:

- `system_prompt`: the reusable instruction block
- `prompt`: an example prompt or default prompt template stored alongside the system prompt

The prompt store is not limited to generators. Query transformers can also reuse stored prompt templates, for example the built-in HyDE prompt key
`hyde_awmf_query_transform_v1`.

The recommended pattern is to keep the reusable instruction in the prompt store and define the actual execution prompt directly in the generator
or query transformer unless the same prompt is reused in multiple workflows.

### Query context merger notes

`query_transformer/query_context_merger` uses the current query plus the last `x` previous interactions from `start.previous_interactions`.

- The previous interaction payload is prepared in `start`, so downstream components do not need to inspect the chat object directly.
- For previous turns, `start` prefers `generator_output` and falls back to the stored `end.response` in workflow execution traces if needed.
- It ignores older turns beyond `max_history_items`.
- It trims each previous generator output via `max_output_chars` before sending the compression prompt.
- It returns one merged query in `component_id.merged_query` and also exposes it as `component_id.primary_query`.

Typical examples:

- Previous turn: "Wie wird Appendizitis diagnostiziert?" -> "Klinik, Labor, Sonographie ..."
- New turn: "Und in der Schwangerschaft?"
- Merged query: "Wie wird Appendizitis in der Schwangerschaft diagnostiziert?"

- Previous turns are unrelated and the new query is standalone.
- Merged query: unchanged current query.

Example:

```json
{
  "name": "Multi Query Vector Retrieval + Prompt Store Generator",
  "nodes": [
	{
	  "component_id": "start",
	  "name": "Start node",
	  "type": "start",
	  "parameters": {}
	},
	{
	  "component_id": "retriever",
	  "name": "Guideline multi-query vector retriever",
	  "type": "retriever/multi_queries_vector_retriever",
	  "parameters": {
		"settings": {
		  "weaviate_collection": "OpenSource_StructuredGuidelineFixedCharacters500_RefSpec",
		  "limit": 5,
		  "per_query_limit": 8,
		  "queries": [
			{
			  "query": "{start.current_user_input}",
			  "vector_name": "text",
			  "weight": 1.0,
			  "mode": "vector"
			},
			{
			  "query": "{start.current_user_input}",
			  "vector_name": "headers",
			  "weight": 0.4,
			  "mode": "vector"
			},
			{
			  "mode": "hybrid",
			  "keyword_properties": [
				"text",
				"headers"
			  ],
			  "alpha": 0.2
			}
		  ],
		  "content_property": "text",
		  "reference_id_property": "reference_id",
		  "source_id_property": "guideline_id"
		}
	  }
	},
	{
	  "component_id": "generator",
	  "name": "OpenAI Generator",
	  "type": "generator",
	  "parameters": {
		"prompt_key": "awmf_clinical_qa_html_v1",
		"prompt": "{\ncontexts = []\nfor i, ref in enumerate(retriever.references):\n    properties = ref.weaviate_properties or {}\n    section = properties.get('headers', '')\n    text = properties.get('text') or ref.retrieval or ''\n    contexts.append(f'''<context_item id=\"{i}\" section=\"{section}\">\\n{text}\\n</context_item>''')\nreturn f'''<context>{chr(10).join(contexts)}</context>\\n<question>{start.current_user_input}</question>'''\n}",
		"llm_settings": {
		  "model": "gpt-4o-mini",
		  "api_key": "TODO",
		  "base_url": "https://api.openai.com/v1",
		  "max_tokens": 512,
		  "timeout_s": 60
		}
	  }
	},
	{
	  "component_id": "end",
	  "name": "End node",
	  "type": "end",
	  "parameters": {
		"generation_key": "{generator.response}",
		"retrieval_key": "{retriever.references}",
		"retrieval_latency_key": "{retriever.latency}"
	  }
	}
  ],
  "edges": [
	{
	  "source": "start",
	  "target": "retriever"
	},
	{
	  "source": "retriever",
	  "target": "generator"
	},
	{
	  "source": "generator",
	  "target": "end"
	}
  ]
}
```

Here, `prompt_key` contributes the reusable AWMF system prompt, while `prompt` is defined in the workflow and can map whatever retrieval structure
that workflow exposes.

---

### Example guideline to retrieval source

Via the backend API, add a guideline entry to the database.

Then, guideline references can be created in the frontend when they are assigned the role of `admin`.
Once logged in, a new tab with the name "reference management" will appear in the navigation bar.
Here, a new reference group can be created, and a guideline can be selected, allowing to now manage and add new references.
How to create a new one: currently only implemented with the bounding box text search.

If the retrieval source should work on chunks instead of the original references, create a second reference group as a
chunking result. Chunking only splits narrative text references; all other reference types stay as they are. The new
chunks get their own bounding boxes again, restricted to the page span of the original reference.

Available chunking strategies:

- `fixed_characters`
- `sentence`
- `paragraph`

Typical setup:

1. create a structured reference group for the guideline
2. create a chunking-result reference group from it, for example with `fixed_characters` and size `500`
3. use that chunking-result reference group as the basis for the vector collection

For the vector setup, see [example_vector_collection_ref_spec.json](./tests/assets/example_vector_collection_ref_spec.json).
That example is shaped for the collection-creation endpoint and includes the ingestion mapping used by the related reference-group ingestion endpoint.

- TODOs are to include the actual reference group ID
- And also: remove the `_related_ingest_reference_group_request_example`, this is for when actually filling the vector database

## Current scope

At the current stage, the backend provides:

- FastAPI application startup
- Swagger / OpenAPI documentation
- Keycloak-based authentication
- Role-based access control (`admin`, `study_user`)
- A development-only token endpoint (`/auth/token`)
- MongoDB interaction and PDF download for guideline entries
- A basic system/chat scaffolding (router + service + models) for the simplified setup
- Admin-only tool endpoints for:
    - Keyword extraction (YAKE, LLM, and comparison of both)
    - SNOMED CT lookup helpers (synonyms, canonical form, keyword expansion, medical keyword extraction)
    - LLM interaction sessions (create session with LLM settings, chat continuation via session id, history/reset)
    - Deletion functions and creation / update for workflows, guidelines, and references
    - Keyword enrichment for stored references / reference groups
    - Reference-group chunking for retrieval-source preparation
- Admin-only vector endpoints for:
    - Embedding via registered vectorizers
    - Creating Weaviate manual-vector collections
    - Inserting and searching vector objects

Full database integration, RAG pipelines, and evaluation logic will be added incrementally.

---

## Notes

- All configuration is provided via environment variables
- The backend is designed to run fully inside Docker
- Services are initialized once and injected via FastAPI dependencies

## Vector services

Two new backend services are available under the `knowledge/vector` slice:

- `EmbeddingService`: provider-backed text embeddings
- `WeaviateVectorStoreService`: Weaviate collection setup, insert, and search with stored metadata in MongoDB

An example collection setup is available in [example_vector_collection_ref_spec.json](./tests/assets/example_vector_collection_ref_spec.json).
It assumes that the chunking-result reference group already exists, for example a `fixed_characters` chunking with size `500`.
Whole-group ingestion creates chunk indices per guideline automatically. The ingest request can optionally target one guideline only, and
guideline-level replacement always restarts chunk indices at `0`.

For workflow orchestration, the matching ready-to-use workflow example
is [example_vector_retriever_workflow.json](./tests/assets/example_vector_retriever_workflow.json).
It is configured against the Weaviate collection `OpenSource_StructuredGuidelineFixedCharacters500_RefSpec`.
For multiple weighted searches against the same collection,
see [example_multi_queries_vector_retriever_workflow.json](./tests/assets/example_multi_queries_vector_retriever_workflow.json).

## SNOMED tool endpoints

The backend now exposes a separate SNOMED tool router under `/tools/snomed/*`:

- `POST /tools/snomed/versions`
- `POST /tools/snomed/synonyms`
- `POST /tools/snomed/canonical`
- `POST /tools/snomed/expand`
- `POST /tools/snomed/medical-keywords`

Each SNOMED request carries its own `llm_settings` in the JSON body. This is required because translation fallback and medical-keyword extraction run
through the configured LLM for that specific request.

The SNOMED instance can also be configured per request through `snomed_settings`, but useful defaults are now built in:

- `base_url`: `http://snomed-lite:8080/fhir`
- `version`: `http://snomed.info/sct/11000274103/version/20250515`
- `display_language_de`: `de`
- `display_language_en`: `en`

These defaults can be overridden via environment variables such as `SNOMED_BASE_URL`, or per request when needed.

Minimal example:

```json
{
  "term": "Blinddarmentzündung",
  "llm_settings": {
	"model": "gpt-4.1-mini",
	"api_key": "..."
  },
  "snomed_settings": {
	"base_url": "http://snomed-lite:8080/fhir"
  }
}
```

If you use the defaults, you can omit `snomed_settings` entirely and send only `term` plus `llm_settings`.

`POST /tools/snomed/versions` is useful for checking which SNOMED versions the configured server currently exposes. It first tries the FHIR
`CodeSystem` endpoint and falls back to `/metadata` if necessary.

## Reference keyword enrichment

The backend exposes two keyword-enrichment endpoints that write extracted keywords into `associated_keywords`:

- `POST /guideline_references/{reference_id}/keywords`
- `POST /guideline_references/groups/{reference_group_id}/keywords`

The group endpoint can optionally be restricted to a single `guideline_id`.

Extraction supports YAKE or LLM settings, and the extracted keywords can optionally be expanded via SNOMED before being stored.
