"""
Streamlit ValueAdd PDF Table Extractor App with Enhanced AI Capabilities

This script creates a Streamlit web application for extracting tables from PDF files,
with special emphasis on handling scanned documents and financial tables.

Usage:
    streamlit run app.py
"""

import os


# Force the HTTP_PROXY and HTTPS_PROXY environment variables to be empty
# This prevents the Anthropic client from using any proxy configuration
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''

import tempfile
import traceback
import pandas as pd
import numpy as np
import streamlit as st
import time
import re
import requests
import io
import base64
from dotenv import load_dotenv
import pytesseract
from PIL import Image
import cv2

# ── App-level logging ──────────────────────────────────────────────────────────
try:
    from logger_config import setup_logging
    app_logger = setup_logging("pdf_extractor_app")
except Exception as _log_err:
    import logging
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    app_logger = logging.getLogger("pdf_extractor_app")
    app_logger.warning(f"logger_config import failed ({_log_err}), using basicConfig fallback")

app_logger.info("=" * 70)
app_logger.info("ValueAdd PDF Table Extractor — app startup")
app_logger.info("=" * 70)

# Import the PDFTableExtractor class
from pdf_table_extractor import PDFTableExtractor

# Load environment variables
load_dotenv()

# Configure API keys from environment
openai_api_key = os.getenv("OPENAI_API_KEY")
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
gemini_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

app_logger.debug(
    f"API keys loaded | "
    f"OpenAI={'SET' if openai_api_key else 'MISSING'} | "
    f"Anthropic={'SET' if anthropic_api_key else 'MISSING'} | "
    f"Gemini={'SET' if gemini_api_key else 'MISSING'} | "
    f"DeepSeek={'SET' if deepseek_api_key else 'MISSING'}"
)

# Set page configuration
st.set_page_config(
    page_title="ValueAdd PDF Table Extractor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #424242;
    }
    .info-box {
        background-color: #E3F2FD;
        padding: 15px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    .stProgress .st-bo {
        background-color: #1E88E5;
    }
</style>
""", unsafe_allow_html=True)


# Add this code at the beginning of your app.py file to help troubleshoot the issue

# Add this code at the beginning of your app.py file
# This will monkey patch the Anthropic class to ignore the proxies parameter

def patch_anthropic_client():
    """Monkey patch the Anthropic client to ignore the proxies parameter"""
    try:
        import anthropic
        import inspect
        import functools
        
       
        
        # Store the original __init__ method
        original_init = anthropic.Anthropic.__init__
        
        # Define a new __init__ that filters out 'proxies'
        @functools.wraps(original_init)
        def patched_init(self, *args, **kwargs):
            # Remove 'proxies' if present
            if 'proxies' in kwargs:
                st.write("Removed 'proxies' parameter from Anthropic client initialization")
                del kwargs['proxies']
            # Call the original __init__
            return original_init(self, *args, **kwargs)
        
        # Replace the __init__ method
        anthropic.Anthropic.__init__ = patched_init
        
     
        
        # Print the client initialization signature to verify
        sig = inspect.signature(anthropic.Anthropic.__init__)
        
        
    except Exception as e:
        st.error(f"Failed to patch Anthropic client: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

# Call this at the beginning of your app
patch_anthropic_client()

def debug_anthropic_module():
    """Debug function to check Anthropic module configuration"""
    try:
        import anthropic
        import inspect
        
        
        
        # Inspect Anthropic class initialization parameters
        sig = inspect.signature(anthropic.Anthropic.__init__)
        
        
        # Check if there are any monkey patches or customizations
        # by examining the module dictionary
        module_dict = dir(anthropic)
        custom_items = [item for item in module_dict if item.startswith('_') and not item.startswith('__')]
        
           
            
        # Check if there's a separate client class
        if hasattr(anthropic, 'Client'):
            client_sig = inspect.signature(anthropic.Client.__init__)
           
        
        # Look for proxy configuration in the module
        proxy_related = [item for item in module_dict if 'proxy' in item.lower()]
        if proxy_related:
            st.write(f"Proxy-related items found in Anthropic module: {proxy_related}")
            
   
        
    except Exception as e:
        st.error(f"Error inspecting Anthropic module: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

# Call this function at the beginning of your app
debug_anthropic_module()


def call_anthropic_api_minimal(prompt, pdf_text, ocr_text=None, image=None):
    """Minimal version of Anthropic API call to isolate the issue"""
    try:
        if not anthropic_api_key:
            return "Anthropic API Error: API key not found in environment variables"
            
        # Try using the requests library directly to avoid any client initialization issues
        if image is None:
            # Text-based processing - use HTTP API directly
            import requests
            import json
            
            # Combine PDF and OCR text if both are available
            text_to_use = pdf_text or ""
            if ocr_text and len(ocr_text) > len(text_to_use):
                text_to_use = ocr_text
                
            # If text is very long, truncate it
            if len(text_to_use) > 12000:
                text_to_use = text_to_use[:12000] + "\n\n[Text truncated due to length]"
            
            # Create a minimal prompt
            minimal_prompt = f"Extract tables from this text: {text_to_use[:1000]}..."
            
            headers = {
                "Content-Type": "application/json",
                "x-api-key": anthropic_api_key,
                "anthropic-version": "2023-06-01"
            }
            
            payload = {
                "model": "claude-opus-4-6",
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": minimal_prompt}
                ]
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=30  # Short timeout for testing
            )
            
            if response.status_code == 200:
                return response.json()["content"][0]["text"]
            else:
                return f"API Error: {response.status_code} - {response.text}"
        
        else:
            # For image processing, we need to use a very minimal approach
            st.warning("Image processing requires the Anthropic client. Trying minimal import...")
            
            # Try to import anthropic in the most basic way
            import importlib
            import sys
            
            # Force reload anthropic module to avoid any cached issues
            if "anthropic" in sys.modules:
                del sys.modules["anthropic"]
            
            anthropic_module = importlib.import_module("anthropic")
            
            # Create the client with only the API key
            try:
                anthropic_client = anthropic_module.Anthropic(api_key=anthropic_api_key)
                st.success("Successfully created minimal Anthropic client")
                
                # Encode the image
                base64_image = encode_image_for_claude(image)
                
                # Minimal message
                response = anthropic_client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=1024,
                    messages=[
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": "What's in this image?"},
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64_image
                                    }
                                }
                            ]
                        }
                    ]
                )
                
                return response.content[0].text
                
            except Exception as e:
                st.error(f"Error with minimal client: {str(e)}")
                # Last resort: Print the exact class initialization signature
                import inspect
                client_class = getattr(anthropic_module, "Anthropic")
                st.code(inspect.getsource(client_class.__init__))
                return f"Client initialization error: {str(e)}"
            
    except Exception as e:
        return f"Minimal Anthropic Error: {str(e)}"


def prepare_table_for_display(table):
    """Ensure table is ready for display in Streamlit with no duplicate columns."""
    if table is None or table.empty:
        return pd.DataFrame()
    
    # Ensure all column names are strings
    table.columns = table.columns.astype(str)
    
    # Fix duplicate column names
    if any(table.columns.duplicated()):
        # Create a list to track column names we've seen
        seen_columns = {}
        new_columns = []
        
        for idx, col in enumerate(table.columns):
            col_str = str(col)
            if col_str in seen_columns:
                # If duplicate, add a unique suffix
                seen_columns[col_str] += 1
                new_columns.append(f"{col_str}_{seen_columns[col_str]}")
            else:
                # First time seeing this column name
                seen_columns[col_str] = 0
                new_columns.append(col_str)
        
        # Assign the new unique column names
        table.columns = new_columns
    
    return table

def count_numbers_in_text(text):
    """Count the number of numerical values in a text."""
    # Find all numbers (integers and decimals)
    numbers = re.findall(r'\b\d+\.\d+\b|\b\d+\b', text)
    return len(numbers)

def preprocess_financial_document_image(image):
    """Apply specialized preprocessing for financial document images to improve OCR accuracy."""
    try:
        img_np = np.array(image)

        # Convert to grayscale
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        # Upscale small images for better OCR on numbers
        h, w = gray.shape
        if h < 1000 or w < 800:
            scale = max(1000.0/h, 800.0/w, 2.0)
            gray = cv2.resize(gray, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)

        # Apply CLAHE for better contrast (especially for faded scans)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Reduce noise before thresholding
        blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)

        # Apply adaptive thresholding optimized for numbers
        binary = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8
        )

        # Light denoise to remove scan artifacts without blurring digits
        denoised = cv2.fastNlMeansDenoising(binary, h=5)

        # Sharpen text edges for better digit recognition
        kernel_sharpen = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(denoised, -1, kernel_sharpen)

        return Image.fromarray(sharpened)
    except Exception as e:
        print(f"Error in image preprocessing: {e}")
        return image

def get_pdf_page_as_image(pdf_path, page_number, dpi=300):
    """Convert a PDF page to a high-resolution image."""
    _t0 = time.time()
    app_logger.debug(f"get_pdf_page_as_image | page={page_number} | dpi={dpi} | file={os.path.basename(pdf_path)}")
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)

        if page_number < 1 or page_number > len(doc):
            error_msg = f"Error: Page {page_number} does not exist. PDF has {len(doc)} pages."
            app_logger.warning(f"get_pdf_page_as_image | {error_msg}")
            return (None, error_msg)
        
        # Get the specified page (0-based index)
        page = doc[page_number - 1]
        
        # Render page to a pixmap with high resolution
        zoom = dpi / 72  # Standard PDF DPI is 72
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        
        # Convert to bytes for display
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        
        # Get basic page info
        page_info = {
            "width": page.rect.width,
            "height": page.rect.height,
            "rotation": page.rotation
        }
        
        text = page.get_text()
        doc.close()

        img_kb = len(img_bytes.getvalue()) / 1024
        app_logger.debug(
            f"get_pdf_page_as_image | page={page_number} | "
            f"image={pixmap.width}x{pixmap.height}px | size={img_kb:.1f}KB | "
            f"text_chars={len(text)} | elapsed={time.time()-_t0:.2f}s"
        )
        return {
            "image": img,
            "image_bytes": img_bytes.getvalue(),
            "page_info": page_info,
            "text": text
        }
    except Exception as e:
        app_logger.error(f"get_pdf_page_as_image | page={page_number} | ERROR: {e}\n{traceback.format_exc()}")
        return (None, f"Error converting PDF page to image: {str(e)}")

def perform_ocr_on_image(image, lang='eng'):
    """Perform OCR on an image with enhanced processing for financial documents."""
    _t0 = time.time()
    app_logger.debug(f"perform_ocr_on_image | lang={lang} | image_size={image.size}")
    try:
        processed_image = preprocess_financial_document_image(image)
        custom_config = r'--psm 6 --oem 3 -c preserve_interword_spaces=1'

        ocr_text = pytesseract.image_to_string(
            processed_image, lang=lang, config=custom_config
        )
        ocr_data = pytesseract.image_to_data(
            processed_image, lang=lang, config=custom_config,
            output_type=pytesseract.Output.DICT
        )

        app_logger.debug(
            f"perform_ocr_on_image | text_chars={len(ocr_text)} | "
            f"elapsed={time.time()-_t0:.2f}s"
        )
        return {"text": ocr_text, "data": ocr_data}
    except Exception as e:
        app_logger.error(f"perform_ocr_on_image | ERROR: {e}\n{traceback.format_exc()}")
        return {"text": f"OCR Error: {str(e)}", "data": None}

def call_openai_api(prompt, pdf_text, ocr_text=None):
    """Call OpenAI API to extract tables from scanned files with high accuracy."""
    _t0 = time.time()
    app_logger.info("call_openai_api | START | model=gpt-4o")
    try:
        if not openai_api_key:
            app_logger.warning("call_openai_api | ABORTED | API key missing")
            return "OpenAI API Error: API key not found in environment variables"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_api_key}"
        }

        # Combine PDF and OCR text if both are available
        text_to_use = pdf_text
        if ocr_text and len(ocr_text) > len(pdf_text):
            text_to_use = ocr_text
            app_logger.debug(f"call_openai_api | using OCR text (len={len(ocr_text)}) over PDF text (len={len(pdf_text)})")
            
        # If text is very long, truncate it
        if len(text_to_use) > 12000:
            text_to_use = text_to_use[:12000] + "\n\n[Text truncated due to length]"
        
        # Create financial table-specific enhanced prompt
        enhanced_prompt = f"""
{prompt}

Here's the extracted text from the scanned PDF:

{text_to_use}

IMPORTANT INSTRUCTIONS FOR FINANCIAL TABLE EXTRACTION:

1. Identify ALL tables in the text, especially financial tables with columns for different periods.
2. Pay special attention to:
   - Financial statements with quarterly/yearly data columns
   - Tables with multi-level headers (e.g., "Quarter Ended" with date sub-columns)
   - Numerical data arranged in columns
   - Tables with currency symbols, percentages, or accounting notations

3. When creating tables:
   - ALWAYS ensure each column has a UNIQUE name (add a suffix like _1, _2 to duplicates)
   - Format tables using proper markdown with | separators
   - Include separator row (|---|---|) after headers
   - Align all numerical data properly in columns

Example of correctly formatted financial table with unique column names:
| Particulars | Quarter Ended_1 | Quarter Ended_2 | Quarter Ended_3 | Year ended |
|-------------|----------------|----------------|----------------|------------|
| Revenue     | 100.5          | 120.3          | 135.7          | 456.5      |
| Expenses    | 80.2           | 95.6           | 110.2          | 386.0      |
| Profit      | 20.3           | 24.7           | 25.5           | 70.5       |

Extract ALL tables with extremely high accuracy and properly formatted unique headers.
"""
        
        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are an AI specialist in extracting tables from scanned financial documents with extreme accuracy. You identify table structures and ensure all column headers are unique."},
                {"role": "user", "content": enhanced_prompt}
            ],
            "temperature": 0.1,  # Lower temperature for more consistency
            "max_tokens": 4000
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=180  # 3 minutes timeout
        )
        
        if response.status_code == 200:
            result_text = response.json()["choices"][0]["message"]["content"]
            app_logger.info(
                f"call_openai_api | SUCCESS | response_len={len(result_text)} | "
                f"elapsed={time.time()-_t0:.2f}s"
            )
            return result_text
        else:
            app_logger.error(
                f"call_openai_api | HTTP {response.status_code} | "
                f"body={response.text[:200]} | elapsed={time.time()-_t0:.2f}s"
            )
            return f"OpenAI API Error: {response.status_code} - {response.text}"

    except Exception as e:
        app_logger.error(f"call_openai_api | EXCEPTION | {e}\n{traceback.format_exc()}")
        return f"OpenAI API Error: {str(e)}"

# Now add this modified function to replace your call_anthropic_api function

def call_anthropic_api(prompt, pdf_text, ocr_text=None, image=None):
    """Call Anthropic API with direct HTTP requests instead of using the client."""
    _t0 = time.time()
    selected_model = st.session_state.get('claude_model', 'claude-opus-4-6')
    mode = "image" if image is not None else "text"
    app_logger.info(f"call_anthropic_api | START | model={selected_model} | mode={mode}")

    try:
        if not anthropic_api_key:
            app_logger.warning("call_anthropic_api | ABORTED | API key missing")
            return "Anthropic API Error: API key not found in environment variables"

        # Use direct HTTP requests instead of the client library
        import requests

        if image is not None:
            # We have an image to process directly
            try:
                # Encode image for Claude
                base64_image = encode_image_for_claude(image)

                encoded_mb = (len(base64_image) * 3 / 4) / (1024 * 1024)
                app_logger.info(
                    f"call_anthropic_api | image_mode | model={selected_model} | "
                    f"image_size_approx={encoded_mb:.2f}MB"
                )
                st.info(f"Sending image directly to Claude API (approx. size: {encoded_mb:.2f}MB)")
                
                # Use direct HTTP request
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": anthropic_api_key,
                    "anthropic-version": "2023-06-01"
                }
                
                payload = {
                    "model": selected_model,
                    "max_tokens": 8192,
                    "temperature": 0,
                    "system": """You are an elite financial document table extraction specialist with a mandate for 100% numerical precision.

ABSOLUTE RULES - NEVER VIOLATE:
1. Copy every single digit EXACTLY as it appears - never round, estimate, interpolate, or modify any number
2. Preserve negative number notation exactly: parentheses like (1,234.56) OR minus sign like -1,234.56 must be kept as-is
3. Preserve commas in numbers exactly: 1,234,567.89 must remain 1,234,567.89
4. Preserve ALL decimal places exactly: 12.30 stays as 12.30, never 12.3
5. Extract EVERY table on the page - never skip any table, including footnote tables
6. Output ONLY markdown tables - zero explanations, zero preamble, zero commentary after tables
7. Every column header must be unique - append _2, _3, _4 suffixes to any duplicates
8. Empty cells and dash placeholders must be preserved exactly as shown""",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """Extract ALL tables from this financial document image with 100% numerical accuracy.

CRITICAL PRECISION REQUIREMENTS:
- Read every number carefully, digit by digit - do not guess or approximate
- Watch for common scanned-image misreads: 0 vs 6, 1 vs 7, 5 vs 6, 8 vs 3, 4 vs 9 - verify each digit
- Preserve exact number formatting: (1,234.56) for negatives, commas in thousands, exact decimal places
- Extract EVERY table on this page including any footnote tables with numbers
- Make column headers unique: add _2, _3 etc. to any duplicate headers

OUTPUT FORMAT: Only markdown tables using | separator, one after another, nothing else.
Example:
| Particulars | Q1_2024 | Q2_2024 | Q3_2024 |
|-------------|---------|---------|---------|
| Revenue | 1,234.56 | 2,345.67 | 3,456.78 |
| Expenses | (890.12) | (987.65) | (1,023.45) |"""
                                },
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": base64_image
                                    }
                                }
                            ]
                        }
                    ]
                }
                
                response = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                    timeout=180  # 3 minutes timeout
                )
                
                if response.status_code == 200:
                    result_text = response.json()["content"][0]["text"]
                    app_logger.info(
                        f"call_anthropic_api | image_mode SUCCESS | "
                        f"response_len={len(result_text)} | elapsed={time.time()-_t0:.2f}s"
                    )
                    return result_text
                else:
                    app_logger.error(
                        f"call_anthropic_api | image_mode HTTP {response.status_code} | "
                        f"body={response.text[:200]} | elapsed={time.time()-_t0:.2f}s"
                    )
                    return f"Anthropic API Error: {response.status_code} - {response.text}"

            except Exception as e:
                app_logger.error(
                    f"call_anthropic_api | image_mode EXCEPTION | {e}\n{traceback.format_exc()}"
                )
                st.error(f"Error with image processing: {str(e)}")
                return f"Anthropic API Error: {str(e)}"

        else:
            # Traditional text-based approach (fallback)
            text_to_use = pdf_text
            if ocr_text and len(ocr_text) > len(pdf_text):
                text_to_use = ocr_text
                app_logger.debug(
                    f"call_anthropic_api | text_mode | using OCR text "
                    f"(ocr_len={len(ocr_text)}) over PDF text (pdf_len={len(pdf_text)})"
                )
                
            # If text is very long, truncate it
            if len(text_to_use) > 12000:
                text_to_use = text_to_use[:12000] + "\n\n[Text truncated due to length]"
            
            # Create financial table-specific enhanced prompt
            enhanced_prompt = f"""
{prompt}

Here's the extracted text from the PDF document:

{text_to_use}

PRECISION EXTRACTION REQUIREMENTS:
1. Extract ALL tables present in the text with 100% numerical accuracy
2. Preserve EVERY number exactly as it appears - never round, estimate, or modify any value
3. Preserve negative notation exactly: parentheses (1,234.56) or minus sign -1,234.56 as shown
4. Preserve commas in numbers: 1,234,567.89 stays as 1,234,567.89
5. Preserve all decimal places exactly: 12.30 stays as 12.30 not 12.3
6. Identify: financial statements, quarterly/yearly columns, multi-level headers
7. Make ALL column headers unique (add _2, _3 suffixes to duplicates)
8. Use proper markdown table format with | separators and separator row |---|---|

Output ONLY the extracted tables in markdown format. No explanations or commentary.
"""

            # Use direct HTTP requests instead of the client
            headers = {
                "Content-Type": "application/json",
                "x-api-key": anthropic_api_key,
                "anthropic-version": "2023-06-01"
            }

            payload = {
                "model": selected_model,
                "max_tokens": 8192,
                "temperature": 0,
                "system": """You are an elite financial document table extraction specialist. Extract ALL tables with 100% numerical accuracy. Output ONLY markdown tables - no explanations. Every number must be copied exactly as it appears in the source.""",
                "messages": [
                    {"role": "user", "content": enhanced_prompt}
                ]
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
                timeout=180  # 3 minutes timeout
            )
            
            if response.status_code == 200:
                result_text = response.json()["content"][0]["text"]
                app_logger.info(
                    f"call_anthropic_api | text_mode SUCCESS | "
                    f"response_len={len(result_text)} | elapsed={time.time()-_t0:.2f}s"
                )
                return result_text
            else:
                app_logger.error(
                    f"call_anthropic_api | text_mode HTTP {response.status_code} | "
                    f"body={response.text[:200]} | elapsed={time.time()-_t0:.2f}s"
                )
                return f"Anthropic API Error: {response.status_code} - {response.text}"

    except Exception as e:
        app_logger.error(f"call_anthropic_api | EXCEPTION | {e}\n{traceback.format_exc()}")
        st.code(traceback.format_exc())
        return f"Anthropic API Error: {str(e)}"

def call_gemini_api(prompt, pdf_text, ocr_text=None):
    """Call Google Gemini API to extract tables."""
    _t0 = time.time()
    app_logger.info("call_gemini_api | START | model=gemini-1.5-pro")
    try:
        if not gemini_api_key:
            app_logger.warning("call_gemini_api | ABORTED | API key missing")
            return "Google Gemini API Error: API key not found in environment variables"

        from google.generativeai import configure, GenerativeModel
        configure(api_key=gemini_api_key)
        model = GenerativeModel('gemini-1.5-pro')
        
        # Combine PDF and OCR text if both are available
        text_to_use = pdf_text
        if ocr_text and len(ocr_text) > len(pdf_text):
            text_to_use = ocr_text
            
        # If text is very long, truncate it
        if len(text_to_use) > 12000:
            text_to_use = text_to_use[:12000] + "\n\n[Text truncated due to length]"
        
        # Create financial table-specific enhanced prompt
        enhanced_prompt = f"""
{prompt}

Here's the extracted text from the scanned PDF:

{text_to_use}

IMPORTANT INSTRUCTIONS FOR FINANCIAL TABLE EXTRACTION:

1. Identify ALL tables in the text, especially financial tables with columns for different periods.
2. Pay special attention to:
   - Financial statements with quarterly/yearly data columns
   - Tables with multi-level headers (e.g., "Quarter Ended" with date sub-columns)
   - Numerical data arranged in columns
   - Tables with currency symbols, percentages, or accounting notations

3. When creating tables:
   - ALWAYS ensure each column has a UNIQUE name (add a suffix like _1, _2 to duplicates)
   - Format tables using proper markdown with | separators
   - Include separator row (|---|---|) after headers
   - Align all numerical data properly in columns

Example of correctly formatted financial table with unique column names:
| Particulars | Quarter Ended_1 | Quarter Ended_2 | Quarter Ended_3 | Year ended |
|-------------|----------------|----------------|----------------|------------|
| Revenue     | 100.5          | 120.3          | 135.7          | 456.5      |
| Expenses    | 80.2           | 95.6           | 110.2          | 386.0      |
| Profit      | 20.3           | 24.7           | 25.5           | 70.5       |

Extract ALL tables with extremely high accuracy and properly formatted unique headers.
"""
        
        system_prompt = "You are an AI specialist in extracting tables from scanned financial documents with extreme accuracy. You identify table structures and ensure all column headers are unique."
        
        response = model.generate_content([system_prompt, enhanced_prompt])
        app_logger.info(
            f"call_gemini_api | SUCCESS | response_len={len(response.text)} | "
            f"elapsed={time.time()-_t0:.2f}s"
        )
        return response.text
    except Exception as e:
        app_logger.error(f"call_gemini_api | EXCEPTION | elapsed={time.time()-_t0:.2f}s | {e}\n{traceback.format_exc()}")
        return f"Google Gemini API Error: {str(e)}"

def call_deepseek_api(prompt, pdf_text, ocr_text=None):
    """Call DeepSeek API to extract tables."""
    _t0 = time.time()
    app_logger.info("call_deepseek_api | START | model=deepseek-chat")
    try:
        if not deepseek_api_key:
            app_logger.warning("call_deepseek_api | ABORTED | API key missing")
            return "DeepSeek API Error: API key not found in environment variables"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {deepseek_api_key}"
        }
        
        # Combine PDF and OCR text if both are available
        text_to_use = pdf_text
        if ocr_text and len(ocr_text) > len(pdf_text):
            text_to_use = ocr_text
            
        # If text is very long, truncate it
        if len(text_to_use) > 12000:
            text_to_use = text_to_use[:12000] + "\n\n[Text truncated due to length]"
        
        # Create financial table-specific enhanced prompt
        enhanced_prompt = f"""
{prompt}

Here's the extracted text from the scanned PDF:

{text_to_use}

IMPORTANT INSTRUCTIONS FOR FINANCIAL TABLE EXTRACTION:

1. Identify ALL tables in the text, especially financial tables with columns for different periods.
2. Pay special attention to:
   - Financial statements with quarterly/yearly data columns
   - Tables with multi-level headers (e.g., "Quarter Ended" with date sub-columns)
   - Numerical data arranged in columns
   - Tables with currency symbols, percentages, or accounting notations

3. When creating tables:
   - ALWAYS ensure each column has a UNIQUE name (add a suffix like _1, _2 to duplicates)
   - Format tables using proper markdown with | separators
   - Include separator row (|---|---|) after headers
   - Align all numerical data properly in columns

Example of correctly formatted financial table with unique column names:
| Particulars | Quarter Ended_1 | Quarter Ended_2 | Quarter Ended_3 | Year ended |
|-------------|----------------|----------------|----------------|------------|
| Revenue     | 100.5          | 120.3          | 135.7          | 456.5      |
| Expenses    | 80.2           | 95.6           | 110.2          | 386.0      |
| Profit      | 20.3           | 24.7           | 25.5           | 70.5       |

Extract ALL tables with extremely high accuracy and properly formatted unique headers.
"""
        
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "You are an AI specialist in extracting tables from scanned financial documents with extreme accuracy. You identify table structures and ensure all column headers are unique."},
                {"role": "user", "content": enhanced_prompt}
            ],
            "temperature": 0.1,  # Lower temperature for more consistency
            "max_tokens": 4000
        }
        
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=180  # 3 minutes timeout
        )
        
        if response.status_code == 200:
            result_text = response.json()["choices"][0]["message"]["content"]
            app_logger.info(
                f"call_deepseek_api | SUCCESS | response_len={len(result_text)} | "
                f"elapsed={time.time()-_t0:.2f}s"
            )
            return result_text
        else:
            app_logger.error(
                f"call_deepseek_api | HTTP {response.status_code} | "
                f"body={response.text[:200]} | elapsed={time.time()-_t0:.2f}s"
            )
            return f"DeepSeek API Error: {response.status_code} - {response.text}"

    except Exception as e:
        app_logger.error(f"call_deepseek_api | EXCEPTION | elapsed={time.time()-_t0:.2f}s | {e}\n{traceback.format_exc()}")
        return f"DeepSeek API Error: {str(e)}"

def extract_markdown_tables(text):
    """Extract markdown tables from text and convert to pandas DataFrames with unique columns."""
    app_logger.debug(f"extract_markdown_tables | input_len={len(text)}")
    table_pattern = r'(\|[^\n]+\|\n\|[-:| ]+\|\n(?:\|[^\n]+\|\n)+)'
    tables = re.findall(table_pattern, text)
    
    # If no matches, try a more lenient pattern
    if not tables:
        # Look for lines starting with | and containing multiple |
        lines = text.split('\n')
        potential_table_lines = []
        in_table = False
        current_table = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('|') and line.endswith('|') and line.count('|') >= 3:
                if not in_table:
                    in_table = True
                    current_table = [line]
                else:
                    current_table.append(line)
            elif in_table and line.startswith('|') and line.count('-') > 3:
                # This might be a separator line like |------|------|
                current_table.append(line)
            elif in_table and (not line or (not line.startswith('|'))):
                # End of table
                if len(current_table) >= 3:  # At least header, separator, and one data row
                    tables.append('\n'.join(current_table))
                in_table = False
                current_table = []
        
        # Check if we ended with an open table
        if in_table and len(current_table) >= 3:
            tables.append('\n'.join(current_table))
    
    dataframes = []
    for table in tables:
        try:
            # Split lines and remove empty lines
            lines = [line.strip() for line in table.split('\n') if line.strip()]
            
            if len(lines) < 3:  # Need at least header, separator, and one data row
                continue
            
            # Process header
            headers = [cell.strip() for cell in lines[0].split('|')]
            headers = [h for h in headers if h]  # Remove empty cells
            
            # Make headers unique before creating the DataFrame
            if len(set(headers)) < len(headers):
                unique_headers = []
                header_count = {}
                
                for h in headers:
                    if h in header_count:
                        header_count[h] += 1
                        unique_headers.append(f"{h}_{header_count[h]}")
                    else:
                        header_count[h] = 0
                        unique_headers.append(h)
                
                headers = unique_headers
            
            # Process data rows
            data = []
            for i in range(2, len(lines)):
                row = [cell.strip() for cell in lines[i].split('|')]
                row = [r for r in row if r != '']  # Remove empty cells
                if row:
                    data.append(row)
            
            # Create DataFrame
            if headers and data:
                # Make sure all rows have the same number of columns as the header
                max_columns = max(len(headers), max([len(row) for row in data]) if data else 0)
                
                # Adjust header if needed
                if len(headers) < max_columns:
                    headers = headers + [f'Column_{i+1}' for i in range(len(headers), max_columns)]
                
                # Adjust data rows if needed
                for i, row in enumerate(data):
                    if len(row) < max_columns:
                        data[i] = row + [''] * (max_columns - len(row))
                    elif len(row) > max_columns:
                        data[i] = row[:max_columns]
                
                df = pd.DataFrame(data, columns=headers)
                
                # Clean up the DataFrame
                df = df.applymap(lambda x: x.replace('_', '') if isinstance(x, str) else x)
                df = df.applymap(lambda x: x.replace('*', '') if isinstance(x, str) else x)
                
                # Final check for unique columns
                df = prepare_table_for_display(df)
                
                dataframes.append(df)
        except Exception as e:
            st.warning(f"Error converting markdown table to DataFrame: {e}")
            continue
    
    # If no markdown tables found, try to look for other table-like structures
    if not dataframes:
        try:
            # Look for patterns of aligned text that might represent tables
            lines = text.split('\n')
            table_lines = []
            in_table = False
            current_table = []
            
            for line in lines:
                stripped = line.strip()
                if stripped and (('  ' in stripped) or ('\t' in stripped)) and len(stripped.split()) > 2:
                    # Lines with multiple spaces or tabs and several words might be table rows
                    if not in_table:
                        in_table = True
                        current_table = [stripped]
                    else:
                        current_table.append(stripped)
                elif in_table and not stripped:
                    # Empty line might indicate end of table
                    if len(current_table) >= 2:  # Need at least header and one data row
                        table_lines.append('\n'.join(current_table))
                    in_table = False
                    current_table = []
            
            # Check if we ended with an open table
            if in_table and len(current_table) >= 2:
                table_lines.append('\n'.join(current_table))
            
            # Process each potential table
            for table_text in table_lines:
                try:
                    # Try to split by multiple spaces
                    df = pd.read_csv(io.StringIO(table_text), sep=r'\s{2,}', engine='python')
                    if not df.empty and df.shape[1] > 1:
                        # Ensure unique column names
                        df = prepare_table_for_display(df)
                        dataframes.append(df)
                except:
                    pass
        except Exception as e:
            st.warning(f"Error detecting table-like structures: {e}")

    app_logger.debug(
        f"extract_markdown_tables | found {len(dataframes)} DataFrame(s) | "
        f"shapes={[df.shape for df in dataframes]}"
    )
    return dataframes

def process_llm_result(model_name, result, pdf_text, ocr_text):
    """Process the result from an LLM and extract tables."""
    # Check if there was an error
    if result.startswith(model_name.split()[0] + " API Error:"):
        return {
            "success": False,
            "error_message": result,
            "tables": [],
            "markdown": "",
            "number_count": 0
        }
    
    # Count numbers in the result
    number_count = count_numbers_in_text(result)
    
    # Extract tables from the result
    tables = extract_markdown_tables(result)
    
    return {
        "success": True,
        "error_message": None,
        "tables": tables,
        "markdown": result,
        "number_count": number_count
    }

def display_extraction_results(model_name, results):
    """Display extraction results and download buttons for a specific model."""
    st.subheader(f"Table extraction results from {model_name}")
    
    if not results["success"]:
        st.error(results["error_message"])
        return
    
    tables = results["tables"]
    
    if tables:
        st.success(f"Successfully extracted {len(tables)} tables with {results['number_count']} numerical values.")

        # Download ALL tables as single multi-sheet Excel
        valid_tables = [prepare_table_for_display(t) for t in tables if not t.empty]
        if valid_tables:
            multi_excel_buf = io.BytesIO()
            with pd.ExcelWriter(multi_excel_buf, engine='openpyxl') as writer:
                for i, tbl in enumerate(valid_tables):
                    tbl.to_excel(writer, index=False, sheet_name=f"Table_{i+1}")
            st.download_button(
                label=f"⬇ Download ALL {len(valid_tables)} Tables as Excel (multi-sheet)",
                data=multi_excel_buf.getvalue(),
                file_name=f"{model_name.replace(' ', '_')}_all_tables.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"multi_excel_{model_name.replace(' ','_')}"
            )
            st.write("---")

        for i, table in enumerate(tables):
            if not table.empty:
                st.write(f"**Table {i+1}**")

                # Ensure no duplicate columns before display
                display_table = prepare_table_for_display(table)
                st.dataframe(display_table)

                # Create download buttons for each table
                col1, col2 = st.columns(2)
                with col1:
                    # CSV download
                    csv = display_table.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label=f"Download Table {i+1} as CSV",
                        data=csv,
                        file_name=f"{model_name.replace(' ', '_')}_table_{i+1}.csv",
                        mime="text/csv",
                        key=f"csv_{model_name.replace(' ','_')}_{i+1}"
                    )

                with col2:
                    # Excel download
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        display_table.to_excel(writer, index=False, sheet_name=f"Table{i+1}")
                    excel_data = output.getvalue()
                    st.download_button(
                        label=f"Download Table {i+1} as Excel",
                        data=excel_data,
                        file_name=f"{model_name.replace(' ', '_')}_table_{i+1}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"xlsx_{model_name.replace(' ','_')}_{i+1}"
                    )

                st.write("---")
    else:
        # Show the raw output if no tables could be automatically extracted
        st.warning("No tables could be automatically extracted as dataframes. Showing raw output instead:")
        st.markdown(results["markdown"])
        
        # Provide a download option for the raw text
        raw_text = results["markdown"].encode('utf-8')
        st.download_button(
            label="Download raw output as Text",
            data=raw_text,
            file_name=f"{model_name.replace(' ', '_')}_raw_output.txt",
            mime="text/plain"
        )
        
def compress_image(image, max_size_mb=4.8):
    """Compress image to ensure it's below the max size limit for Claude API"""
    max_size_bytes = max_size_mb * 1024 * 1024
    
    # First check if image needs compression
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    current_size = buffer.getbuffer().nbytes
    
    if current_size <= max_size_bytes:
        return image  # No compression needed
    
    # Calculate scale factor based on area
    scale_factor = (max_size_bytes / current_size) ** 0.5
    
    # Scale down the image while maintaining aspect ratio
    new_width = int(image.width * scale_factor * 0.9)  # 10% buffer
    new_height = int(image.height * scale_factor * 0.9)
    
    # Resize image
    resized_img = image.resize((new_width, new_height), Image.LANCZOS)
    
    # If still too large, reduce quality further
    buffer = io.BytesIO()
    resized_img.save(buffer, format="JPEG", quality=85)
    
    if buffer.getbuffer().nbytes > max_size_bytes:
        # Try with lower quality
        buffer = io.BytesIO()
        resized_img.save(buffer, format="JPEG", quality=70)
    
    # Convert back to PIL Image
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")

def encode_image_for_claude(image):
    """Encode a PIL image to base64 for Claude API"""
    # First compress the image to ensure it's below 5MB
    compressed_image = compress_image(image)
    
    # Now encode it
    buffer = io.BytesIO()
    compressed_image.save(buffer, format="JPEG", quality=90)
    
    # Check final size
    file_size_mb = buffer.getbuffer().nbytes / (1024 * 1024)
    if file_size_mb > 5:
        st.warning(f"Image size is {file_size_mb:.2f}MB, which exceeds Claude's 5MB limit. Compressing further...")
        # Try more aggressive compression
        buffer = io.BytesIO()
        compressed_image.save(buffer, format="JPEG", quality=75)
        file_size_mb = buffer.getbuffer().nbytes / (1024 * 1024)
        st.info(f"Compressed image size: {file_size_mb:.2f}MB")
    
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# Header
st.markdown('<p class="main-header">ValueAdd PDF Table Extractor</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Extract tables from any PDF file</p>', unsafe_allow_html=True)

# Sidebar for options
st.sidebar.header("Extraction Options")

# OCR options
use_ocr = st.sidebar.checkbox("Use OCR (for scanned documents)", value=True)
ocr_language = st.sidebar.selectbox(
    "OCR Language",
    options=["eng", "fra", "deu", "spa", "ita", "por", "chi_sim", "jpn", "rus"],
    index=0,
    help="Language for OCR text recognition"
)
dpi = st.sidebar.slider("DPI for Image Conversion", 
                        min_value=100, 
                        max_value=600, 
                        value=300, 
                        step=50,
                        help="Higher DPI means better quality but slower processing")

# Output format
output_format = st.sidebar.selectbox(
    "Output Format",
    options=["CSV", "Excel", "JSON"],
    index=0,
    help="Format for saving extracted tables"
)

# Advanced options
with st.sidebar.expander("Advanced Options"):
    confidence_threshold = st.slider(
        "OCR Confidence Threshold",
        min_value=0.0,
        max_value=100.0,
        value=50.0,
        step=5.0,
        help="Minimum confidence score for OCR results"
    )
    
    lattice_mode = st.checkbox(
        "Enable Lattice Mode",
        value=True,
        help="For tables with visible grid lines"
    )
    
    stream_mode = st.checkbox(
        "Enable Stream Mode",
        value=True,
        help="For tables without visible grid lines"
    )

st.sidebar.markdown("---")
st.sidebar.markdown("### About")
st.sidebar.info(
    "This app extracts tables from PDF files "
    "using multiple extraction methods. It works with "
    "structured tables, unstructured tables, "
    "scanned documents, and more."
)

# Main content area
with st.container():
    st.markdown('<div class="info-box">', unsafe_allow_html=True)
    st.markdown("""
    #### How to use:
    1. Upload a PDF file
    2. Configure extraction options
    3. Select either:
       - **Traditional Extraction** for algorithm-based table extraction
       - **LLM-Based Extraction** to extract tables using AI models (OpenAI, Anthropic, Google Gemini, or DeepSeek)
    4. View and download the results
    """)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # File upload
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    
    if uploaded_file is not None:
        app_logger.info(
            f"FILE UPLOADED | name={uploaded_file.name} | "
            f"size={uploaded_file.size/1024:.1f}KB"
        )
        file_details = {
            "Filename": uploaded_file.name,
            "File size": f"{uploaded_file.size / 1024:.2f} KB"
        }
        st.write("**File Details:**")
        for key, value in file_details.items():
            st.write(f"- {key}: {value}")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            pdf_path = tmp_file.name
        app_logger.debug(f"PDF saved to temp file: {pdf_path}")
        
        # TABS for different extraction methods
        tab1, tab2 = st.tabs(["Traditional Extraction", "LLM-Based Extraction"])
        
        with tab1:
            # Option to specify pages
            page_option = st.radio(
                "Pages to process",
                options=["All pages", "Specific pages"],
                index=0
            )
            
            pages_to_process = "all"
            if page_option == "Specific pages":
                pages_input = st.text_input(
                    "Enter page numbers (comma-separated, e.g., '1,3,5-7')",
                    "1"
                )
                try:
                    # Process page ranges like "1-3"
                    pages = []
                    for part in pages_input.split(','):
                        if '-' in part:
                            start, end = map(int, part.split('-'))
                            pages.extend(range(start, end + 1))
                        else:
                            pages.append(int(part))
                    pages_to_process = pages
                except ValueError:
                    st.error("Invalid page format. Please use comma-separated numbers or ranges (e.g., '1,3,5-7').")
                    pages_to_process = [1]  # Default to first page if invalid input
            
            # Extract tables button
            extract_button = st.button("Extract Tables")
            
            if extract_button:
                # Show progress
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Status updates
                status_text.text("Initializing table extractor...")
                progress_bar.progress(10)
                
                # Initialize the extractor with selected options
                extractor = PDFTableExtractor(
                    use_ocr=use_ocr,
                    ocr_lang=ocr_language,
                    dpi=dpi,
                    confidence_threshold=confidence_threshold
                )
                
                # Status update
                status_text.text("Analyzing PDF structure...")
                progress_bar.progress(20)
                
                # Analyze PDF
                pdf_info = extractor.analyze_pdf(pdf_path)
                
                # Status update
                status_text.text(f"PDF has {pdf_info['pages']} pages. " +
                                (f"Document appears to be {'scanned' if pdf_info['is_scanned'] else 'text-based'}. " if 'is_scanned' in pdf_info else ""))
                progress_bar.progress(30)
                
                # Status update
                status_text.text("Extracting tables from PDF...")
                progress_bar.progress(40)
                
                # Extract tables
                start_time = time.time()
                tables_dict = extractor.extract_tables(pdf_path, pages=pages_to_process)
                extraction_time = time.time() - start_time
                
                # Status update
                status_text.text("Post-processing extracted tables...")
                progress_bar.progress(70)
                
                # Status update
                status_text.text("Extraction complete!")
                progress_bar.progress(100)
                
                # Display extraction summary
                st.success(f"Extraction completed in {extraction_time:.2f} seconds")
                
                # Count total tables extracted
                total_tables = sum(len(tables) for tables in tables_dict.values())
                st.write(f"**Total tables extracted:** {total_tables}")
                
                if total_tables > 0:
                    # Create tabs for visualization and download
                    view_tab, download_tab = st.tabs(["View Tables", "Download Tables"])
                    
                    with view_tab:
                        # Display tables
                        for page_num, tables in tables_dict.items():
                            if tables:  # Only show pages with tables
                                st.subheader(f"Page {page_num}")
                                for i, table in enumerate(tables):
                                    if table is not None and not table.empty:
                                        # Fix any duplicate columns before display
                                        display_table = prepare_table_for_display(table)
                                        
                                        st.write(f"**Table {i+1}**")
                                        st.dataframe(display_table)
                                        st.write("---")
                    
                    with download_tab:
                        # Multi-sheet Excel: all tables in one file, each table = one sheet
                        multi_xl_trad = io.BytesIO()
                        with pd.ExcelWriter(multi_xl_trad, engine='openpyxl') as writer:
                            trad_sn = {}
                            for page_num, tbls in tables_dict.items():
                                for tbl in tbls:
                                    if tbl is not None and not tbl.empty:
                                        base = f"Pg{page_num}_Tbl"
                                        trad_sn[base] = trad_sn.get(base, 0) + 1
                                        sn = f"{base}{trad_sn[base]}"[:31]
                                        prepare_table_for_display(tbl).to_excel(writer, index=False, sheet_name=sn)
                        st.download_button(
                            label=f"⬇ Download ALL {total_tables} Tables as Excel (multi-sheet)",
                            data=multi_xl_trad.getvalue(),
                            file_name="extracted_all_tables.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="trad_multi_xl_btn"
                        )
                        st.write("---")

                        # Create a temporary directory for saving files
                        with tempfile.TemporaryDirectory() as tmp_dir:
                            # Prepare tables for saving (fix duplicate columns)
                            fixed_tables_dict = {}
                            for page_num, tables in tables_dict.items():
                                fixed_tables_dict[page_num] = [prepare_table_for_display(table) for table in tables if table is not None and not table.empty]

                            saved_files = extractor.save_tables(
                                fixed_tables_dict, 
                                tmp_dir, 
                                format=output_format.lower(), 
                                prefix='table'
                            )
                            
                            # Create download buttons for each file
                            if saved_files:
                                st.subheader("Download Extracted Tables")
                                for file_path in saved_files:
                                    file_name = os.path.basename(file_path)
                                    with open(file_path, "rb") as file:
                                        file_bytes = file.read()
                                        
                                    # Create download button
                                    download_button_str = f"Download {file_name}"
                                    st.download_button(
                                        label=download_button_str,
                                        data=file_bytes,
                                        file_name=file_name,
                                        mime={
                                            'csv': 'text/csv',
                                            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                                            'json': 'application/json'
                                        }[output_format.lower()]
                                    )
                                    
                                    st.write("---")
                            else:
                                st.warning("No files were generated. No tables were found or the extraction failed.")
                else:
                    st.warning("No tables were found in the PDF. Try adjusting the extraction options or try a different PDF.")
        
        with tab2:
            st.subheader("Extract Tables using LLMs")
            st.write("This feature uses multiple AI models to extract tables from your PDF, with special focus on scanned documents.")
            
            # Get total page count for all-pages option
            try:
                import fitz as _fitz_llm
                _doc_llm = _fitz_llm.open(pdf_path)
                _total_pages_llm = len(_doc_llm)
                _doc_llm.close()
            except Exception:
                _total_pages_llm = 1

            # Page selection for LLM extraction
            llm_page_option = st.radio(
                "Pages to process with LLMs",
                options=["All pages", "Specific page"],
                index=0,
                help="Select 'All pages' to extract tables from every page, or 'Specific page' for a single page"
            )

            if llm_page_option == "Specific page":
                llm_page_number = st.number_input(
                    "Select page number",
                    min_value=1,
                    max_value=_total_pages_llm,
                    value=1,
                    step=1,
                    help="Enter the page number you want to extract tables from"
                )
                llm_pages_to_process = [int(llm_page_number)]
            else:
                llm_page_number = 1
                llm_pages_to_process = list(range(1, _total_pages_llm + 1))
                st.info(f"Will process all {_total_pages_llm} page(s)")
            
            # Custom prompt option
            use_custom_prompt = st.checkbox("Use custom prompt", value=False)
            
            default_prompt = "Could you please extract table/tables from given PDF file with high accuracy. You can use your highest powerful model. Show me the extracted table/tables. Don't give any coding, only tables required. If not able to extract don't give up as ChatGPT, DeepSeek, Claude, and Google Gemini have extracted tables from this PDF, you can also extract. Try your best."
            
            if use_custom_prompt:
                llm_prompt = st.text_area("Custom prompt for LLMs", value=default_prompt, height=150)
            else:
                llm_prompt = default_prompt
                
            # Initialize session state variables for Anthropic settings if they don't exist
            if 'use_direct_image' not in st.session_state:
                st.session_state.use_direct_image = True
            if 'selected_dpi' not in st.session_state:
                st.session_state.selected_dpi = 200
            if 'claude_model' not in st.session_state:
                st.session_state.claude_model = "claude-opus-4-6"
                
            # Advanced settings for Anthropic/Claude
            with st.expander("Advanced Anthropic Settings"):
                st.write("These settings only apply when using the Anthropic Claude model.")
                
                dpi_options = [150, 200, 250, 300]
                st.session_state.selected_dpi = st.select_slider(
                    "Image Resolution (DPI)",
                    options=dpi_options,
                    value=st.session_state.selected_dpi,
                    help="Higher DPI gives better quality but may hit file size limits"
                )
                
                st.session_state.use_direct_image = st.checkbox(
                    "Use Direct Image Processing", 
                    value=st.session_state.use_direct_image,
                    help="When enabled, sends PDF image directly to Claude instead of text extraction. This is more accurate for scanned documents."
                )
                
                st.session_state.claude_model = st.selectbox(
                    "Claude Model",
                    options=["claude-opus-4-6", "claude-3-7-sonnet-20250219", "claude-opus-4-5-20251101"],
                    index=0,
                    help="Select which Claude model to use. Opus 4.6 provides maximum accuracy for table extraction."
                )
                
            
            # Initialize session state for LLM results if not already done
            if 'pdf_page_data' not in st.session_state:
                st.session_state.pdf_page_data = None
            if 'ocr_result' not in st.session_state:
                st.session_state.ocr_result = None
            
            # Container for LLM buttons
            st.write("### Select an AI service to extract tables")
            
            # Create a 2x2 grid for the buttons
            col1, col2 = st.columns(2)
            col3, col4 = st.columns(2)
            
            # Create visually appealing buttons with custom HTML
            with col1:
                st.markdown('<div class="model-card">', unsafe_allow_html=True)
                st.markdown("### OpenAI GPT-4o")
                extract_openai_button = st.button("Extract with OpenAI", key="openai_button")
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col2:
                st.markdown('<div class="model-card">', unsafe_allow_html=True)
                st.markdown("### Anthropic Claude")
                extract_anthropic_button = st.button("Extract with Claude", key="anthropic_button")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col3:
                st.markdown('<div class="model-card">', unsafe_allow_html=True)
                st.markdown("### Google Gemini")
                extract_gemini_button = st.button("Extract with Gemini", key="gemini_button")
                st.markdown('</div>', unsafe_allow_html=True)
                
            with col4:
                st.markdown('<div class="model-card">', unsafe_allow_html=True)
                st.markdown("### DeepSeek")
                extract_deepseek_button = st.button("Extract with DeepSeek", key="deepseek_button")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Common preparation code for all LLM buttons
            def prepare_pdf_data():
                # Convert the PDF page to image for better processing of scanned documents
                page_data = get_pdf_page_as_image(pdf_path, llm_page_number, dpi=dpi)
                
                if isinstance(page_data, tuple):
                    error_message = page_data[1] if len(page_data) > 1 else "Unknown error in PDF processing"
                    st.error(error_message)
                    return None, None
                
                # Display the page image
                st.subheader("PDF Page Preview")
                st.image(page_data["image_bytes"], caption=f"Page {llm_page_number}")
                
                # Extract text using native PDF extraction
                pdf_text = page_data["text"]
                
                # Also perform OCR on the image for better text extraction (especially for scanned PDFs)
                st.info("Performing OCR on the page image for better table extraction...")
                ocr_result = perform_ocr_on_image(page_data["image"], lang=ocr_language)
                ocr_text = ocr_result["text"]
                
                # Show the extracted text in an expander
                with st.expander("View extracted text"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("PDF Text")
                        st.text(pdf_text[:1000] + ("..." if len(pdf_text) > 1000 else ""))
                    with col2:
                        st.subheader("OCR Text")
                        st.text(ocr_text[:1000] + ("..." if len(ocr_text) > 1000 else ""))
                
                return page_data, ocr_result
            
            # Function to process LLM extraction (supports single page and all pages)
            def process_llm_extraction(model_name, api_function):
                all_extracted = []  # list of (page_num, table_df)
                all_markdown_parts = []

                progress_bar_llm = st.progress(0)
                status_llm = st.empty()

                for p_idx, page_num in enumerate(llm_pages_to_process):
                    status_llm.info(f"Processing page {page_num}/{len(llm_pages_to_process)} with {model_name}...")
                    progress_bar_llm.progress(p_idx / max(len(llm_pages_to_process), 1))

                    page_item = get_pdf_page_as_image(pdf_path, page_num, dpi=dpi)
                    if isinstance(page_item, tuple):
                        st.warning(f"Page {page_num}: Could not load image")
                        continue

                    if len(llm_pages_to_process) > 1:
                        with st.expander(f"Page {page_num} Preview"):
                            st.image(page_item["image_bytes"], caption=f"Page {page_num}")
                    else:
                        st.subheader("PDF Page Preview")
                        st.image(page_item["image_bytes"], caption=f"Page {page_num}")

                    pdf_text = page_item["text"]
                    ocr_res = perform_ocr_on_image(page_item["image"], lang=ocr_language)
                    ocr_text = ocr_res["text"]

                    if len(llm_pages_to_process) == 1:
                        with st.expander("View extracted text"):
                            col_t1, col_t2 = st.columns(2)
                            with col_t1:
                                st.subheader("PDF Text")
                                st.text(pdf_text[:1000] + ("..." if len(pdf_text) > 1000 else ""))
                            with col_t2:
                                st.subheader("OCR Text")
                                st.text(ocr_text[:1000] + ("..." if len(ocr_text) > 1000 else ""))

                    result = api_function(llm_prompt, pdf_text, ocr_text)

                    if not result.startswith(model_name.split()[0] + " API Error:"):
                        page_tables = extract_markdown_tables(result)
                        for t in page_tables:
                            all_extracted.append((page_num, t))
                        all_markdown_parts.append(f"\n\n### Page {page_num}\n\n{result}")
                    else:
                        st.warning(f"Page {page_num}: {result}")

                progress_bar_llm.progress(1.0)
                total_nums = count_numbers_in_text("\n".join(all_markdown_parts))
                status_llm.success(f"Completed {len(llm_pages_to_process)} page(s). Found {len(all_extracted)} table(s) with {total_nums} numerical values.")

                if all_extracted:
                    # Multi-sheet Excel: each table in its own sheet
                    multi_xl = io.BytesIO()
                    with pd.ExcelWriter(multi_xl, engine='openpyxl') as writer:
                        sn_counts = {}
                        for pg, tbl in all_extracted:
                            base = f"Pg{pg}_Tbl"
                            sn_counts[base] = sn_counts.get(base, 0) + 1
                            sn = f"{base}{sn_counts[base]}"[:31]
                            prepare_table_for_display(tbl).to_excel(writer, index=False, sheet_name=sn)
                    st.download_button(
                        label=f"⬇ Download ALL {len(all_extracted)} Tables as Excel (multi-sheet)",
                        data=multi_xl.getvalue(),
                        file_name=f"{model_name.replace(' ', '_')}_all_tables.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"multi_xl_{model_name.replace(' ','_')}_btn"
                    )
                    st.write("---")
                    for t_idx, (pg, tbl) in enumerate(all_extracted):
                        st.write(f"**Page {pg} - Table {t_idx+1}**")
                        display_tbl = prepare_table_for_display(tbl)
                        st.dataframe(display_tbl)
                        c1, c2 = st.columns(2)
                        with c1:
                            csv_d = display_tbl.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                label="Download CSV",
                                data=csv_d,
                                file_name=f"{model_name.replace(' ','_')}_pg{pg}_t{t_idx+1}.csv",
                                mime="text/csv",
                                key=f"csv_{model_name.replace(' ','_')}_{pg}_{t_idx}"
                            )
                        with c2:
                            xl_single = io.BytesIO()
                            with pd.ExcelWriter(xl_single, engine='openpyxl') as w2:
                                display_tbl.to_excel(w2, index=False, sheet_name="Table")
                            st.download_button(
                                label="Download Excel",
                                data=xl_single.getvalue(),
                                file_name=f"{model_name.replace(' ','_')}_pg{pg}_t{t_idx+1}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"xlsx_{model_name.replace(' ','_')}_{pg}_{t_idx}"
                            )
                        st.write("---")
                else:
                    combined_md = "\n".join(all_markdown_parts)
                    if combined_md:
                        st.warning("No structured tables extracted. Showing raw output:")
                        st.markdown(combined_md)
                        st.download_button(
                            label="Download raw output as Text",
                            data=combined_md.encode('utf-8'),
                            file_name=f"{model_name.replace(' ', '_')}_raw_output.txt",
                            mime="text/plain",
                            key=f"raw_{model_name.replace(' ','_')}_btn"
                        )
            
            # Handle LLM extraction button clicks
            if extract_openai_button:
                process_llm_extraction("OpenAI GPT-4o", call_openai_api)
                
            if extract_anthropic_button:
                # Check if using direct image processing or text-based processing
                if st.session_state.use_direct_image:
                    selected_dpi_claude = st.session_state.get('selected_dpi', 200)
                    all_claude_tables = []  # list of (page_num, table_df)
                    all_claude_md = []

                    progress_claude = st.progress(0)
                    status_claude = st.empty()

                    for p_idx, page_num in enumerate(llm_pages_to_process):
                        status_claude.info(f"Processing page {page_num}/{len(llm_pages_to_process)} with Claude (Direct Image)...")
                        progress_claude.progress(p_idx / max(len(llm_pages_to_process), 1))

                        page_data = get_pdf_page_as_image(pdf_path, page_num, dpi=selected_dpi_claude)

                        if isinstance(page_data, tuple):
                            st.warning(f"Page {page_num}: {page_data[1] if len(page_data) > 1 else 'Error'}")
                            continue

                        if len(llm_pages_to_process) > 1:
                            with st.expander(f"Page {page_num} Preview"):
                                st.image(page_data["image_bytes"], caption=f"Page {page_num}")
                        else:
                            st.subheader("PDF Page Preview")
                            st.image(page_data["image_bytes"], caption=f"Page {page_num}")

                        result = call_anthropic_api(llm_prompt, "", None, page_data["image"])

                        if result.startswith("Anthropic API Error:"):
                            st.warning(f"Page {page_num}: {result}")
                        else:
                            page_tables = extract_markdown_tables(result)
                            for t in page_tables:
                                all_claude_tables.append((page_num, t))
                            all_claude_md.append(f"\n\n### Page {page_num}\n\n{result}")

                    progress_claude.progress(1.0)
                    total_claude_nums = count_numbers_in_text("\n".join(all_claude_md))
                    status_claude.success(f"Completed {len(llm_pages_to_process)} page(s). Found {len(all_claude_tables)} table(s) with {total_claude_nums} numerical values.")

                    if all_claude_tables:
                        # Multi-sheet Excel download
                        multi_xl_claude = io.BytesIO()
                        with pd.ExcelWriter(multi_xl_claude, engine='openpyxl') as writer:
                            sn_cnt = {}
                            for pg, tbl in all_claude_tables:
                                base = f"Pg{pg}_Tbl"
                                sn_cnt[base] = sn_cnt.get(base, 0) + 1
                                sn = f"{base}{sn_cnt[base]}"[:31]
                                prepare_table_for_display(tbl).to_excel(writer, index=False, sheet_name=sn)
                        st.download_button(
                            label=f"⬇ Download ALL {len(all_claude_tables)} Tables as Excel (multi-sheet)",
                            data=multi_xl_claude.getvalue(),
                            file_name="Claude_all_tables.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="claude_multi_xl_btn"
                        )
                        st.write("---")
                        for t_idx, (pg, tbl) in enumerate(all_claude_tables):
                            st.write(f"**Page {pg} - Table {t_idx+1}**")
                            display_tbl = prepare_table_for_display(tbl)
                            st.dataframe(display_tbl)
                            c1, c2 = st.columns(2)
                            with c1:
                                csv_d = display_tbl.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    label="Download CSV",
                                    data=csv_d,
                                    file_name=f"Claude_pg{pg}_t{t_idx+1}.csv",
                                    mime="text/csv",
                                    key=f"claude_csv_{pg}_{t_idx}"
                                )
                            with c2:
                                xl_s = io.BytesIO()
                                with pd.ExcelWriter(xl_s, engine='openpyxl') as w2:
                                    display_tbl.to_excel(w2, index=False, sheet_name="Table")
                                st.download_button(
                                    label="Download Excel",
                                    data=xl_s.getvalue(),
                                    file_name=f"Claude_pg{pg}_t{t_idx+1}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"claude_xlsx_{pg}_{t_idx}"
                                )
                            st.write("---")
                    else:
                        combined_claude_md = "\n".join(all_claude_md)
                        if combined_claude_md:
                            st.warning("No structured tables found. Showing raw output:")
                            st.markdown(combined_claude_md)
                else:
                    # Use the text-based processing
                    process_llm_extraction("Anthropic Claude", call_anthropic_api)
                
            if extract_gemini_button:
                process_llm_extraction("Google Gemini", call_gemini_api)
                
            if extract_deepseek_button:
                process_llm_extraction("DeepSeek", call_deepseek_api)
        
                
        # Clean up the temporary file when done
        try:
            os.unlink(pdf_path)
        except:
            pass
        

# Footer
st.markdown("---")
st.markdown("Made with Streamlit • ValueAdd PDF Table Extractor")