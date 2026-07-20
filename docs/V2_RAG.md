# Version 2.0.1 Project Knowledge RAG

Project Knowledge is the only supported RAG corpus. `docs/PROJECT_KNOWLEDGE.md` is the reviewed Git baseline; production uses a separate runtime file and PostgreSQL index.

Analyze accepts `use_project_knowledge` and `project_knowledge_top_k`. Top-k defaults to 5 and is clamped to 1–10. When disabled, the backend does no retrieval and returns `used_knowledge_base=false`, `retrieval_count=0`, and `rag_sources=[]`.

When enabled, the backend builds a bounded query from sanitized Resume and JD text, locates the one Project Knowledge document, retrieves PostgreSQL FTS chunks using `websearch_to_tsquery`/`ts_rank`, scans the chunks, and places only retrieved content in `TRUSTED_PROJECT_EVIDENCE`. Resume uses `USER_PROVIDED_RESUME`; pasted/fetched JD remains `UNTRUSTED_JOB_DESCRIPTION`.

The model cannot define source metadata. The backend returns only:

```json
{
  "document": "PROJECT_KNOWLEDGE.md",
  "section": "RAG architecture",
  "chunk_id": 7,
  "relevance_score": 0.82,
  "supported_skills": ["PostgreSQL"]
}
```

Skill synonyms improve retrieval only. A matched skill still requires direct Resume or retrieved-chunk text. Backend reconciliation moves supported Project Knowledge skills out of `missing_skills`, labels their evidence source, removes unsupported matched skills, and blocks unsupported generated letter claims.

Replacement requires runtime hash and backup, reviewed comparison, atomic file installation, chunk/index rebuild, status and search validation, then fictional Analyze checks with RAG off and on. Empty retrieval degrades safely without invented evidence.
