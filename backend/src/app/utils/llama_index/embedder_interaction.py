import os

import torch
from FlagEmbedding import BGEM3FlagModel
from llama_index.core.base.embeddings.base import BaseEmbedding, Embedding
from openai import AzureOpenAI, OpenAI
from transformers import AutoModel


class OpenAI3LargeEmbedder(BaseEmbedding):
    def __init__(self):
        super().__init__()
        self.api_type = os.getenv("OPEN_AI_TYPE", "")
        self.api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        self.api_base = os.getenv("AZURE_OPENAI_API_BASE", "")
        self.api_version = "2024-08-01-preview"
        self.deployment_name = "text-embedding-3-large"
        
        if not all([self.api_key, self.deployment_name]):
            raise ValueError("Missing Azure OpenAI configuration environment variables")
        
        if self.api_type == "azure":
            self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        else:
            self.client = OpenAI(api_key=self.api_key)
    
    def _get_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    async def _aget_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    def _get_text_embedding(self, text: str) -> Embedding:
        response = self.client.embeddings.create(
            model=self.deployment_name,
            input=[text],
        )
        return [item.embedding for item in response.data][0]


class BAAILLMEmbedder(BaseEmbedding):
    def __init__(self):
        super().__init__()
        model_name: str = "BAAI/embedder"
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
    
    def _get_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    async def _aget_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    def _get_text_embedding(self, text: str) -> Embedding:
        inputs = self.tokenizer(
            [text],
            padding=True,
            truncation=True,
            return_tensors="pt",
        ).to(self.device)
        
        # Forward pass to get model outputs
        with torch.no_grad():
            outputs = self.model(**inputs)
            embeddings = outputs.last_hidden_state[:, 0]  # CLS token
        
        embeddings = embeddings.cpu().numpy().tolist()
        return embeddings[0]


class BAAIBilingualGeneralEmbedderM3(BaseEmbedding):
    def __init__(self):
        super().__init__()
        model_name: str = "BAAI/bge-m3"
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = BGEM3FlagModel(model_name, use_fp16=False)
    
    def _get_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    async def _aget_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    def _get_text_embedding(self, text: str) -> Embedding:
        outputs = self.model.encode(
            [text],
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense_vecs = outputs["dense_vecs"]
        if hasattr(dense_vecs, "tolist"):
            return dense_vecs.tolist()[0]
        else:
            return [float(v) for v in dense_vecs[0]]


class BAAIBilingualGeneralRerankerLarge(BaseEmbedding):
    def __init__(self):
        super().__init__()
        model_name: str = "BAAI/bge-reranker-large"
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = BGEM3FlagModel(model_name, use_fp16=False)
    
    def _get_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    async def _aget_query_embedding(self, query: str) -> Embedding:
        return self._get_text_embedding(query)
    
    def _get_text_embedding(self, text: str) -> Embedding:
        outputs = self.model.encode(
            [text],
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        dense_vecs = outputs["dense_vecs"]
        if hasattr(dense_vecs, "tolist"):
            return dense_vecs.tolist()[0]
        else:
            return [float(v) for v in dense_vecs[0]]
