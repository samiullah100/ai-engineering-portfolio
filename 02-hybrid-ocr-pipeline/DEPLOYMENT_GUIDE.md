## What Are We Building? (The Big Picture)

Imagine you have a magic filing system:
1. You drop a PDF or image file into a special folder (Google Cloud Storage bucket)
2. The system automatically:
   - Reads the text from the image/PDF (even if it's scanned!)
   - Breaks the text into smaller, manageable pieces
   - Converts each piece into a special "fingerprint" (called an embedding)
   - Stores these fingerprints in a searchable database (Pinecone)

**Why?** So you can later search through all your documents by asking questions, and the system will find the most relevant parts!

**What is this system?** It's called a "Cloud Function" - a piece of code that runs automatically in the cloud when something happens (like a file being uploaded).

---

## What You Need Before Starting

Think of this like gathering ingredients before cooking:

1. **Google Cloud Project with billing enabled**
   - This is your workspace in Google's cloud. You need billing enabled because some services cost money (though there are free tiers).

2. **Python 3.10 or newer installed on your computer**
   - Python is the programming language we'll use. Cloud Functions Gen 2 supports Python 3.11.

3. **gcloud CLI installed and logged in** (Optional - you can use Cloud Console instead!)
   - This is a command-line tool that lets you control Google Cloud from your terminal. It's like a remote control for Google Cloud.
   - **OR** you can use the Google Cloud Console (web interface) - instructions for both methods are provided below!

4. **Pinecone account**
   - Pinecone is the database where we'll store the document "fingerprints" (embeddings). You'll need:
     - An account (sign up at pinecone.io)
     - An index created (think of it as a table in a database)
     - Your API key (like a password to access Pinecone)

5. **Gemini API Key**
   - **Embeddings** are the "fingerprints" we create from text. We'll use **Google's Gemini** for embeddings.
   - You'll need a Gemini API key (get it from [Google AI Studio](https://makersuite.google.com/app/apikey) or [Google Cloud Console](https://console.cloud.google.com/apis/credentials))
   - **Note:** This guide uses Gemini for embeddings, which keeps everything within Google's ecosystem

---

## Two Ways to Set Things Up: CLI or Cloud Console

**You can use either method!** Choose what you're more comfortable with:

- **CLI (Command Line)**: Type commands in your terminal - faster if you know what you're doing
- **Cloud Console (Web Interface)**: Click through menus in your browser - more visual and beginner-friendly

Both methods do the same thing, so pick whichever you prefer! Instructions for both are provided below.

### If Using CLI (Command Line):

**All commands should be run in your terminal/command prompt** (the black window where you type commands).

1. **Set your PROJECT_ID** (do this first, once per terminal session):
   ```bash
   export PROJECT_ID="your-gcp-project-id"
   ```
   This is like telling your terminal "remember this project ID for all commands."

2. **Where to run different commands:**
   - **Enable APIs**: Can run from anywhere (they affect your whole project)
   - **Deploy function**: Must run from inside the function folder (where your code is)
   - **Test uploads**: Can run from anywhere
   - **View logs**: Can run from anywhere

### Example: Getting Started with CLI
```bash
# 1. Set your project ID (replace with your actual project ID)
export PROJECT_ID="my-gcp-project-12345"

# 2. Check if you're logged in to Google Cloud
gcloud auth list

# 3. Tell gcloud which project to use
gcloud config set project $PROJECT_ID

# Now you're ready to run the commands below!
```

### If Using Cloud Console (Web Interface):

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Make sure you're logged in and have selected your project (use the project dropdown at the top)
3. Follow the Cloud Console instructions in each section below

---

## Step 1: Enable APIs (Turn On Google Cloud Services)

**What are APIs?** Think of them as switches that turn on different Google Cloud services. We need to turn on several switches.

### Method 1: Using CLI (Command Line)

**Run this once per project** (from any directory):

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudfunctions.googleapis.com \
  eventarc.googleapis.com \
  run.googleapis.com \
  documentai.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  logging.googleapis.com
```

### Method 2: Using Cloud Console (Web Interface)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Make sure your project is selected (check the project dropdown at the top)
3. In the search bar at the top, type "APIs & Services" and click on it
4. Click "Enable APIs and Services" (or "Library" in the left menu)
5. Search for and enable each of these APIs one by one:
   - **Artifact Registry API** (search for "Artifact Registry")
   - **Cloud Functions API** (search for "Cloud Functions")
   - **Eventarc API** (search for "Eventarc")
   - **Cloud Run API** (search for "Cloud Run")
   - **Document AI API** (search for "Document AI")
   - **Cloud Storage API** (search for "Cloud Storage")
   - **Secret Manager API** (search for "Secret Manager")
   - **Cloud Logging API** (search for "Cloud Logging")

   For each one: Click on it, then click the "Enable" button.

**What each one does:**
- `artifactregistry`: Stores your code packages
- `cloudfunctions`: The service that runs your code automatically
- `eventarc`: Watches for events (like file uploads) and triggers your function
- `run`: The platform that actually runs your function
- `documentai`: Google's service that reads text from images/PDFs
- `storage`: Where your files will be stored
- `secretmanager`: Safely stores passwords and API keys
- `logging`: Keeps track of what your function does (for debugging)

---

## Step 2: Create the Core Resources

### 1) Create a Storage Bucket (Your File Drop Box)

**What is a bucket?** It's like a folder in the cloud where you'll upload files. When a file is uploaded here, our function will automatically process it.

#### Method 1: Using CLI (Command Line)

```bash
gcloud storage buckets create gs://my-docs-upload-bucket --location=us
```

#### Method 2: Using Cloud Console (Web Interface)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. In the search bar, type "Cloud Storage" and click on it
3. Click "Create Bucket" (or "Buckets" → "Create")
4. Fill in the details:
   - **Name**: Choose a unique name (e.g., `my-docs-upload-bucket`) - must be globally unique
   - **Location type**: Choose "Region" or "Multi-region"
   - **Location**: Choose a region close to you (e.g., `us-central1` or `us-east1`)
   - **Storage class**: Standard is fine
   - **Access control**: Uniform (recommended) or Fine-grained
5. Click "Create"

**Important:** 
- Replace `my-docs-upload-bucket` with your own bucket name (must be unique globally)
- Choose a location close to you (us, eu, asia, etc.) and use the same location for everything
- **Write down your bucket name** - you'll need it later!

### 2) Create a Document AI Processor (The Text Reader)

**What is this?** This is Google's service that can read text from images and PDFs, even if they're scanned.

**How to create it:**
1. Go to the Google Cloud Console
2. Navigate to "Document AI"
3. Click "Create Processor"
4. Choose "OCR Processor" (OCR = Optical Character Recognition = reading text from images)
5. Save these details (you'll need them later):
   - **Processor ID**: A long number like `abcd1234567890`
   - **Location**: The region you chose (us, eu, etc.)

### 3) Set Up Pinecone (Your Search Database)

**What is Pinecone?** It's a database that stores "embeddings" (mathematical representations of text) so you can search through documents later.

**What to do:**
1. Go to pinecone.io and create an account
2. Create an index (like creating a table in a database)
3. Save these details:
   - **API Key**: Your password to access Pinecone
   - **Index Name**: The name you gave your index (e.g., "documents")
   - **Environment/Host**: Where your index lives (e.g., "us-east-1" or "gcp-starter")

---

## Step 3: Create a Service Account (A Robot Identity)

**What is a service account?** Think of it as a robot user that your Cloud Function will use. Instead of using your personal account, we create a special account just for this function. This is safer and more organized.

### Method 1: Using CLI (Command Line)

```bash
gcloud iam service-accounts create docai-pipeline \
  --description="Document AI OCR → Embeddings → Pinecone pipeline" \
  --display-name="docai-pipeline"
```

**What does this do?** Creates a new service account named "docai-pipeline" that your function will use.

### Method 2: Using Cloud Console (Web Interface)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. In the search bar, type "IAM & Admin" → "Service Accounts" and click on it
3. Click "Create Service Account" (or "+ Create Service Account")
4. Fill in:
   - **Service account name**: `docai-pipeline`
   - **Service account ID**: Will auto-fill (usually `docai-pipeline`)
   - **Description**: `Document AI OCR → Embeddings → Pinecone pipeline`
5. Click "Create and Continue"
6. Skip "Grant this service account access to project" for now (we'll add permissions separately)
7. Click "Done"

### Give the Service Account Permissions

**What are permissions?** They're like keys that let the service account access different services. We need to give it three keys:

#### Method 1: Using CLI (Command Line)

```bash
# Key 1: Read files from storage
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:docai-pipeline@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

# Key 2: Use Document AI to read text
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:docai-pipeline@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/documentai.apiUser"

# Key 3: Read secrets (API keys)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:docai-pipeline@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

#### Method 2: Using Cloud Console (Web Interface)

1. Go to "IAM & Admin" → "Service Accounts"
2. Find `docai-pipeline@YOUR_PROJECT_ID.iam.gserviceaccount.com` and click on it
3. Click the "Permissions" tab
4. Click "Grant Access" (or "Add Principal")
5. In "New principals", enter: `docai-pipeline@your-gcp-project-id.iam.gserviceaccount.com`
6. Click "Select a role" and add these three roles one by one:
   - **Storage Object Viewer** (`roles/storage.objectViewer`)
   - **Document AI API User** (`roles/documentai.apiUser`)
   - **Secret Manager Secret Accessor** (`roles/secretmanager.secretAccessor`)
7. Click "Save" after adding each role

**What each permission does:**
- `storage.objectViewer`: Can read files from your storage bucket
- `documentai.apiUser`: Can use Document AI to extract text
- `secretmanager.secretAccessor`: Can read API keys from Secret Manager

**Optional:** If your bucket uses uniform access control, you can also grant bucket-level permissions:

**CLI:**
```bash
gcloud storage buckets add-iam-policy-binding gs://my-docs-upload-bucket \
  --member="serviceAccount:docai-pipeline@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

**Console:**
1. Go to Cloud Storage → Buckets
2. Click on your bucket name
3. Click "Permissions" tab
4. Click "Grant Access"
5. Add the service account with "Storage Object Viewer" role

---

## Step 4: Store Your Secrets Safely

**What are secrets?** Your API keys and passwords. We store them in Google's Secret Manager instead of putting them in code (which is unsafe).

**Why Secret Manager?** It's like a safe deposit box - only authorized services can access the keys.

### Method 1: Using CLI (Command Line)

```bash
# Store your Pinecone API key
echo -n "YOUR_PINECONE_API_KEY" | gcloud secrets create PINECONE_API_KEY --data-file=-

# Store your Gemini API key (for embeddings)
echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create GEMINI_API_KEY --data-file=-
```

**What does this do?** 
- Takes your API key (replace `YOUR_PINECONE_API_KEY` with your actual key)
- Stores it securely in Google Secret Manager
- Names it `PINECONE_API_KEY` so we can reference it later

### Method 2: Using Cloud Console (Web Interface)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. In the search bar, type "Secret Manager" and click on it
3. Click "Create Secret" (or "+ Create Secret")
4. For the Pinecone API key:
   - **Name**: `PINECONE_API_KEY`
   - **Secret value**: Paste your Pinecone API key
   - Click "Create Secret"
5. For the Gemini API key:
   - Click "Create Secret" again
   - **Name**: `GEMINI_API_KEY`
   - **Secret value**: Paste your Gemini API key (get it from [Google AI Studio](https://makersuite.google.com/app/apikey))
   - Click "Create Secret"

**Note:** The service account we created earlier already has permission to read these secrets (we gave it `secretmanager.secretAccessor`).

---

## Step 5: Create Your Function Code

**What is a Cloud Function?** It's a piece of Python code that runs automatically when triggered (in our case, when a file is uploaded).

### Create the Folder Structure

Create a folder for your function code:

```
gcf-docai-ocr/
  main.py          (your Python code)
  requirements.txt (list of Python packages needed)
```

**What each file does:**
- `main.py`: Contains the actual code that processes files
- `requirements.txt`: Lists all the Python libraries your code needs

### Create requirements.txt

This file tells Google Cloud which Python packages to install:

```text
google-cloud-documentai==2.27.0
google-cloud-storage==2.16.0
google-cloud-secret-manager==2.20.2
pinecone-client==5.0.1
langchain-google-genai==2.0.0
langchain-pinecone==0.1.0
langchain-core==0.3.0
google-generativeai==0.8.0
```

**What each package does:**
- `google-cloud-documentai`: Talks to Document AI service for OCR
- `google-cloud-storage`: Reads files from storage
- `google-cloud-secret-manager`: Gets API keys from Secret Manager
- `pinecone-client`: Sends data to Pinecone
- `langchain-google-genai`: Creates embeddings using Gemini (GoogleGenerativeAIEmbeddings)
- `langchain-pinecone`: Integrates Pinecone with LangChain
- `langchain-core`: Core LangChain functionality
- `google-generativeai`: Google's Gemini API client (for optional Gemini Vision OCR fallback)

**Note:** This setup uses Gemini for embeddings, which keeps everything within Google's ecosystem and works well with Document AI.

### Environment Variables (Settings for Your Function)

These are like settings that your function will read when it runs. You'll set them when deploying:

- `DOCUMENT_AI_PROCESSOR_ID`: The processor ID you saved earlier (e.g., `abcd1234567890`)
- `DOCUMENT_AI_LOCATION`: The location you chose (e.g., `us`)
- `PINECONE_INDEX_NAME`: Your Pinecone index name (e.g., `documents`)
- `SECRET_PINECONE_API_KEY`: The name of the secret in Secret Manager (`PINECONE_API_KEY`)
- `SECRET_GEMINI_API_KEY`: The name of the Gemini secret in Secret Manager (`GEMINI_API_KEY`)

---

## Step 6: Set Up the Trigger (What Makes It Run)

**What is a trigger?** It's like a motion sensor - when something happens (a file is uploaded), it automatically runs your function.

**How it works:**
- Event type: `google.cloud.storage.object.v1.finalized` (this means "a file was fully uploaded")
- Bucket: `my-docs-upload-bucket` (the bucket we created)

**What happens:** When a file finishes uploading to your bucket, Google automatically calls your function.

---

## Step 7: Deploy Your Function (Put It Online)

**What is deployment?** This is when you upload your code to Google Cloud so it can run automatically.

### Method 1: Using CLI (Command Line)

**Important:** Run this command from **inside your function folder** (where `main.py` and `requirements.txt` are):

```bash
# 1. Go to your function folder
cd /path/to/gcf-docai-ocr

# 2. Make sure PROJECT_ID is set
export PROJECT_ID="your-gcp-project-id"

# 3. Deploy the function
gcloud functions deploy docai-ocr-pipeline \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=on_gcs_event \
  --trigger-event-filters="type=google.cloud.storage.object.v1.finalized" \
  --trigger-event-filters="bucket=my-docs-upload-bucket" \
  --service-account="docai-pipeline@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-env-vars="DOCUMENT_AI_PROCESSOR_ID=abcd1234567890,DOCUMENT_AI_LOCATION=us,PINECONE_INDEX_NAME=documents,SECRET_PINECONE_API_KEY=PINECONE_API_KEY,SECRET_GEMINI_API_KEY=GEMINI_API_KEY"
```

**What each part means:**
- `docai-ocr-pipeline`: The name of your function
- `--gen2`: Use the newer version of Cloud Functions
- `--runtime=python311`: Use Python 3.11
- `--region=us-central1`: Where your function will run (choose close to you)
- `--source=.`: Use the current folder (where your code is)
- `--entry-point=on_gcs_event`: The function name in your code that should run
- `--trigger-event-filters`: What event triggers the function (file upload)
- `--service-account`: Which service account to use
- `--set-env-vars`: The settings/environment variables

### Method 2: Using Cloud Console (Web Interface)

1. **Prepare your code:**
   - Make sure you have your `main.py` and `requirements.txt` files ready
   - You'll need to zip them or use Cloud Source Repositories (or just use the inline editor for simple functions)

2. **Go to Cloud Functions:**
   - Go to [console.cloud.google.com](https://console.cloud.google.com)
   - In the search bar, type "Cloud Functions" and click on it
   - Click "Create Function"

3. **Basic Settings:**
   - **Function name**: `docai-ocr-pipeline`
   - **Region**: Choose the same region as your bucket (e.g., `us-central1`)
   - **Environment**: Select "2nd gen" (Gen 2)

4. **Trigger Configuration:**
   - **Trigger type**: Select "Cloud Storage"
   - **Event type**: Select "Finalize/Create"
   - **Bucket**: Select your bucket (e.g., `my-docs-upload-bucket`)

5. **Runtime Settings:**
   - **Runtime**: Python 3.11
   - **Entry point**: `on_gcs_event` (the function name in your code)

6. **Code:**
   - **Source code**: Choose one:
     - **Inline editor**: Paste your code directly (good for small functions)
     - **Cloud Storage**: Upload a zip file of your code
     - **Cloud Source Repositories**: Connect to a Git repository
   - **Runtime**: Python 3.11
   - **Entry point**: `on_gcs_event`

7. **Dependencies:**
   - In the inline editor, you can edit `requirements.txt` directly
   - Or upload it if using Cloud Storage/Source Repositories

8. **Runtime, Build, Connections and Security Settings:**
   - Click "Runtime, Build, Connections and Security Settings" to expand
   - **Service account**: Select `docai-pipeline@YOUR_PROJECT_ID.iam.gserviceaccount.com`

9. **Environment Variables:**
   - Click "Add Variable" and add each of these:
     - `DOCUMENT_AI_PROCESSOR_ID` = `abcd1234567890` (your actual processor ID)
     - `DOCUMENT_AI_LOCATION` = `us` (or your location)
     - `PINECONE_INDEX_NAME` = `documents` (your index name)
     - `SECRET_PINECONE_API_KEY` = `PINECONE_API_KEY` (the secret name)
     - `SECRET_GEMINI_API_KEY` = `GEMINI_API_KEY` (the Gemini secret name)

10. **Click "Deploy"** and wait for deployment to complete (this may take a few minutes)

**Remember:** Replace the example values (like `abcd1234567890`, `my-docs-upload-bucket`) with your actual values!

---

## Step 8: What Your Function Should Do (The Logic)

When your function runs, it should follow these steps:

### 1) Read the Event (What File Was Uploaded?)
- The event tells you which bucket and which file name
- Your code reads this information
- Optionally, skip folders or temporary files

### 2) Download the File
- Use the Google Cloud Storage library to download the file
- Figure out what type of file it is (PDF, image, etc.)

### 3) Extract Text Using Document AI
- Send the file to Document AI
- Document AI reads the text (even from scanned images!)
- Get back the extracted text

### 4) Break Text Into Chunks
**What is chunking?** Breaking long text into smaller pieces. Why? Because:
- Embedding models have limits on how much text they can process at once
- Smaller pieces are easier to search through later

**How to chunk:**
- Split text into pieces of 1,000-1,600 characters each
- Add 10-20% overlap between chunks (so context isn't lost)
- Make sure each chunk fits within your embedding model's limit

### 5) Create Embeddings
**What is an embedding?** It's a list of numbers that represents the meaning of text. Similar texts have similar numbers. This lets us search by meaning, not just keywords.

**How:**
- Send each text chunk to Google's Gemini Embeddings API (using `GoogleGenerativeAIEmbeddings`)
- Use the model `models/gemini-embedding-001` for embeddings
- Get back an array of numbers (the embedding)
- Each chunk gets its own embedding
- **Note:** You can batch embeddings (100-200 at a time) to improve performance and respect rate limits

### 6) Store in Pinecone
**What is upsert?** It means "update if exists, insert if new" - so we don't create duplicates.

**What to store for each chunk:**
- **id**: A unique identifier (e.g., `filename-chunk-0`, `filename-chunk-1`)
- **values**: The embedding (array of numbers)
- **metadata**: Extra information like:
  - Which bucket/file it came from
  - Which chunk number it is
  - A preview of the text

### 7) Make It Idempotent (Safe to Run Multiple Times)
**What is idempotent?** It means running the same thing multiple times has the same result as running it once. If you upload the same file twice, it should update the existing data, not create duplicates.

**How:** Use consistent IDs (like `filename-chunk-0`) so re-processing overwrites instead of duplicating.

### 8) Handle Errors
- If something goes wrong, log it to Cloud Logging
- Include the filename and error details
- Cloud Functions will automatically retry on failure

---

## Step 9: Example Code Structure

Here's a skeleton of what your `main.py` might look like:

```python
import os
from typing import List, Tuple
from google.cloud import storage, documentai, secretmanager
from pinecone import Pinecone
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain.docstore.document import Document

# Get settings from environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
PROCESSOR_ID = os.environ["DOCUMENT_AI_PROCESSOR_ID"]
PROCESSOR_LOCATION = os.environ.get("DOCUMENT_AI_LOCATION", "us")
PINECONE_INDEX = os.environ["PINECONE_INDEX_NAME"]
SECRET_PINECONE = os.environ.get("SECRET_PINECONE_API_KEY", "PINECONE_API_KEY")
SECRET_GEMINI = os.environ.get("SECRET_GEMINI_API_KEY", "GEMINI_API_KEY")

# Create clients (connections to services)
storage_client = storage.Client()
docai_client = documentai.DocumentProcessorServiceClient()
secrets_client = secretmanager.SecretManagerServiceClient()

# Get API keys from Secret Manager
pinecone_key = secrets_client.access_secret_version(
    name=f"projects/{PROJECT_ID}/secrets/{SECRET_PINECONE}/versions/latest"
).payload.data.decode("UTF-8")

gemini_key = secrets_client.access_secret_version(
    name=f"projects/{PROJECT_ID}/secrets/{SECRET_GEMINI}/versions/latest"
).payload.data.decode("UTF-8")

# Initialize Pinecone and embeddings
pc_client = Pinecone(api_key=pinecone_key)
gemini_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=gemini_key
)
vectorstore = PineconeVectorStore(
    index=pc_client.Index(PINECONE_INDEX),
    embedding=gemini_embeddings
)

def on_gcs_event(event, context):
    """
    This function runs automatically when a file is uploaded.
    event: Contains information about the uploaded file
    context: Contains information about the function execution
    """
    bucket = event["bucket"]  # Which bucket?
    name = event["name"]      # Which file?
    
    # Step 1: Download the file
    # Step 2: Extract text with Document AI
    # Step 3: Break text into chunks
    # Step 4: Create embeddings using Gemini
    # Step 5: Store in Pinecone
    
    return "OK"
```

**Note:** This is just a skeleton! You'll need to fill in the actual code for each step. The key difference is using `GoogleGenerativeAIEmbeddings` with Gemini instead of OpenAI.

---

## Step 10: Test Your Function

### 1) Upload a Test File

**Method 1: Using CLI (Command Line)**

Upload a PDF or image to your bucket:

```bash
gcloud storage cp ./sample.pdf gs://my-docs-upload-bucket/sample.pdf
```

**Method 2: Using Cloud Console (Web Interface)**

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. In the search bar, type "Cloud Storage" and click on it
3. Click on your bucket name (e.g., `my-docs-upload-bucket`)
4. Click "Upload Files" (or drag and drop)
5. Select your test PDF or image file
6. Click "Upload"

**What happens:** This should automatically trigger your function!

### 2) Check the Logs

**Method 1: Using CLI (Command Line)**

See what your function did:

```bash
gcloud functions logs read docai-ocr-pipeline --region=us-central1 --limit=100
```

**Method 2: Using Cloud Console (Web Interface)**

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. In the search bar, type "Cloud Functions" and click on it
3. Click on your function name (`docai-ocr-pipeline`)
4. Click the "Logs" tab
5. You'll see logs showing what your function did

**What to look for:**
- Any error messages
- Confirmation that the file was processed
- Information about chunks created

### 3) Verify in Pinecone

Check your Pinecone dashboard or query the index to see if:
- Vectors (embeddings) were created
- Metadata is correct
- The right number of chunks were stored

---

## Tips and Best Practices

### Regions Matter
- Keep everything in the same region (bucket, function, Document AI processor)
- This makes things faster and cheaper

### Supported File Types
- Document AI can read: PDF, TIFF, JPEG, PNG
- Multi-page PDFs work great!

### Control Costs
- Only process files in certain folders (use filters)
- Skip very large files (add size limits in your code)

### Security
- Always use Secret Manager for API keys (never hardcode them!)
- Give service accounts only the permissions they need

### Making Updates Safe
- Use consistent IDs so re-processing doesn't create duplicates
- Test with small files first

---

## Quick Checklist (Before You're Done)

Make sure you've done all of these:

- [ ] Enabled all required APIs
- [ ] Created storage bucket
- [ ] Created Document AI processor and saved the ID
- [ ] Set up Pinecone index and saved API key
- [ ] Created service account
- [ ] Gave service account all needed permissions
- [ ] Stored API keys in Secret Manager (Pinecone and Gemini)
- [ ] Created function code (`main.py` and `requirements.txt`)
- [ ] Deployed function with correct settings
- [ ] Tested by uploading a file
- [ ] Checked logs for errors
- [ ] Verified data appeared in Pinecone

---

## Optional: Using Gemini Vision API for Hybrid OCR

**What is Hybrid OCR?** This is an advanced approach that uses:
1. **Document AI** as the primary OCR (fast and cost-effective)
2. **Gemini Vision API** as a fallback for difficult pages (better accuracy for low-quality scans)

**Why use it?** Some pages might have low confidence scores from Document AI. You can automatically use Gemini Vision to re-process those pages for better accuracy.

**What to add:**
1. You already have `google-generativeai` in requirements.txt
2. In your code, add logic to:
   - Check Document AI confidence scores
   - For pages with confidence below a threshold (e.g., 0.7), use Gemini Vision
   - Convert PDF pages to images and send to Gemini Vision API
3. Use the same `GEMINI_API_KEY` you're already using for embeddings

**Note:** This is optional - Document AI alone works great for most documents. Hybrid approach is best when you have many low-quality scanned documents.

---

## Need Help?

- **Google Cloud Console**: Check the status of your resources
- **Cloud Logging**: See detailed logs of what your function is doing
- **Pinecone Dashboard**: Verify your vectors are being stored
- **Document AI Console**: Check if your processor is working

Remember: Start small, test often, and check the logs when something doesn't work!
