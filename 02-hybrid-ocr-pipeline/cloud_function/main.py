"""
Hybrid OCR Cloud Function: Document AI + Gemini Vision API
==========================================================

This Cloud Function automatically processes PDFs uploaded to GCS:
1. Uses Document AI as primary OCR (fast, cost-effective)
2. Uses Gemini Vision API as fallback for difficult pages (better accuracy)
3. Chunks text and generates embeddings using Gemini
4. Stores embeddings in Pinecone for semantic search

Trigger: Cloud Storage object finalized event
"""

import os
import io
import time
import logging
from typing import Dict, List, Optional
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Google Cloud imports
from google.cloud import storage, documentai_v1 as documentai
from google.api_core.exceptions import GoogleAPICallError

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PDF processing
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image

# pdf2image is optional - requires poppler system dependency
try:
    import pdf2image
    PDF2IMAGE_AVAILABLE = True
except (ImportError, OSError):
    # OSError can occur if poppler is not installed
    PDF2IMAGE_AVAILABLE = False
    logger.warning("⚠️ pdf2image not available. Gemini Vision fallback will be disabled.")

# Gemini and embeddings
import google.generativeai as genai

# Lazy imports for Pinecone/LangChain to avoid import errors at module load time
GoogleGenerativeAIEmbeddings = None
PineconeVectorStore = None
Document = None
Pinecone = None

def _lazy_import_langchain():
    """Lazy import LangChain and Pinecone components."""
    global GoogleGenerativeAIEmbeddings, PineconeVectorStore, Document, Pinecone
    if GoogleGenerativeAIEmbeddings is None:
        try:
            # Workaround for deprecated plugin error
            # The check happens in pinecone.__init__, so we need to patch before import
            import sys
            import types
            import importlib.util
            
            # Monkey-patch the deprecated_plugins module before pinecone imports it
            class MockDeprecatedPlugins(types.ModuleType):
                @staticmethod
                def check_for_deprecated_plugins():
                    # Do nothing - suppress the deprecation check
                    pass
            
            # Install the mock before pinecone is imported
            mock_module = MockDeprecatedPlugins('pinecone.deprecated_plugins')
            sys.modules['pinecone.deprecated_plugins'] = mock_module
            
            # Now import pinecone - it should use our mocked module
            from pinecone import Pinecone
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            from langchain_pinecone import PineconeVectorStore
            from langchain.docstore.document import Document
        except Exception as e:
            error_msg = str(e)
            if "DeprecatedPluginError" in error_msg or "pinecone-plugin-inference" in error_msg:
                logger.error("❌ Pinecone deprecated plugin error detected.")
                logger.error("   The pinecone-plugin-inference package needs to be removed.")
                logger.error("   This is a known issue with older pinecone-client versions.")
            logger.error(f"Failed to import LangChain/Pinecone components: {e}")
            raise

# ==================== CONFIGURATION ====================
# Get settings from environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
PROCESSOR_ID = os.environ["DOCUMENT_AI_PROCESSOR_ID"]
PROCESSOR_LOCATION = os.environ.get("DOCUMENT_AI_LOCATION", "us")
PINECONE_INDEX_NAME = os.environ["PINECONE_INDEX_NAME"]
PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Processing settings
MAX_WORKERS = 10
PAGES_PER_CHUNK = 15  # Document AI limit
MAX_RETRIES = 5
REQUEST_TIMEOUT = 300  # 5 minutes

# Gemini Vision settings
# Only enable if pdf2image is available (requires poppler system dependency)
USE_GEMINI_FOR_LOW_QUALITY = PDF2IMAGE_AVAILABLE
QUALITY_THRESHOLD = 0.7  # Confidence threshold below which to use Gemini
GEMINI_MODEL = "gemini-2.5-pro"  # or "gemini-1.5-pro", "gemini-1.5-flash"

# Embedding settings
EMBEDDING_BATCH_SIZE = 150
EMBEDDING_DELAY = 0.2  # Delay between batch calls
EMBEDDING_MAX_RETRIES = 6
EMBEDDING_RETRY_DELAY = 2

# ==================== LAZY INITIALIZATION ====================
# Global variables for lazy initialization
_storage_client = None
_docai_client = None
_pc_client = None
_gemini_embeddings = None
_vectorstore = None
_gemini_model = None
_embedding_manager = None

def initialize_clients():
    """Initialize all clients lazily."""
    global _storage_client, _docai_client
    global _pc_client, _gemini_embeddings, _vectorstore, _gemini_model
    
    if _storage_client is None:
        _storage_client = storage.Client(project=PROJECT_ID)
    
    if _docai_client is None:
        _docai_client = documentai.DocumentProcessorServiceClient()
    
    # Initialize Pinecone and embeddings only if not already done
    if _vectorstore is None:
        try:
            # Lazy import LangChain components
            _lazy_import_langchain()
            
            _pc_client = Pinecone(api_key=PINECONE_API_KEY)
            _gemini_embeddings = GoogleGenerativeAIEmbeddings(
                model="models/gemini-embedding-001",
                google_api_key=GEMINI_API_KEY
            )
            _vectorstore = PineconeVectorStore(
                index=_pc_client.Index(PINECONE_INDEX_NAME),
                embedding=_gemini_embeddings
            )
            logger.info("✅ Pinecone and embeddings initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Pinecone/embeddings: {e}")
            raise
    
    # Initialize Gemini Vision model only if not already done
    if _gemini_model is None:
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
            logger.info(f"✅ Gemini Vision API initialized with model: {GEMINI_MODEL}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to initialize Gemini model {GEMINI_MODEL}: {e}")
            # Try alternative models
            alternative_models = ["gemini-2.0-pro", "gemini-1.5-pro", "gemini-1.5-flash"]
            for alt_model in alternative_models:
                try:
                    _gemini_model = genai.GenerativeModel(alt_model)
                    logger.info(f"✅ Using alternative Gemini model: {alt_model}")
                    break
                except:
                    continue
            if not _gemini_model:
                logger.warning("⚠️ Could not initialize any Gemini model. Will use Document AI only.")
    
    return _storage_client, _docai_client, _vectorstore, _gemini_model

# ==================== BATCH EMBEDDING MANAGER ====================
class BatchEmbeddingManager:
    """Manages batch embedding to improve performance and respect rate limits."""
    def __init__(self, batch_size=EMBEDDING_BATCH_SIZE):
        self.batch_size = batch_size
        self.batch = []
        self.embedded_count = 0
        self.failed_count = 0
    
    def add_page(self, page_text: str, page_num: int, source_file: str = None):
        """Add a page to the batch. Embeds automatically when batch is full."""
        global _vectorstore
        if _vectorstore is None or not page_text or not page_text.strip():
            return False
        
        # Extract book name
        if source_file:
            book_name = source_file.replace(".pdf", "").replace(".PDF", "")
        else:
            book_name = "unknown"
        
        # Create Document (ensure LangChain is imported)
        _lazy_import_langchain()
        doc = Document(
            page_content=page_text,
            metadata={
                "bookname": book_name,
                "page": page_num,
                "page_number": page_num,
                "source_file": source_file or "unknown",
                "method": "hybrid_ocr"
            }
        )
        
        self.batch.append(doc)
        
        # Embed batch when it reaches batch_size
        if len(self.batch) >= self.batch_size:
            return self._embed_batch()
        
        return True
    
    def _embed_batch(self, max_retries=None, retry_delay=None):
        """Embed the current batch with retry logic."""
        if not self.batch:
            return True
        
        if max_retries is None:
            max_retries = EMBEDDING_MAX_RETRIES
        if retry_delay is None:
            retry_delay = EMBEDDING_RETRY_DELAY
        
        batch_to_embed = self.batch.copy()
        self.batch = []  # Clear batch
        
        for attempt in range(1, max_retries + 1):
            try:
                # Add delay between batch embedding calls
                if attempt > 1:
                    delay = retry_delay * (2 ** (attempt - 2))
                    logger.info(f"   Retrying batch embedding (attempt {attempt}/{max_retries}) after {delay}s...")
                    time.sleep(delay)
                elif hasattr(BatchEmbeddingManager, '_last_batch_time'):
                    elapsed = time.time() - BatchEmbeddingManager._last_batch_time
                    if elapsed < EMBEDDING_DELAY:
                        time.sleep(EMBEDDING_DELAY - elapsed)
                
                # Embed batch
                global _vectorstore
                _vectorstore.add_documents(batch_to_embed)
                BatchEmbeddingManager._last_batch_time = time.time()
                
                self.embedded_count += len(batch_to_embed)
                logger.info(f"✅ Embedded batch of {len(batch_to_embed)} pages in Pinecone (total: {self.embedded_count} pages)")
                return True
                
            except Exception as e:
                error_str = str(e)
                
                # Check for rate limit errors (429)
                if "429" in error_str or "quota" in error_str.lower() or "rate limit" in error_str.lower():
                    if attempt < max_retries:
                        delay = retry_delay * (2 ** (attempt - 1))
                        if not hasattr(BatchEmbeddingManager, '_rate_limit_logged'):
                            logger.warning(f"⚠️ Rate limit hit for batch embeddings. Retrying with exponential backoff...")
                            BatchEmbeddingManager._rate_limit_logged = True
                        time.sleep(delay)
                        continue
                    else:
                        if not hasattr(BatchEmbeddingManager, '_rate_limit_final_logged'):
                            logger.error(f"❌ Rate limit exceeded for batch embeddings after {max_retries} retries")
                            logger.error(f"   {len(batch_to_embed)} pages failed to embed")
                            BatchEmbeddingManager._rate_limit_final_logged = True
                        self.failed_count += len(batch_to_embed)
                        return False
                
                # Other errors
                else:
                    if attempt < max_retries:
                        logger.warning(f"⚠️ Batch embedding failed (attempt {attempt}/{max_retries}): {e}")
                        continue
                    else:
                        logger.error(f"❌ Batch embedding failed after {max_retries} attempts: {e}")
                        self.failed_count += len(batch_to_embed)
                        return False
        
        return False
    
    def flush(self):
        """Embed any remaining pages in the batch."""
        if self.batch:
            return self._embed_batch()
        return True
    
    def get_stats(self):
        """Get embedding statistics."""
        return {
            "embedded": self.embedded_count,
            "failed": self.failed_count,
            "pending": len(self.batch)
        }

def initialize_embedding_manager():
    """Initialize the global batch embedding manager."""
    global _embedding_manager, _vectorstore
    if _vectorstore:
        _embedding_manager = BatchEmbeddingManager(batch_size=EMBEDDING_BATCH_SIZE)
        logger.info(f"✅ Batch embedding manager initialized (batch_size: {EMBEDDING_BATCH_SIZE})")
    return _embedding_manager

def embed_page_in_pinecone(page_text: str, page_num: int, source_file: str = None):
    """Add a page to the batch embedding queue."""
    global _embedding_manager
    
    if _embedding_manager is None:
        initialize_embedding_manager()
    
    if _embedding_manager:
        return _embedding_manager.add_page(page_text, page_num, source_file)
    
    return False

# ==================== HELPER FUNCTIONS ====================
def pdf_page_to_image(pdf_bytes: bytes, page_num: int) -> Optional[Image.Image]:
    """Convert a single PDF page to PIL Image."""
    if not PDF2IMAGE_AVAILABLE:
        logger.warning("pdf2image not available - cannot convert PDF to image")
        return None
    
    try:
        images = pdf2image.convert_from_bytes(
            pdf_bytes, 
            first_page=page_num+1, 
            last_page=page_num+1, 
            dpi=300
        )
        return images[0] if images else None
    except Exception as e:
        logger.error(f"Error converting page {page_num} to image: {e}")
        return None

def extract_text_from_layout(layout, doc_text: str) -> Optional[str]:
    """Extract text from a layout element."""
    if not hasattr(layout, "text_anchor") or not layout.text_anchor:
        return None
    
    segments = layout.text_anchor.text_segments
    if not segments:
        return None
    
    valid_starts = [seg.start_index for seg in segments if seg.start_index is not None]
    valid_ends = [seg.end_index for seg in segments if seg.end_index is not None]
    
    if not valid_starts or not valid_ends:
        return None
    
    return doc_text[min(valid_starts):max(valid_ends)]

def calculate_confidence_score(doc, page) -> float:
    """Calculate confidence score for Document AI OCR result."""
    if not doc.text:
        return 0.0
    
    has_blocks = hasattr(page, "blocks") and page.blocks
    has_paragraphs = hasattr(page, "paragraphs") and page.paragraphs
    
    confidence = 0.5  # Base confidence
    if has_blocks:
        confidence += 0.2
    if has_paragraphs:
        confidence += 0.2
    
    page_text = extract_text_from_layout(page.layout, doc.text) if hasattr(page, "layout") and page.layout else ""
    if page_text and len(page_text) > 100:
        confidence += 0.1
    
    return min(confidence, 1.0)

# ==================== DOCUMENT AI PROCESSING ====================
def parse_documentai_doc(doc, start_page: int = 1) -> List[Dict]:
    """Extract text from Document AI response with confidence scores."""
    parsed_pages = []
    for idx, page in enumerate(doc.pages):
        global_page_num = start_page + idx
        page_text = ""
        confidence = 0.0
        
        confidence = calculate_confidence_score(doc, page)
        
        if doc.text and hasattr(page, "layout") and page.layout:
            page_text = extract_text_from_layout(page.layout, doc.text)
        
        if not page_text and hasattr(page, "blocks") and page.blocks:
            block_texts = []
            for block in page.blocks:
                if hasattr(block, "layout") and block.layout:
                    block_text = extract_text_from_layout(block.layout, doc.text)
                    if block_text and block_text.strip():
                        block_texts.append(block_text)
            if block_texts:
                page_text = "\n\n".join(block_texts)
        
        if not page_text.strip():
            page_text = "[BLANK PAGE]"
        else:
            # Clean up
            lines = page_text.split('\n')
            cleaned_lines = []
            prev_empty = False
            for line in lines:
                if line.strip():
                    cleaned_lines.append(line)
                    prev_empty = False
                elif not prev_empty:
                    cleaned_lines.append('')
                    prev_empty = True
            while cleaned_lines and not cleaned_lines[-1]:
                cleaned_lines.pop()
            page_text = '\n'.join(cleaned_lines)
        
        parsed_pages.append({
            'page_num': global_page_num,
            'text': page_text,
            'confidence': confidence,
            'method': 'documentai'
        })
    
    return parsed_pages

def process_pdf_chunk_with_documentai(chunk_bytes: bytes, start_page: int = 1, chunk_id: int = 0) -> tuple:
    """Process PDF chunk with Document AI."""
    global _docai_client
    client_options = {"api_endpoint": f"{PROCESSOR_LOCATION}-documentai.googleapis.com"}
    client = documentai.DocumentProcessorServiceClient(client_options=client_options)
    processor_name = client.processor_path(PROJECT_ID, PROCESSOR_LOCATION, PROCESSOR_ID)

    raw_doc = documentai.RawDocument(content=chunk_bytes, mime_type="application/pdf")
    request = documentai.ProcessRequest(name=processor_name, raw_document=raw_doc)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            doc = client.process_document(request=request, timeout=REQUEST_TIMEOUT).document
            if not doc or not doc.text:
                raise ValueError("Empty document response")
            
            pages = parse_documentai_doc(doc, start_page=start_page)
            return pages, chunk_id
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = min(2 ** attempt, 10)
                logger.warning(f"⚠️ Document AI attempt {attempt} failed: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"❌ Document AI failed after {MAX_RETRIES} retries: {e}")
                return None, chunk_id
    
    return None, chunk_id

# ==================== GEMINI VISION OCR ====================
def ocr_with_gemini_vision(image: Image.Image, page_num: int) -> tuple:
    """OCR a page using Gemini Vision API."""
    global _gemini_model
    if not _gemini_model:
        return None, 0.0
    
    try:
        prompt = """Extract all text from this image. 
The text is in Urdu/Arabic (right-to-left) and may also contain English.
Preserve the exact formatting, line breaks, and alignment.
Output the text exactly as it appears, maintaining proper RTL structure.
Do not translate or summarize, just extract the text."""
        
        try:
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            
            generation_config = genai.types.GenerationConfig(
                temperature=0.1,
                top_p=0.95,
                top_k=40,
                max_output_tokens=8192,
            )
            
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
            
            response = _gemini_model.generate_content(
                [prompt, image],
                generation_config=generation_config,
                safety_settings=safety_settings
            )
        except (ImportError, AttributeError) as config_error:
            try:
                generation_config = {
                    "temperature": 0.1,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }
                response = _gemini_model.generate_content(
                    [prompt, image],
                    generation_config=generation_config
                )
            except Exception:
                logger.warning(f"⚠️ Config error, trying without config: {config_error}")
                response = _gemini_model.generate_content([prompt, image])
        
        if response:
            text = None
            
            if hasattr(response, 'text') and response.text:
                text = response.text.strip()
            elif hasattr(response, 'candidates') and response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    if candidate.content.parts and len(candidate.content.parts) > 0:
                        if hasattr(candidate.content.parts[0], 'text'):
                            text = candidate.content.parts[0].text.strip()
                elif hasattr(candidate, 'text'):
                    text = candidate.text.strip()
                elif hasattr(candidate, 'output'):
                    text = str(candidate.output).strip()
            
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    logger.warning(f"⚠️ Gemini blocked page {page_num}: {feedback.block_reason}")
                    return None, 0.0
            
            if text:
                confidence = min(len(text) / 1000.0, 1.0) if text else 0.0
                logger.info(f"✅ Gemini OCR completed for page {page_num} ({len(text)} chars)")
                return text, confidence
            else:
                logger.warning(f"⚠️ Gemini returned empty response for page {page_num}")
                return None, 0.0
        else:
            logger.warning(f"⚠️ Gemini returned no response for page {page_num}")
            return None, 0.0
            
    except Exception as e:
        logger.error(f"❌ Gemini OCR error for page {page_num}: {e}")
        return None, 0.0

# ==================== HYBRID PROCESSING ====================
def process_page_hybrid(pdf_bytes: bytes, page_num: int, docai_result: Dict = None) -> Dict:
    """Process a single page using hybrid approach."""
    global _gemini_model
    page_result = {
        'page_num': page_num,
        'text': '',
        'method': 'none',
        'confidence': 0.0
    }
    
    if docai_result:
        page_result['text'] = docai_result['text']
        page_result['confidence'] = docai_result['confidence']
        page_result['method'] = 'documentai'
        
        if USE_GEMINI_FOR_LOW_QUALITY and _gemini_model:
            if docai_result['confidence'] < QUALITY_THRESHOLD:
                logger.info(f"📊 Page {page_num} confidence ({docai_result['confidence']:.2f}) below threshold, trying Gemini...")
                image = pdf_page_to_image(pdf_bytes, page_num - 1)
                if image:
                    gemini_text, gemini_conf = ocr_with_gemini_vision(image, page_num)
                    if gemini_text and gemini_conf > docai_result['confidence']:
                        page_result['text'] = gemini_text
                        page_result['confidence'] = gemini_conf
                        page_result['method'] = 'gemini'
                        logger.info(f"✅ Page {page_num} improved with Gemini (conf: {gemini_conf:.2f})")
    else:
        if _gemini_model:
            logger.info(f"📄 Page {page_num} not processed by Document AI, trying Gemini...")
            image = pdf_page_to_image(pdf_bytes, page_num - 1)
            if image:
                gemini_text, gemini_conf = ocr_with_gemini_vision(image, page_num)
                if gemini_text:
                    page_result['text'] = gemini_text
                    page_result['confidence'] = gemini_conf
                    page_result['method'] = 'gemini'
    
    return page_result

def split_pdf_bytes(pdf_bytes: bytes, pages_per_chunk: int = PAGES_PER_CHUNK) -> tuple:
    """Split PDF into chunks."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)
    chunks = []

    for i in range(0, total_pages, pages_per_chunk):
        writer = PdfWriter()
        for page_num in range(i, min(i + pages_per_chunk, total_pages)):
            writer.add_page(reader.pages[page_num])
        chunk_stream = io.BytesIO()
        writer.write(chunk_stream)
        chunk_stream.seek(0)
        chunks.append((chunk_stream.read(), i + 1, i // pages_per_chunk))
    return chunks, total_pages

# ==================== MAIN CLOUD FUNCTION ====================
def on_gcs_event(event: Dict, context) -> str:
    """
    Cloud Function entry point triggered by GCS object finalized event.
    
    Args:
        event: Event payload containing bucket and object name
        context: Function execution context
    
    Returns:
        str: Status message
    """
    start_time = time.time()
    bucket_name = event["bucket"]
    object_name = event["name"]
    
    logger.info("=" * 60)
    logger.info(f"Starting Hybrid OCR: {object_name}")
    logger.info("=" * 60)
    
    try:
        # Initialize clients (lazy loading)
        storage_client, docai_client, vectorstore, gemini_model = initialize_clients()
        
        # Download PDF
        logger.info(f"Downloading {object_name} from {bucket_name}")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        if not blob.exists():
            logger.error(f"❌ File {object_name} not found in bucket {bucket_name}")
            return f"ERROR: File not found"
        
        pdf_bytes = blob.download_as_bytes()
        logger.info(f"✅ Downloaded PDF ({len(pdf_bytes)//1024} KB)")

        # Split into chunks
        chunks, total_pages = split_pdf_bytes(pdf_bytes)
        logger.info(f"📄 Split PDF into {len(chunks)} chunks ({PAGES_PER_CHUNK} pages per chunk, {total_pages} total pages)")

        # Step 1: Process all chunks with Document AI
        logger.info("\n🚀 Step 1: Processing with Document AI...")
        docai_results = OrderedDict()
        completed_count = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_pdf_chunk_with_documentai, c[0], c[1], c[2]): c[2]
                for c in chunks
            }
            
            for future in as_completed(futures):
                chunk_id = futures[future]
                try:
                    pages, _ = future.result()
                    if pages:
                        for page in pages:
                            docai_results[page['page_num']] = page
                            # Embed page in Pinecone immediately after OCR
                            embed_page_in_pinecone(page['text'], page['page_num'], object_name)
                        completed_count += 1
                        logger.info(f"✅ Chunk {chunk_id + 1}/{len(chunks)} completed ({completed_count}/{len(chunks)} total)")
                except Exception as e:
                    logger.error(f"❌ Chunk {chunk_id + 1} failed: {e}")

        # Step 2: Process low-quality pages with Gemini
        if USE_GEMINI_FOR_LOW_QUALITY and _gemini_model:
            logger.info(f"\n🔍 Step 2: Checking pages with confidence < {QUALITY_THRESHOLD}...")
            low_quality_pages = [p for p in docai_results.values() if p['confidence'] < QUALITY_THRESHOLD]
            logger.info(f"   Found {len(low_quality_pages)} pages needing Gemini processing")
            
            if low_quality_pages:
                logger.info("🚀 Processing low-quality pages with Gemini Vision...")
                for page_data in low_quality_pages:
                    page_num = page_data['page_num']
                    result = process_page_hybrid(pdf_bytes, page_num, page_data)
                    docai_results[page_num] = result
                    # Embed updated page in Pinecone
                    embed_page_in_pinecone(result['text'], page_num, object_name)
                    if result['method'] == 'gemini':
                        logger.info(f"   ✅ Page {page_num} improved with Gemini")

        # Step 3: Process any missing pages with Gemini
        missing_pages = []
        for page_num in range(1, total_pages + 1):
            if page_num not in docai_results:
                missing_pages.append(page_num)
        
        if missing_pages and _gemini_model:
            logger.info(f"\n📄 Step 3: Processing {len(missing_pages)} missing pages with Gemini...")
            for page_num in missing_pages:
                result = process_page_hybrid(pdf_bytes, page_num, None)
                docai_results[page_num] = result
                embed_page_in_pinecone(result['text'], page_num, object_name)

        # Step 4: Flush any remaining embeddings
        global _embedding_manager
        if _embedding_manager:
            logger.info("\n📦 Flushing remaining embeddings...")
            _embedding_manager.flush()
            embed_stats = _embedding_manager.get_stats()
            logger.info(f"   Embedded: {embed_stats['embedded']} pages")
            if embed_stats['failed'] > 0:
                logger.warning(f"   Failed: {embed_stats['failed']} pages")

        # Calculate statistics
        docai_count = sum(1 for p in docai_results.values() if p.get('method') == 'documentai')
        gemini_count = sum(1 for p in docai_results.values() if p.get('method') == 'gemini')
        avg_confidence = sum(p['confidence'] for p in docai_results.values()) / len(docai_results) if docai_results else 0.0

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info(f"✅ Hybrid OCR processing complete!")
        logger.info(f"   File: {object_name}")
        logger.info(f"   Total time: {elapsed:.2f} seconds ({elapsed/60:.2f} minutes)")
        logger.info(f"   Pages processed: {len(docai_results)}/{total_pages}")
        logger.info(f"   Document AI: {docai_count} pages")
        logger.info(f"   Gemini Vision: {gemini_count} pages")
        logger.info(f"   Average confidence: {avg_confidence:.2f}")
        if _embedding_manager:
            embed_stats = _embedding_manager.get_stats()
            logger.info(f"   Pages embedded in Pinecone: {embed_stats['embedded']}")
        logger.info("=" * 60)

        return f"SUCCESS: Processed {len(docai_results)} pages from {object_name}"

    except Exception as e:
        logger.error(f"❌ Fatal error processing {object_name}: {e}", exc_info=True)
        return f"ERROR: {str(e)}"

