import os
import re
import time
from typing import Optional, List, Dict, Union
from urllib.parse import urlparse

import weaviate
from pymongo.synchronous.collection import Collection
from weaviate.classes.config import Configure, Property, VectorDistances
from weaviate.classes.query import TargetVectors, MetadataQuery, HybridFusion
from weaviate.collections.classes.filters import Filter
from weaviate.collections.classes.grpc import Sort

from app.exceptions.knowledge.vector.weaviate_interaction_exceptions import ChunkNotFoundError, MultipleChunksFoundError
from app.models.knowledge.vector.weaviate_related_models import (
    WeaviateCollection, WeaviateSearchResult, WeaviateSearchChunkResult, WeaviateProperty, WeaviateVectorizer, QueryWithSearchContribution,
)
from app.services.knowledge.vector import VectorizerService
from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


class WeaviateVectorDBService:
    def __init__(self, vector_dbs_collection: Collection, vectorizer_service: VectorizerService):
        self.vectorizer_service = vectorizer_service
        self.vector_dbs_collection = vector_dbs_collection
        
        weaviate_url = os.getenv("WEAVIATE_URL", "http://127.0.0.1:8081")
        grpc_weaviate_url = os.getenv("GRPC_WEAVIATE_URL", "http://127.0.0.1:50051")
        parsed = urlparse(weaviate_url)
        parsed_grpc = urlparse(grpc_weaviate_url)
        self.client = weaviate.connect_to_custom(
            http_host=parsed.hostname, http_port=parsed.port, http_secure=parsed.scheme == "https",
            grpc_host=parsed_grpc.hostname, grpc_port=parsed_grpc.port, grpc_secure=parsed_grpc.scheme == "https",
        )
        self.client.connect()
    
    @staticmethod
    def get_available_distance_metrics() -> List[str]:
        return [vd.value for vd in VectorDistances]
    
    def get_available_vectorizers(self) -> List[str]:
        return self.vectorizer_service.list_available_vectorizers()
    
    def create_collection(self, collection: WeaviateCollection):
        if not collection.collection_name[0].isupper():
            raise ValueError("Collection name must start with an uppercase letter")
        
        if self.client.collections.exists(collection.collection_name):
            raise ValueError(f"Collection '{collection.collection_name}' already exists")
        
        properties = [
            Property(name=p.name, data_type=p.data_type, description=p.description)
            for p in collection.properties
        ]
        vectorizer_properties = [v.vectorizer_property for v in collection.vectorizers]
        property_names = [p.name for p in collection.properties]
        assert all([p in property_names for p in vectorizer_properties])
        assert any([prop.name == "chunk_index" for prop in properties])
        assert any([prop.name == "reference_id" for prop in properties])
        assert any([prop.name == "guideline_id" for prop in properties])
        
        assert len(collection.vectorizers) > 0
        utilized_vectorizers = [v.embedder for v in collection.vectorizers]
        available_vectorizers = self.get_available_vectorizers()
        assert all([v in available_vectorizers for v in utilized_vectorizers])
        utilized_metrics = [v.distance_metric for v in collection.vectorizers]
        available_distance_metrics = self.get_available_distance_metrics()
        assert all([dm in available_distance_metrics for dm in utilized_metrics])
        
        vectorizer_config = [
            Configure.NamedVectors.none(
                name=v.name,
                vector_index_config=Configure.VectorIndex.hnsw(distance_metric=VectorDistances(v.distance_metric)),
            )
            for v in collection.vectorizers
        ]
        
        inserted_collection = self.client.collections.create(
            name=collection.collection_name,
            description=collection.description,
            properties=properties,
            vectorizer_config=vectorizer_config,
        )
        logger.info(f"Created collection: {collection.collection_name} ({inserted_collection.name})")
        
        self.vector_dbs_collection.insert_one(collection.model_dump(by_alias=True))
        logger.info(f"Created collection: {collection.collection_name}")
        return collection.collection_name
    
    def list_collections(self) -> List[WeaviateCollection]:
        collection_names = self.client.collections.list_all()
        collections = []
        for name in collection_names:
            config = self.client.collections.get(name).config.get()
            collections.append(self._format_weaviate_collection_config(config))
        return collections
    
    def get_collection_from_db(self, collection_name: str) -> Optional[WeaviateCollection]:
        doc = self.vector_dbs_collection.find_one({"collection_name": collection_name})
        if doc:
            return WeaviateCollection(**doc)
        else:
            raise ValueError(f"Collection '{collection_name}' not found in DB")
    
    def update_collection_in_db(self, collection: WeaviateCollection):
        self.vector_dbs_collection.update_one(
            {"collection_name": collection.collection_name},
            {"$set": collection.model_dump(by_alias=True)},
            upsert=True,
        )
    
    def delete_collection_from_db(self, collection_name: str):
        self.vector_dbs_collection.delete_one({"collection_name": collection_name})
    
    def _format_weaviate_collection_config(self, config) -> WeaviateCollection:
        logger.debug(f"Collection {config.name} config: {config}")
        name = config.name
        description = config.description or ""
        
        vectorizers = self.get_collection_from_db(name).vectorizers
        
        properties = [
            WeaviateProperty(name=prop.name, data_type=prop.data_type, description=prop.description)
            for prop in config.properties
        ]
        
        return WeaviateCollection(
            collection_name=name,
            description=description,
            vectorizers=vectorizers,
            properties=properties,
        )
    
    def get_collection(self, collection_name: str):
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        
        config = self.client.collections.get(collection_name).config.get()
        return self._format_weaviate_collection_config(config)
    
    def delete_collection(self, collection_name: str):
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        self.client.collections.delete(collection_name)
        self.delete_collection_from_db(collection_name)
        logger.info(f"Deleted collection: {collection_name}")
    
    def insert_chunk(self, collection_name: str, chunk: dict):
        self._validate_chunk(collection_name, chunk)
        
        props, empty_props = self._sanitize_chunk(chunk)
        if not props:
            raise ValueError("No properties to vectorize")
        
        logger.debug(props.keys())
        logger.debug(empty_props)
        
        vectors = self._vectorize_chunk(collection_name, props)
        
        collection = self.client.collections.get(collection_name)
        
        logger.debug([f'{k}: {v is None}' for k, v in vectors.items()])
        empty_str = "/"
        logger.debug(
            f"Attempt to insert: {chunk}, with vectors: {[f'{k}: {empty_str if v is None else v[:11]}...' for k, v in vectors.items()]} in {collection_name}"
            f", and empty handle for vectorizer properties: {empty_props.keys()}",
        )
        return collection.data.insert(properties=chunk, vector=vectors)
    
    def _find_chunk_id(self, collection_name: str, chunk: dict):
        collection = self.client.collections.get(collection_name)
        logger.debug(f"Searching for a chunk matching: {chunk}")
        
        def _is_emptyish(v) -> bool:
            if v is None:
                return True
            if isinstance(v, str):
                return len(v.strip()) == 0 or v == "__"
            if isinstance(v, (list, tuple, set, dict)):
                return len(v) == 0
            return False
        
        collection_props = {p.name for p in collection.config.get().properties}
        non_empty_props = [k for k in chunk.keys() if k in collection_props and not _is_emptyish(chunk[k])]
        empty_props = [k for k in chunk.keys() if k in collection_props and _is_emptyish(chunk[k])]
        
        if not non_empty_props and not empty_props:
            raise ValueError("None of the chunk's properties exist in the collection schema.")
        
        if not non_empty_props:
            raise ValueError("Cannot build dedup filter: all matching properties are empty.")
        filters = Filter.all_of(
            [
                Filter.by_property(prop).equal(chunk[prop]) for prop in non_empty_props
            ],
        )
        logger.debug(f"Filter: {filters}")
        results = collection.query.fetch_objects(filters=filters)
        
        objs = results.objects or []
        
        # Post-filter: ensure all properties that were empty in 'chunk' are empty/missing on the candidate too
        def _prop_empty_on_obj(obj, prop):
            return _is_emptyish((obj.properties or {}).get(prop))
        
        candidates = [o for o in objs if all(_prop_empty_on_obj(o, p) for p in empty_props)]
        
        if len(candidates) == 0:
            raise ChunkNotFoundError()
        if len(candidates) == 1:
            return candidates[0].uuid
        raise MultipleChunksFoundError(uuids=[o.uuid for o in candidates])
    
    def remove_chunk(self, collection_name: str, chunk: dict):
        collection = self.client.collections.get(collection_name)
        chunk_id = self._find_chunk_id(collection_name, chunk)
        collection.data.delete_by_id(chunk_id)
    
    def _validate_chunk(self, collection_name, chunk):
        collection = self.client.collections.get(collection_name)
        
        try:
            self._find_chunk_id(collection_name, chunk)
            raise ValueError(f"Chunk '{chunk}' already exists in collection '{collection_name}'")
        except ChunkNotFoundError:
            pass
        except MultipleChunksFoundError as e:
            raise ValueError(f"Multiple chunks similar to '{chunk}' already exist in collection '{collection_name}'")
        
        chunk_index = chunk["chunk_index"]
        filter_obj = Filter.by_property("chunk_index").equal(chunk_index)
        results = collection.query.fetch_objects(filters=filter_obj)
        
        if not results.objects or len(results.objects) == 0:
            logger.debug(f"Valid chunk index: {chunk_index} provided for collection {collection_name}")
            return chunk_index
        else:
            logger.error(f"Chunk with index '{chunk_index}' already exists in collection '{collection_name}'")
            raise ValueError(f"chunk_index '{chunk_index}' already exists in collection '{collection_name}'")
    
    @staticmethod
    def _sanitize_chunk(chunk):
        props = {}
        empty_props = {}
        for k, v in chunk.items():
            if isinstance(v, str):
                v = v.strip()
            if v is None or (isinstance(v, (str, list, tuple, set, dict)) and len(v) == 0):
                empty_props[k] = None
                continue
            else:
                props[k] = v
        return props, empty_props
    
    def _vectorize_chunk(self, collection_name: str, chunk):
        vectorizers: List[WeaviateVectorizer] = self.get_collection_from_db(collection_name).vectorizers
        vectors = {}
        for vectorizer in vectorizers:
            if chunk.get(vectorizer.vectorizer_property, None) is None:
                logger.warning(f"Empty vectorizer: {vectorizer.name} for chunk: {chunk} in collection: {collection_name}. Skipping vectorization.")
                continue
            else:
                vectors[vectorizer.name] = self.vectorizer_service.vectorize(
                    texts=[chunk.get(vectorizer.vectorizer_property)],
                    provider=vectorizer.embedder,
                )[0]
        return vectors
    
    def update_chunk(self, collection_name: str, original_chunk: dict, new_chunk: dict):
        chunk_id = self._find_chunk_id(collection_name, original_chunk)
        self._validate_chunk(collection_name, new_chunk)
        props, empty_props = self._sanitize_chunk(new_chunk)
        vectors = self._vectorize_chunk(collection_name, props)
        collection = self.client.collections.get(collection_name)
        
        return collection.data.update(uuid=chunk_id, properties=new_chunk, vector=vectors)
    
    @staticmethod
    def _parse_explain_score_fields(explain_score_str: str):
        # Extract original + normalized scores for both BM25 and vector
        bm25_raw = bm25_norm = vector_raw = vector_norm = None
        
        bm_match = re.search(r'keyword,bm25.*?original score ([\d.]+), normalized score: ([\d.]+)', explain_score_str)
        vec_match = re.search(r'vector,nearVector.*?original score ([\d.]+), normalized score: ([\d.]+)', explain_score_str)
        
        if bm_match:
            bm25_raw = float(bm_match.group(1))
            bm25_norm = float(bm_match.group(2))
        if vec_match:
            vector_raw = float(vec_match.group(1))
            vector_norm = float(vec_match.group(2))
        
        return bm25_raw, bm25_norm, vector_raw, vector_norm
    
    def single_query_search(
            self,
            collection_name: str,
            query: str,
            top_k: int,
            distance_threshold: Optional[float] = None,
            score_threshold: Optional[float] = None,
            overwrite_vectorizer_manual_weights: Optional[Dict[str, Union[float, int]]] = None,
            bm25_search_properties: Optional[List[str]] = None, alpha: Optional[float] = None,
    ) -> WeaviateSearchResult:
        if bm25_search_properties is not None and alpha is None:
            raise ValueError("Alpha must be provided when using BM25 search")
        if overwrite_vectorizer_manual_weights is None:
            overwrite_vectorizer_manual_weights = {}
        
        start = time.time()
        
        collection = self.client.collections.get(collection_name)
        vectorizers: List[WeaviateVectorizer] = self.get_collection_from_db(collection_name).vectorizers
        logger.debug(f"Loaded {len(vectorizers)} vectorizers from DB for collection '{collection_name}'")
        
        embedded_vectors = {}
        near_vector_dict = self._fill_empty_embedding_vectors(vectorizers)
        manual_weights_dict: Dict[str, Union[list, float]] = {v.name: 0.0 for v in vectorizers}
        
        for vect in vectorizers:
            key = vect.name
            weight = overwrite_vectorizer_manual_weights.get(key, vect.relevance_factor)
            if embedded_vectors.get((hash(query), vect.embedder), None) is None:
                embedded_vectors[(hash(query), vect.embedder)] = self.vectorizer_service.vectorize(texts=[query], provider=vect.embedder)[0]
                logger.debug(f"Vectorized query with vectorizer '{vect.embedder}' (property: {vect.vectorizer_property})")
            embedded_query = embedded_vectors[(hash(query), vect.embedder)]
            near_vector_dict[vect.name] = embedded_query
            manual_weights_dict[vect.name] = weight
        
        logger.debug(f"Prepared near_vector_dict with {len(near_vector_dict)} entries")
        logger.debug(f"Prepared manual_weights_dict: {manual_weights_dict}")
        
        if bm25_search_properties is None:
            bm25_search_properties = []
            alpha = 1.0
        
        logger.info(f"Using hybrid search with BM25 properties: {bm25_search_properties} and alpha: {alpha}...")
        search_result = collection.query.hybrid(
            query=query,
            query_properties=bm25_search_properties,
            alpha=alpha,
            vector=near_vector_dict,
            target_vector=TargetVectors.relative_score(manual_weights_dict),
            fusion_type=HybridFusion.RELATIVE_SCORE,
            limit=top_k,
            max_vector_distance=distance_threshold,
            return_metadata=MetadataQuery(score=True, explain_score=True),
        )
        results = self._parse_hybrid_search_result(search_result, score_threshold=score_threshold)
        
        duration = time.time() - start
        logger.info(f"Search completed in {duration:.2f} seconds")
        
        return WeaviateSearchResult(results=results, duration=duration)
    
    def multi_query_search(
            self,
            collection_name: str,
            queries: List[QueryWithSearchContribution],
            top_k: int,
            distance_threshold: Optional[float] = None,
            score_threshold: Optional[float] = None,
            bm25_query: Optional[str] = None,
            bm25_search_properties: Optional[List[str]] = None,
            alpha: Optional[float] = None,
    ) -> WeaviateSearchResult:
        if bm25_search_properties is not None and alpha is None:
            raise ValueError("Alpha must be provided when using BM25 search")
        
        logger.debug("=== multi_query_search start ===")
        logger.debug(
            f"Args: top_k={top_k}, distance_threshold={distance_threshold}, "
            f"score_threshold={score_threshold}, alpha={alpha}, "
            f"bm25_query_len={len(bm25_query or '')}, "
            f"bm25_props={bm25_search_properties}",
        )
        start = time.time()
        
        collection = self.client.collections.get(collection_name)
        vectorizers: List[WeaviateVectorizer] = self.get_collection_from_db(collection_name).vectorizers
        vect_by_name: Dict[str, WeaviateVectorizer] = {v.name: v for v in vectorizers}
        
        queries_grouped_by_vectorizer: Dict[str, List[QueryWithSearchContribution]] = {}
        for q in queries:
            if q.vectorizer_name not in vect_by_name:
                raise ValueError(f"Vectorizer '{q.vectorizer_name}' not found in collection '{collection_name}'")
            
            queries_grouped_by_vectorizer.setdefault(q.vectorizer_name, []).append(q)
        
        embedded_vectors = {}
        near_vector_dict = self._fill_empty_embedding_vectors(vectorizers)
        weights_dict: Dict[str, Union[list, float]] = {v.name: 0.0 for v in vectorizers}
        
        for vectorizer_name, queries_for_vectorizer in queries_grouped_by_vectorizer.items():
            vectorizer = vect_by_name[vectorizer_name]
            
            vectors, weights = [], []
            
            for query in queries_for_vectorizer:
                emb_vec_key = (hash(query.query), vectorizer.embedder)
                if embedded_vectors.get(emb_vec_key, None) is None:
                    embedded_vectors[emb_vec_key] = self.vectorizer_service.vectorize(texts=[query.query], provider=vectorizer.embedder)[0]
                    logger.debug(f"Vectorized query with vectorizer '{vectorizer.name}' (property: {vectorizer.vectorizer_property})")
                
                vectors.append(embedded_vectors[emb_vec_key])
                weights.append(query.query_weight)
            
            if len(queries_for_vectorizer) == 1:
                near_vector_dict[vectorizer.name] = vectors[0]
                weights_dict[vectorizer.name] = weights[0]
                logger.debug(
                    f"[Payload] target='{vectorizer_name}' num_vectors=1 "
                    f"weight={weights[0]} vec_dim={len(vectors[0])}",
                )
            else:
                near_vector_dict[vectorizer.name] = vectors
                weights_dict[vectorizer.name] = weights
                logger.debug(
                    f"[Payload] target='{vectorizer_name}' num_vectors={len(vectors)} "
                    f"weights={weights} vec_dims={[len(v) for v in vectors]}",
                )
        
        logger.debug(f"near_vector_dict keys: {list(near_vector_dict.keys())}")
        logger.debug(f"weights_dict keys: {list(weights_dict.items())}")
        
        if bm25_search_properties is None:
            bm25_query = bm25_query or ""
            bm25_search_properties = []
            alpha = 1.0
        
        logger.info(f"Using hybrid search with BM25 properties: {bm25_search_properties} and alpha: {alpha}...")
        search_result = collection.query.hybrid(
            query=bm25_query,
            query_properties=bm25_search_properties,
            alpha=alpha,
            vector=near_vector_dict,
            target_vector=TargetVectors.relative_score(weights_dict),
            fusion_type=HybridFusion.RELATIVE_SCORE,
            limit=top_k,
            max_vector_distance=distance_threshold,
            return_metadata=MetadataQuery(score=True, explain_score=True),
        )
        logger.debug(search_result)
        results = self._parse_hybrid_search_result(search_result, score_threshold=score_threshold)
        
        duration = time.time() - start
        logger.info(f"Search completed in {duration:.2f} seconds")
        return WeaviateSearchResult(results=results, duration=duration)
    
    def _fill_empty_embedding_vectors(self, vectorizers: List[WeaviateVectorizer]):
        empty_query = "NONE"
        embedded_vectors = {}
        empty_vector_dict = {}
        for v in vectorizers:
            embedded_vectors.setdefault(
                v.embedder,
                self.vectorizer_service.vectorize(texts=[empty_query], provider=v.embedder)[0],
            )
            empty_vector_dict[v.name] = embedded_vectors[v.embedder]
        return empty_vector_dict
    
    def _parse_hybrid_search_result(self, search_result, score_threshold: Optional[float] = None) -> List[WeaviateSearchChunkResult]:
        logger.info(f"Query executed. Retrieved {len(search_result.objects)} results")
        
        results = []
        for obj in search_result.objects:
            chunk = obj.properties
            metadata = obj.metadata
            explain_str = metadata.explain_score or ""
            
            # Parse scores
            bm25_raw, bm25_norm, vector_raw, vector_norm = self._parse_explain_score_fields(explain_str)
            hybrid_score = metadata.score
            
            # Build log message
            score_details = []
            if bm25_raw is not None:
                score_details.append(f"BM25: {bm25_raw:.4f} (norm: {bm25_norm:.4f})")
            if vector_raw is not None:
                score_details.append(f"Vector: {vector_raw:.4f} (norm: {vector_norm:.4f})")
            if hybrid_score is not None:
                score_details.append(f"→ Hybrid Score: {hybrid_score:.4f}")
            
            logger.debug(
                f"Found chunk with vector similarity score {hybrid_score:.4f}, chunk: {str(chunk)[:50]}... "
                f"[{'; '.join(score_details)}]",
            )
            
            if (score_threshold is not None) and (hybrid_score < score_threshold):
                logger.debug(f"Chunk score {hybrid_score:.4f} below threshold {score_threshold}, skipping")
                continue
            
            results.append(WeaviateSearchChunkResult(retrieved_chunk=chunk, score=metadata.score))
        return results
    
    def count_chunks(self, collection_name):
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        
        collection = self.client.collections.get(collection_name)
        count = collection.aggregate.over_all(total_count=True).total_count
        logger.debug(f"Counted {count} chunks in collection '{collection_name}'")
        return count
    
    def list_chunks_in_collection(
            self, collection_name, guideline_id: Optional[str] = None, chunk_index: Optional[int] = None, reference_id: Optional[str] = None,
    ) -> List[dict]:
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        
        def fetch_all_objects(filters, batch_size=25):
            collection = self.client.collections.get(collection_name)
            logger.info(f"Running search with filters: {filters}")
            all_objects = []
            offset = 0
            
            while True:
                response = collection.query.fetch_objects(
                    limit=batch_size, offset=offset, sort=Sort.by_property(name="chunk_index"),
                    filters=filters,
                )
                
                if not response.objects:
                    break
                
                all_objects.extend(response.objects)
                offset += batch_size
            
            return all_objects
        
        filter_list = []
        if guideline_id is not None:
            filter_list.append(Filter.by_property("guideline_id").equal(str(guideline_id)))
        if chunk_index is not None:
            filter_list.append(Filter.by_property("chunk_index").equal(int(chunk_index)))
        if reference_id is not None:
            filter_list.append(Filter.by_property("reference_id").equal(str(reference_id)))
        
        objects = fetch_all_objects(filters=Filter.all_of(filter_list) if filter_list else None)
        results = [obj.properties for obj in objects]
        
        logger.debug(
            f"Found {len(results)} chunks in collection '{collection_name}' matching query: "
            f"gl={guideline_id}, idx={chunk_index}, ref={reference_id}",
        )
        return results
    
    def average_len_chunk_property(self, collection_name: str, property_name: str) -> float:
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        
        collection = self.client.collections.get(collection_name)
        logger.info(f"Calculating average of property '{property_name}' in collection '{collection_name}'")
        
        # Fetch all objects in batches
        all_objects = []
        offset = 0
        batch_size = 25
        
        while True:
            response = collection.query.fetch_objects(
                limit=batch_size, offset=offset, sort=Sort.by_property(name="chunk_index"),
            )
            if not response.objects:
                break
            all_objects.extend(response.objects)
            offset += batch_size
        
        # Extract the target property values
        values = []
        for obj in all_objects:
            val = obj.properties.get(property_name)
            if isinstance(val, (int, float)):
                values.append(val)
            elif isinstance(val, (str, list)):
                values.append(len(val))
            else:
                logger.warning(f"Skipping object with invalid or missing '{property_name}' value: {val}")
        
        if not values:
            raise ValueError(f"No valid numeric values found for property '{property_name}' in collection '{collection_name}'")
        
        average = sum(values) / len(values)
        logger.debug(f"Average '{property_name}' in collection '{collection_name}': {average:.2f}")
        return average
    
    def find_by_reference_id(self, collection_name: str, reference_id) -> dict:
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        
        collection = self.client.collections.get(collection_name)
        
        filter_obj = Filter.by_property("reference_id").equal(reference_id)
        results = collection.query.fetch_objects(filters=filter_obj)
        
        if not results.objects or len(results.objects) == 0:
            raise ValueError(f"No chunk found with reference_id={reference_id} in collection '{collection_name}'")
        elif len(results.objects) > 1:
            raise ValueError(f"Multiple chunks found with reference_id={reference_id} in collection '{collection_name}'")
        
        return results.objects[0].properties
    
    def find_by_chunk_index(self, collection_name: str, chunk_index: int) -> dict:
        """
        Returns the single chunk with the given chunk_index in the specified collection.
        Raises an error if zero or multiple chunks are found.
        """
        if not self.client.collections.exists(collection_name):
            raise ValueError(f"Collection '{collection_name}' does not exist")
        
        collection = self.client.collections.get(collection_name)
        
        filter_obj = Filter.by_property("chunk_index").equal(chunk_index)
        results = collection.query.fetch_objects(filters=filter_obj)
        
        if not results.objects or len(results.objects) == 0:
            raise ValueError(f"No chunk found with chunk_index={chunk_index} in collection '{collection_name}'")
        elif len(results.objects) > 1:
            raise ValueError(f"Multiple chunks found with chunk_index={chunk_index} in collection '{collection_name}'")
        
        return results.objects[0].properties
