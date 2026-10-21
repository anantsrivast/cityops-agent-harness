"""The in-database embedder the notebooks hand to the Agent Memory store.

Embeddings are computed by an ONNX model loaded into the database itself
(``settings.embed_model``), so no embedding service or API key is involved and
the same model that indexes the store answers its queries.
"""

from __future__ import annotations

import asyncio

import numpy as np
from langchain_oracledb.embeddings.oracleai import OracleEmbeddings
from oracleagentmemory.apis.embedders.embedder import IEmbedder


class OracleONNXEmbedder(IEmbedder):
    """Agent Memory embedder backed by an ONNX model inside the database."""

    def __init__(self, conn, model_name: str):
        self.provider = OracleEmbeddings(
            conn=conn, params={"provider": "database", "model": model_name}
        )

    def embed(self, texts, *, is_query: bool = False):
        return np.asarray(self.provider.embed_documents(list(texts)), dtype=np.float32)

    async def embed_async(self, texts, *, is_query: bool = False):
        return await asyncio.to_thread(self.embed, texts, is_query=is_query)
