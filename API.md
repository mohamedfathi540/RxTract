# RxTract API Reference

This document describes the REST API endpoints available in RxTract.

Base URL: `http://localhost:8000/api/v1`

---

## Health Check

### GET /

Check if the API is running.

**Response**

```json
{
  "app_name": "RxTract",
  "app_version": "0.1"
}
```

---

## Data Management

### POST /data/upload/{project_id}

Upload a file for processing.

**Parameters**
| Name | Type | Location | Description |
|------|------|----------|-------------|
| project_id | integer | path | Project identifier |
| file | file | form-data | File to upload |

**Supported File Types**

- Plain text (.txt)
- PDF (.pdf)
- Markdown (.md)
- JSON (.json)
- CSV (.csv)
- Word documents (.docx)

**Response**

```json
{
  "signal": "FILE_UPLOADED",
  "file_id": "123"
}
```

---

### DELETE /data/asset/{project_id}/{file_id}

Remove an asset (and its chunks and vector rows) from the project. Use this when a file was deleted from disk or you want to unregister it.

**Parameters**
| Name       | Type    | Location | Description                                                                 |
| ---------- | ------- | -------- | --------------------------------------------------------------------------- |
| project_id | integer | path     | Project identifier                                                          |
| file_id    | string  | path     | Asset ID (integer as string) or asset name (e.g. `63p3infd9rrm_My_File.pdf`) |

**Response**

```json
{
  "signal": "Asset deleted",
  "asset_id": 123
}
```

Returns 404 with `"signal": "Asset not found"` if no asset matches.

---

### DELETE /data/project/{project_id}/assets

Remove **all** file assets (and their chunks and vector rows) from the project.

**Parameters**
| Name       | Type    | Location | Description          |
| ---------- | ------- | -------- | -------------------- |
| project_id | integer | path     | Project identifier   |

**Response**

```json
{
  "signal": "Assets deleted",
  "deleted_count": 5
}
```

Returns 404 with `"signal": "project not found"` if the project does not exist. If the project has no file assets, returns `deleted_count: 0`.

---

### POST /data/process/{project_id}

Process uploaded files into text chunks.

**Parameters**
| Name | Type | Location | Description |
|------|------|----------|-------------|
| project_id | integer | path | Project identifier |

**Request Body**

```json
{
  "chunk_size": 512,
  "overlap_size": 50,
  "Do_reset": 0,
  "file_id": "123"
}
```

| Field        | Type    | Default | Description                                          |
| ------------ | ------- | ------- | ---------------------------------------------------- |
| chunk_size   | integer | 100     | Size of each text chunk in characters                |
| overlap_size | integer | 20      | Overlap between consecutive chunks                   |
| Do_reset     | integer | 0       | Set to 1 to delete existing chunks before processing |
| file_id      | string  | null    | Process specific file, or all files if omitted       |

**Response**

```json
{
  "signal": "PROCESSING_DONE",
  "Inserted_chunks": 42,
  "processed_files": 1
}
```

---

## NLP and Vector Search

### POST /nlp/index/push/{project_id}

Index processed chunks into the vector database.

**Parameters**
| Name | Type | Location | Description |
|------|------|----------|-------------|
| project_id | integer | path | Project identifier |

**Request Body**

```json
{
  "do_reset": false
}
```

**Response**

```json
{
  "Signal": "INSERT_INTO_VECTOR_DB_DONE",
  "InsertedItemsCount": 42
}
```

---

### GET /nlp/index/info/{project_id}

Get information about the vector index.

**Parameters**
| Name | Type | Location | Description |
|------|------|----------|-------------|
| project_id | integer | path | Project identifier |

**Response**

```json
{
  "Signal": "GET_VECTOR_COLLECTION_INFO_DONE",
  "CollectionInfo": {
    "vectors_count": 42,
    "indexed_vectors_count": 42
  }
}
```

---

### POST /nlp/index/search/{project_id}

Perform semantic search on indexed documents.

**Parameters**
| Name | Type | Location | Description |
|------|------|----------|-------------|
| project_id | integer | path | Project identifier |

**Request Body**

```json
{
  "text": "What is machine learning?",
  "limit": 5
}
```

**Response**

```json
{
  "Signal": "SEARCH_INDEX_DONE",
  "Results": [
    {
      "text": "Machine learning is a subset of AI...",
      "score": 0.89
    }
  ]
}
```

---

### POST /nlp/index/answer/{project_id}

Get an AI-generated answer using RAG (Retrieval-Augmented Generation).

**Parameters**
| Name | Type | Location | Description |
|------|------|----------|-------------|
| project_id | integer | path | Project identifier |

**Request Body**

```json
{
  "text": "What is machine learning?",
  "limit": 5
}
```

**Response**

```json
{
  "Signal": "ANSWER_INDEX_DONE",
  "Answer": "Based on the documents, machine learning is...",
  "FullPrompt": "...",
  "ChatHistory": [...]
}
```

---

## Error Responses

All endpoints may return the following error responses:

| Status | Signal                      | Description                      |
| ------ | --------------------------- | -------------------------------- |
| 400    | FILE_TYPE_ERROR             | Unsupported file type            |
| 400    | FILE_SIZE_ERROR             | File exceeds maximum size        |
| 400    | FILE_ID_ERROR               | File ID not found                |
| 400    | NO_FILE_ERROR               | No files to process              |
| 400    | PROCESSING_FAILED           | File processing failed           |
| 404    | PROJECT_NOT_FOUND           | Project does not exist           |
| 500    | INSERT_INTO_VECTOR_DB_ERROR | Vector database insertion failed |
