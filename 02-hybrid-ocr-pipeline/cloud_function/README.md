# Hybrid OCR Cloud Function

This Cloud Function automatically processes PDFs uploaded to Google Cloud Storage using a hybrid OCR approach:
1. **Document AI** as primary OCR (fast, cost-effective)
2. **Gemini Vision API** as fallback for difficult pages (better accuracy)
3. **Gemini Embeddings** to create vector embeddings
4. **Pinecone** to store embeddings for semantic search

## Features

- ✅ Automatic processing when files are uploaded to GCS
- ✅ Hybrid OCR: Document AI + Gemini Vision for maximum accuracy
- ✅ Batch embedding for efficient Pinecone storage
- ✅ Rate limit handling and retry logic
- ✅ Confidence-based quality scoring
- ✅ Support for multi-page PDFs
- ✅ Urdu/Arabic text support

## Setup

1. Follow the main documentation: `DOCUMENT_AI_HYBRID_OCR_CLOUD_FUNCTION.md`

2. Set environment variables when deploying:
   - `DOCUMENT_AI_PROCESSOR_ID`: Your Document AI processor ID
   - `DOCUMENT_AI_LOCATION`: Location (us, eu, etc.)
   - `PINECONE_INDEX_NAME`: Your Pinecone index name
   - `SECRET_PINECONE_API_KEY`: Secret name for Pinecone API key
   - `SECRET_GEMINI_API_KEY`: Secret name for Gemini API key

3. Deploy the function:
   ```bash
   cd gcf-docai-ocr
   gcloud functions deploy docai-ocr-pipeline \
     --gen2 \
     --runtime=python311 \
     --region=us-central1 \
     --source=. \
     --entry-point=on_gcs_event \
     --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
     --trigger-event-filters="bucket=YOUR_BUCKET_NAME" \
     --service-account="docai-pipeline@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --set-env-vars="DOCUMENT_AI_PROCESSOR_ID=YOUR_PROCESSOR_ID,DOCUMENT_AI_LOCATION=us,PINECONE_INDEX_NAME=documents,SECRET_PINECONE_API_KEY=PINECONE_API_KEY,SECRET_GEMINI_API_KEY=GEMINI_API_KEY"
   ```

## Configuration

You can adjust these settings in `main.py`:

- `MAX_WORKERS`: Number of parallel Document AI workers (default: 10)
- `PAGES_PER_CHUNK`: Pages per Document AI request (default: 15)
- `USE_GEMINI_FOR_LOW_QUALITY`: Enable Gemini fallback (default: True)
- `QUALITY_THRESHOLD`: Confidence threshold for Gemini (default: 0.7)
- `EMBEDDING_BATCH_SIZE`: Batch size for embeddings (default: 150)
- `GEMINI_MODEL`: Gemini model to use (default: "gemini-2.5-pro")

## How It Works

1. **File Upload**: When a PDF is uploaded to the configured GCS bucket, the function is triggered
2. **Document AI Processing**: PDF is split into chunks and processed with Document AI
3. **Quality Check**: Pages with low confidence scores are re-processed with Gemini Vision
4. **Embedding**: All pages are embedded using Gemini embeddings and stored in Pinecone
5. **Metadata**: Each page includes metadata (source file, page number, method used)

## Output

- Text is extracted and embedded in Pinecone
- Each page is stored as a separate vector with metadata
- Logs show processing statistics and any errors

## Troubleshooting

- Check Cloud Function logs for detailed error messages
- Verify all secrets are stored in Secret Manager
- Ensure service account has required permissions
- Check Pinecone index dimensions match embedding model (768 for gemini-embedding-001)

