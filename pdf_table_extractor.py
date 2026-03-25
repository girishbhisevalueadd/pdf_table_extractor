"""
PDF Table Extraction Pipeline

This script provides a comprehensive approach to extract tables from PDFs
regardless of their format (structured, unstructured, image-based, or scanned).

Installation:
    pip install -r requirements.txt

Requirements:
    - tabula-py
    - camelot-py[cv]
    - pdfplumber
    - pytesseract
    - pdf2image
    - opencv-python
    - numpy
    - pandas
    - pillow
    - ghostscript (external dependency)
    - poppler (external dependency)
    - tesseract (external dependency)
"""

import os
import time
import tempfile
import logging
import traceback
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Union

import numpy as np
import pandas as pd
import cv2
import pytesseract
from PIL import Image
import tabula
import camelot
import pdfplumber
from pdf2image import convert_from_path

# ── Logging setup ──────────────────────────────────────────────────────────────
try:
    from logger_config import setup_logging
    logger = setup_logging(__name__)
except ImportError:
    # Fallback if logger_config.py is not present
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

class PDFTableExtractor:
    """
    A comprehensive table extraction pipeline for PDFs that handles various types of tables.
    """
    
    def __init__(self, 
                 use_ocr: bool = True, 
                 ocr_lang: str = 'eng',
                 dpi: int = 300,
                 confidence_threshold: float = 50.0,
                 tesseract_path: Optional[str] = None):
        """
        Initialize the PDF Table Extractor.
        
        Args:
            use_ocr: Whether to use OCR for scanned documents
            ocr_lang: Language for OCR (default: English)
            dpi: DPI for image conversion (higher means better quality but slower)
            confidence_threshold: Minimum confidence score for OCR results
            tesseract_path: Path to the Tesseract executable (if not in PATH)
        """
        self.use_ocr = use_ocr
        self.ocr_lang = ocr_lang
        self.dpi = dpi
        self.confidence_threshold = confidence_threshold

        logger.info(
            f"PDFTableExtractor init | use_ocr={use_ocr}, ocr_lang={ocr_lang}, "
            f"dpi={dpi}, confidence_threshold={confidence_threshold}"
        )

        # Set Tesseract path if provided
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
            logger.debug(f"Tesseract path set to: {tesseract_path}")

        # Validate external dependencies
        self._validate_dependencies()
    
    def _validate_dependencies(self):
        """Check if external dependencies are properly installed."""
        logger.debug("Validating external dependencies...")
        try:
            if self.use_ocr:
                tess_ver = pytesseract.get_tesseract_version()
                logger.info(f"Tesseract OK | version={tess_ver}")
        except Exception as e:
            logger.warning(f"Tesseract validation failed: {e} — OCR may not work")

        try:
            import tabula  # noqa: F401
            logger.debug("tabula-py: OK")
        except ImportError:
            logger.warning("tabula-py not found — lattice/stream extraction unavailable")

        try:
            import camelot  # noqa: F401
            logger.debug("camelot-py: OK")
        except ImportError:
            logger.warning("camelot-py not found — camelot extraction unavailable")

        try:
            import pdfplumber  # noqa: F401
            logger.debug("pdfplumber: OK")
        except ImportError:
            logger.warning("pdfplumber not found — pdfplumber extraction unavailable")
    
    def analyze_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Analyze the PDF to determine its characteristics.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with PDF analysis results
        """
        _t0 = time.time()
        fname = os.path.basename(pdf_path)
        logger.info(f"analyze_pdf | START | file={fname}")

        pdf_info = {
            "path": pdf_path,
            "pages": 0,
            "has_text": False,
            "is_scanned": False,
            "page_dimensions": [],
            "text_density": []
        }

        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            file_size_kb = os.path.getsize(pdf_path) / 1024
            logger.debug(f"analyze_pdf | file_size={file_size_kb:.1f} KB")

            with pdfplumber.open(pdf_path) as pdf:
                pdf_info["pages"] = len(pdf.pages)
                logger.debug(f"analyze_pdf | total_pages={pdf_info['pages']}")

                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    width, height = float(page.width), float(page.height)
                    pdf_info["page_dimensions"].append((width, height))

                    text_density = len(text) / (width * height) if width * height > 0 else 0
                    pdf_info["text_density"].append(text_density)

                    logger.debug(
                        f"analyze_pdf | page={i+1}/{pdf_info['pages']} | "
                        f"dims={width:.0f}x{height:.0f} | "
                        f"text_len={len(text)} | density={text_density:.6f}"
                    )

            avg_density = (
                sum(pdf_info["text_density"]) / len(pdf_info["text_density"])
                if pdf_info["text_density"] else 0
            )
            pdf_info["has_text"]   = avg_density > 0.001
            pdf_info["is_scanned"] = avg_density < 0.001

            elapsed = time.time() - _t0
            logger.info(
                f"analyze_pdf | DONE | pages={pdf_info['pages']} | "
                f"has_text={pdf_info['has_text']} | is_scanned={pdf_info['is_scanned']} | "
                f"avg_density={avg_density:.6f} | elapsed={elapsed:.2f}s"
            )

        except Exception as e:
            logger.error(f"analyze_pdf | ERROR | {e}\n{traceback.format_exc()}")

        return pdf_info
    
    def extract_tables(self, pdf_path: str, pages: Union[str, List[int]] = 'all') -> Dict[int, List[pd.DataFrame]]:
        """
        Extract tables from a PDF using multiple methods.
        
        Args:
            pdf_path: Path to the PDF file
            pages: Page numbers to process ('all' or list of page numbers starting from 1)
            
        Returns:
            Dictionary mapping page numbers to lists of extracted tables (as pandas DataFrames)
        """
        _t0 = time.time()
        fname = os.path.basename(pdf_path)
        logger.info(f"extract_tables | START | file={fname} | requested_pages={pages}")

        pdf_info = self.analyze_pdf(pdf_path)

        if pages == 'all':
            pages_to_process = list(range(1, pdf_info["pages"] + 1))
        else:
            pages_to_process = pages

        logger.info(
            f"extract_tables | pages_to_process={pages_to_process} "
            f"({len(pages_to_process)} page(s))"
        )

        results = {}
        for page_num in pages_to_process:
            _pt = time.time()
            logger.info(f"extract_tables | processing page {page_num}/{pdf_info['pages']}")
            page_tables = self._extract_tables_from_page(pdf_path, page_num, pdf_info)
            results[page_num] = page_tables
            logger.info(
                f"extract_tables | page {page_num} done | "
                f"tables_found={len(page_tables)} | page_elapsed={time.time()-_pt:.2f}s"
            )

        total_tables = sum(len(v) for v in results.values())
        logger.info(
            f"extract_tables | DONE | total_tables={total_tables} | "
            f"total_elapsed={time.time()-_t0:.2f}s"
        )
        return results
    
    def _extract_tables_from_page(self, pdf_path: str, page_num: int, pdf_info: Dict[str, Any]) -> List[pd.DataFrame]:
        """
        Extract tables from a single PDF page using multiple methods.
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number to process (starting from 1)
            pdf_info: PDF analysis information
            
        Returns:
            List of extracted tables (as pandas DataFrames)
        """
        _t0 = time.time()
        logger.debug(
            f"_extract_tables_from_page | page={page_num} | "
            f"has_text={pdf_info['has_text']} | is_scanned={pdf_info['is_scanned']}"
        )
        tables = []

        if pdf_info["has_text"]:
            logger.debug(f"_extract_tables_from_page | page={page_num} | trying text-based extraction")
            text_based_tables = self._extract_text_based_tables(pdf_path, page_num)
            tables.extend(text_based_tables)
            logger.debug(
                f"_extract_tables_from_page | page={page_num} | "
                f"text-based found {len(text_based_tables)} table(s)"
            )

        if (not tables or pdf_info["is_scanned"]) and self.use_ocr:
            logger.debug(
                f"_extract_tables_from_page | page={page_num} | "
                f"falling back to OCR (tables_so_far={len(tables)}, is_scanned={pdf_info['is_scanned']})"
            )
            ocr_tables = self._extract_tables_with_ocr(pdf_path, page_num)
            tables.extend(ocr_tables)
            logger.debug(
                f"_extract_tables_from_page | page={page_num} | "
                f"OCR found {len(ocr_tables)} table(s)"
            )

        tables = self._post_process_tables(tables)

        logger.info(
            f"_extract_tables_from_page | page={page_num} | "
            f"final_tables={len(tables)} | elapsed={time.time()-_t0:.2f}s"
        )
        for i, tbl in enumerate(tables):
            logger.debug(
                f"_extract_tables_from_page | page={page_num} table[{i}] | "
                f"shape={tbl.shape} | cols={list(tbl.columns)[:5]}"
            )
        return tables
    
    def _extract_text_based_tables(self, pdf_path: str, page_num: int) -> List[pd.DataFrame]:
        """
        Extract tables from text-based PDFs using libraries like Tabula and Camelot.
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number to process (starting from 1)
            
        Returns:
            List of extracted tables (as pandas DataFrames)
        """
        tables = []
        _t0 = time.time()
        page_str = str(page_num)
        logger.info(f"_extract_text_based_tables | START | page={page_num}")

        # ── Method 1: Tabula ──────────────────────────────────────────────────
        try:
            _t = time.time()
            logger.debug(f"_extract_text_based_tables | page={page_num} | Tabula lattice mode...")
            tabula_tables = tabula.read_pdf(
                pdf_path, pages=page_num, multiple_tables=True, guess=True, lattice=True
            )
            if tabula_tables:
                logger.info(
                    f"_extract_text_based_tables | page={page_num} | "
                    f"Tabula lattice found {len(tabula_tables)} table(s) | {time.time()-_t:.2f}s"
                )
                tables.extend(tabula_tables)

            if not tabula_tables:
                logger.debug(f"_extract_text_based_tables | page={page_num} | Tabula stream mode...")
                tabula_tables = tabula.read_pdf(
                    pdf_path, pages=page_num, multiple_tables=True, guess=True, stream=True
                )
                if tabula_tables:
                    logger.info(
                        f"_extract_text_based_tables | page={page_num} | "
                        f"Tabula stream found {len(tabula_tables)} table(s) | {time.time()-_t:.2f}s"
                    )
                    tables.extend(tabula_tables)
                else:
                    logger.debug(f"_extract_text_based_tables | page={page_num} | Tabula: no tables found")
        except Exception as e:
            logger.warning(f"_extract_text_based_tables | page={page_num} | Tabula failed: {e}")

        # ── Method 2: Camelot ─────────────────────────────────────────────────
        try:
            _t = time.time()
            logger.debug(f"_extract_text_based_tables | page={page_num} | Camelot lattice mode...")
            camelot_tables = camelot.read_pdf(
                pdf_path, pages=page_str, flavor='lattice', line_scale=40
            )
            if camelot_tables and len(camelot_tables) > 0:
                accepted = [t for t in camelot_tables if t.accuracy > 80]
                logger.info(
                    f"_extract_text_based_tables | page={page_num} | "
                    f"Camelot lattice: {len(camelot_tables)} raw, {len(accepted)} accepted (acc>80) | "
                    f"{time.time()-_t:.2f}s"
                )
                for t in accepted:
                    logger.debug(
                        f"_extract_text_based_tables | page={page_num} | "
                        f"Camelot lattice table shape={t.df.shape} accuracy={t.accuracy:.1f}"
                    )
                    tables.append(t.df)

            _t = time.time()
            logger.debug(f"_extract_text_based_tables | page={page_num} | Camelot stream mode...")
            camelot_tables = camelot.read_pdf(
                pdf_path, pages=page_str, flavor='stream', edge_tol=100, row_tol=10
            )
            if camelot_tables and len(camelot_tables) > 0:
                accepted = [t for t in camelot_tables if t.accuracy > 80]
                logger.info(
                    f"_extract_text_based_tables | page={page_num} | "
                    f"Camelot stream: {len(camelot_tables)} raw, {len(accepted)} accepted (acc>80) | "
                    f"{time.time()-_t:.2f}s"
                )
                for t in accepted:
                    tables.append(t.df)
        except Exception as e:
            logger.warning(f"_extract_text_based_tables | page={page_num} | Camelot failed: {e}")

        # ── Method 3: PDFPlumber ──────────────────────────────────────────────
        try:
            _t = time.time()
            logger.debug(f"_extract_text_based_tables | page={page_num} | PDFPlumber...")
            with pdfplumber.open(pdf_path) as pdf:
                if page_num <= len(pdf.pages):
                    page = pdf.pages[page_num - 1]
                    pdfplumber_tables = page.extract_tables()
                    if pdfplumber_tables:
                        logger.info(
                            f"_extract_text_based_tables | page={page_num} | "
                            f"PDFPlumber found {len(pdfplumber_tables)} table(s) | {time.time()-_t:.2f}s"
                        )
                        for table in pdfplumber_tables:
                            if table and len(table) > 0:
                                df = pd.DataFrame(table[1:], columns=table[0] if table[0] else None)
                                logger.debug(
                                    f"_extract_text_based_tables | page={page_num} | "
                                    f"PDFPlumber table shape={df.shape}"
                                )
                                tables.append(df)
                    else:
                        logger.debug(f"_extract_text_based_tables | page={page_num} | PDFPlumber: no tables")
        except Exception as e:
            logger.warning(f"_extract_text_based_tables | page={page_num} | PDFPlumber failed: {e}")

        logger.info(
            f"_extract_text_based_tables | DONE | page={page_num} | "
            f"total_tables={len(tables)} | elapsed={time.time()-_t0:.2f}s"
        )
        return tables
    
    def _extract_tables_with_ocr(self, pdf_path: str, page_num: int) -> List[pd.DataFrame]:
        """
        Extract tables from scanned PDFs using OCR and image processing.
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number to process (starting from 1)
            
        Returns:
            List of extracted tables (as pandas DataFrames)
        """
        _t0 = time.time()
        logger.info(f"_extract_tables_with_ocr | START | page={page_num} | dpi={self.dpi}")
        tables = []

        try:
            logger.debug(f"_extract_tables_with_ocr | page={page_num} | converting PDF page to image...")

            # Convert PDF page to image
            try:
                # Try without explicit poppler path first
                images = convert_from_path(pdf_path, dpi=self.dpi, first_page=page_num, last_page=page_num)
            except Exception as e:
                # If that fails, try various fallback paths
                logger.warning(f"Failed to convert without explicit poppler path: {e}. Trying alternatives...")
                try:
                    # Common Windows installation path
                    images = convert_from_path(pdf_path, dpi=self.dpi, first_page=page_num, last_page=page_num,
                                            poppler_path=r"C:\Program Files (x86)\poppler-24.08.0\Library\bin")
                except Exception:
                    try:
                        # Another common Windows path
                        images = convert_from_path(pdf_path, dpi=self.dpi, first_page=page_num, last_page=page_num,
                                                poppler_path=r"C:\Program Files\poppler-24.08.0\Library\bin")
                    except Exception:
                        try:
                            # Common Linux path
                            images = convert_from_path(pdf_path, dpi=self.dpi, first_page=page_num, last_page=page_num,
                                                    poppler_path="/usr/bin")
                        except Exception as final_e:
                            logger.error(f"Failed to convert PDF to image: {final_e}")
                            return tables
                
            if not images:
                logger.warning(f"_extract_tables_with_ocr | page={page_num} | PDF→image conversion returned no images")
                return tables

            image = images[0]
            img_w, img_h = image.size
            logger.debug(
                f"_extract_tables_with_ocr | page={page_num} | "
                f"image size={img_w}x{img_h} px"
            )

            # Apply preprocessing for better OCR quality
            img_np = np.array(image)
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )
            kernel = np.ones((1, 1), np.uint8)
            dilated = cv2.dilate(binary, kernel, iterations=1)
            denoised = cv2.fastNlMeansDenoising(dilated, h=10)
            processed_image = Image.fromarray(denoised)
            logger.debug(f"_extract_tables_with_ocr | page={page_num} | image preprocessed")

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                temp_path = tmp.name
                processed_image.save(temp_path, 'PNG')

            logger.debug(f"_extract_tables_with_ocr | page={page_num} | running image-based table detection...")
            tables = self._detect_and_extract_tables_from_image(temp_path)
            os.unlink(temp_path)

        except Exception as e:
            logger.error(
                f"_extract_tables_with_ocr | page={page_num} | ERROR: {e}\n{traceback.format_exc()}"
            )

        logger.info(
            f"_extract_tables_with_ocr | DONE | page={page_num} | "
            f"tables={len(tables)} | elapsed={time.time()-_t0:.2f}s"
        )
        return tables
    
    def _detect_and_extract_tables_from_image(self, image_path: str) -> List[pd.DataFrame]:
        """
        Detect and extract tables from an image using OpenCV and OCR.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            List of extracted tables (as pandas DataFrames)
        """
        tables = []
        
        try:
            # Read the image
            img = cv2.imread(image_path)
            if img is None:
                logger.error(f"Failed to read image: {image_path}")
                return tables
            
            # Preprocess the image
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Apply thresholding to get binary image
            _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
            
            # Dilate to connect table lines
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(thresh, kernel, iterations=3)
            
            # Find contours
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Filter contours by size to find potential tables
            image_area = img.shape[0] * img.shape[1]
            min_table_area = image_area * 0.05  # Minimum size to consider as a table
            
            table_contours = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                
                # Filter by size and aspect ratio
                if area > min_table_area and 0.2 < w/h < 5:
                    table_contours.append((x, y, w, h))
            
            logger.info(f"Detected {len(table_contours)} potential tables in the image")
            
            # Process each detected table region
            for i, (x, y, w, h) in enumerate(table_contours):
                # Extract the table region
                table_region = img[y:y+h, x:x+w]
                
                # Use OCR to extract text
                try:
                    # Save to temporary file
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                        temp_region_path = tmp.name
                        cv2.imwrite(temp_region_path, table_region)
                    
                    # Try to detect table structure
                    table_df = self._extract_structured_table_from_image(temp_region_path)
                    
                    if table_df is not None and not table_df.empty:
                        tables.append(table_df)
                    else:
                        # Fallback: Extract text and try to infer table structure
                        ocr_text = pytesseract.image_to_string(
                            Image.open(temp_region_path),
                            lang=self.ocr_lang,
                            config='--psm 6 --oem 3 -c preserve_interword_spaces=1'
                        )
                        
                        # Try to convert OCR text to table
                        table_df = self._convert_ocr_text_to_table(ocr_text)
                        if table_df is not None and not table_df.empty:
                            tables.append(table_df)
                    
                    # Clean up temporary file
                    os.unlink(temp_region_path)
                    
                except Exception as e:
                    logger.warning(f"Error processing table region {i}: {e}")
            
        except Exception as e:
            logger.error(f"Error in table detection from image: {e}")
        
        return tables
    
    def _extract_structured_table_from_image(self, image_path: str) -> Optional[pd.DataFrame]:
        """
        Extract a structured table from an image using OpenCV line detection.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Pandas DataFrame containing the table or None if no table is found
        """
        try:
            # Read the image
            img = cv2.imread(image_path)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Detect horizontal and vertical lines
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
            
            horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)
            vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=2)
            
            # Combine horizontal and vertical lines
            table_grid = cv2.add(horizontal_lines, vertical_lines)
            
            # Find contours of grid cells
            contours, _ = cv2.findContours(table_grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            
            # Sort contours by position (top to bottom, left to right)
            def sort_contours(cnts):
                # Sort by Y first (top to bottom)
                y_sorted = sorted(cnts, key=lambda c: cv2.boundingRect(c)[1])
                
                # Group by rows
                row_threshold = 10  # Pixels
                rows = []
                current_row = [y_sorted[0]]
                
                for contour in y_sorted[1:]:
                    x, y, w, h = cv2.boundingRect(contour)
                    prev_x, prev_y, prev_w, prev_h = cv2.boundingRect(current_row[-1])
                    
                    if abs(y - prev_y) <= row_threshold:
                        # Same row
                        current_row.append(contour)
                    else:
                        # New row
                        rows.append(sorted(current_row, key=lambda c: cv2.boundingRect(c)[0]))
                        current_row = [contour]
                
                if current_row:
                    rows.append(sorted(current_row, key=lambda c: cv2.boundingRect(c)[0]))
                
                return rows
            
            # If we found enough contours, try to organize them into a table
            if len(contours) > 4:  # At least a 2x2 table
                sorted_contours = sort_contours(contours)
                
                # Extract text from each cell
                table_data = []
                for row in sorted_contours:
                    row_data = []
                    for contour in row:
                        x, y, w, h = cv2.boundingRect(contour)
                        cell_img = gray[y:y+h, x:x+w]
                        
                        # Apply OCR to the cell
                        text = pytesseract.image_to_string(
                            Image.fromarray(cell_img),
                            lang=self.ocr_lang,
                            config='--psm 7 --oem 3'  # Single text line OCR
                        ).strip()
                        
                        row_data.append(text)
                    
                    if row_data:
                        table_data.append(row_data)
                
                # Create DataFrame
                if table_data and len(table_data) > 1:
                    # Use first row as header
                    header = table_data[0]
                    data = table_data[1:]
                    
                    # Make sure all rows have the same number of columns
                    max_cols = max(len(row) for row in table_data)
                    data = [row + [''] * (max_cols - len(row)) for row in data]
                    header = header + [''] * (max_cols - len(header))
                    
                    # Ensure unique column names
                    unique_headers = []
                    header_count = {}
                    
                    for h in header:
                        h_str = str(h)
                        if h_str in header_count:
                            header_count[h_str] += 1
                            unique_headers.append(f"{h_str}_{header_count[h_str]}")
                        else:
                            header_count[h_str] = 0
                            unique_headers.append(h_str)
                    
                    return pd.DataFrame(data, columns=unique_headers)
            
            # If structured approach didn't work, try tesseract's built-in table detection
            tesseract_data = pytesseract.image_to_data(
                Image.open(image_path),
                lang=self.ocr_lang,
                config='--psm 6 -c preserve_interword_spaces=1',
                output_type=pytesseract.Output.DATAFRAME
            )
            
            # Clean and filter the OCR data
            filtered_data = tesseract_data[tesseract_data['conf'] >= self.confidence_threshold]
            if not filtered_data.empty:
                # Try to infer table structure from text positions
                return self._infer_table_from_ocr_data(filtered_data)
            
        except Exception as e:
            logger.warning(f"Error extracting structured table from image: {e}")
        
        return None
    
    def _infer_table_from_ocr_data(self, ocr_data: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Infer table structure from OCR positional data.
        
        Args:
            ocr_data: DataFrame with OCR results including positional data
            
        Returns:
            Pandas DataFrame containing the inferred table or None if inference fails
        """
        try:
            # Group text by line (based on top position)
            line_tolerance = 5  # Pixels
            ocr_data = ocr_data.sort_values(by=['top', 'left'])
            
            current_line = 0
            current_top = None
            ocr_data['line_num'] = 0
            
            for idx, row in ocr_data.iterrows():
                if current_top is None or abs(row['top'] - current_top) > line_tolerance:
                    current_line += 1
                    current_top = row['top']
                ocr_data.at[idx, 'line_num'] = current_line
            
            # Group words into cells based on horizontal spacing
            space_threshold = 20  # Pixels
            current_line = 0
            current_cell = 0
            last_right = 0
            ocr_data['cell_num'] = 0
            
            for idx, row in ocr_data.iterrows():
                if row['line_num'] != current_line:
                    current_line = row['line_num']
                    current_cell = 0
                    last_right = 0
                
                if last_right == 0 or (row['left'] - last_right) > space_threshold:
                    current_cell += 1
                
                ocr_data.at[idx, 'cell_num'] = current_cell
                last_right = row['left'] + row['width']
            
            # Construct table from lines and cells
            table_data = []
            for line_num, line_group in ocr_data.groupby('line_num'):
                row_data = []
                for cell_num, cell_group in line_group.groupby('cell_num'):
                    cell_text = ' '.join(cell_group['text'].astype(str))
                    row_data.append(cell_text)
                table_data.append(row_data)
            
            # Create DataFrame
            if table_data and len(table_data) > 1:
                # Use first row as header
                header = table_data[0]
                data = table_data[1:]
                
                # Make sure all rows have the same number of columns
                max_cols = max(len(row) for row in table_data)
                data = [row + [''] * (max_cols - len(row)) for row in data]
                header = header + [''] * (max_cols - len(header))
                
                # Ensure unique column names
                unique_headers = []
                header_count = {}
                
                for h in header:
                    h_str = str(h)
                    if h_str in header_count:
                        header_count[h_str] += 1
                        unique_headers.append(f"{h_str}_{header_count[h_str]}")
                    else:
                        header_count[h_str] = 0
                        unique_headers.append(h_str)
                
                return pd.DataFrame(data, columns=unique_headers)
            
        except Exception as e:
            logger.warning(f"Error inferring table structure: {e}")
        
        return None
    
    def _convert_ocr_text_to_table(self, text: str) -> Optional[pd.DataFrame]:
        """
        Convert OCR text to a table structure.
        
        Args:
            text: OCR text output
            
        Returns:
            Pandas DataFrame containing the inferred table or None if inference fails
        """
        if not text or len(text.strip()) == 0:
            return None
        
        try:
            # Split text into lines
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            if len(lines) < 2:  # Need at least header and one data row
                return None
            
            # Try to split by consistent delimiters
            for delimiter in ['\t', '  ', ' | ', ' - ', ';', ',']:
                # Check if delimiter is consistent across lines
                first_row = lines[0].split(delimiter)
                if len(first_row) > 1:
                    consistent = True
                    for line in lines[1:]:
                        if len(line.split(delimiter)) != len(first_row):
                            consistent = False
                            break
                    
                    if consistent:
                        # Split all lines by this delimiter
                        table_data = [line.split(delimiter) for line in lines]
                        header = table_data[0]
                        data = table_data[1:]
                        
                        # Ensure unique column names
                        unique_headers = []
                        header_count = {}
                        
                        for h in header:
                            h_str = str(h)
                            if h_str in header_count:
                                header_count[h_str] += 1
                                unique_headers.append(f"{h_str}_{header_count[h_str]}")
                            else:
                                header_count[h_str] = 0
                                unique_headers.append(h_str)
                        
                        return pd.DataFrame(data, columns=unique_headers)
            
            # If no consistent delimiter, try fixed width parsing
            # Find column boundaries by looking for consistent whitespace
            col_boundaries = []
            for i in range(1, len(lines[0])):
                is_boundary = True
                for line in lines:
                    if i >= len(line) or not line[i].isspace():
                        is_boundary = False
                        break
                if is_boundary:
                    col_boundaries.append(i)
            
            if col_boundaries:
                # Extract columns using boundaries
                table_data = []
                for line in lines:
                    row = []
                    start_idx = 0
                    for boundary in col_boundaries:
                        row.append(line[start_idx:boundary].strip())
                        start_idx = boundary + 1
                    row.append(line[start_idx:].strip())
                    table_data.append(row)
                
                header = table_data[0]
                data = table_data[1:]
                
                # Ensure unique column names
                unique_headers = []
                header_count = {}
                
                for h in header:
                    h_str = str(h)
                    if h_str in header_count:
                        header_count[h_str] += 1
                        unique_headers.append(f"{h_str}_{header_count[h_str]}")
                    else:
                        header_count[h_str] = 0
                        unique_headers.append(h_str)
                
                return pd.DataFrame(data, columns=unique_headers)
            
        except Exception as e:
            logger.warning(f"Error converting OCR text to table: {e}")
        
        return None
    
    def _clean_table(self, table: pd.DataFrame) -> pd.DataFrame:
        """
        Clean up a table by removing empty rows/columns and standardizing values.
        Also handles duplicate column names.
        
        Args:
            table: Table to clean
            
        Returns:
            Cleaned table
        """
        # Make a copy to avoid modifying the original
        df = table.copy()
        
        # Handle duplicate column names
        if df.columns.duplicated().any():
            # Create a list to track column names we've seen
            seen_columns = {}
            new_columns = []
            
            for idx, col in enumerate(df.columns):
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
            df.columns = new_columns
        
        # Convert all values to strings and strip whitespace
        df = df.astype(str)
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        
        # Replace values that indicate empty cells
        empty_values = ['nan', 'None', 'null', 'NA', 'N/A', '-']
        for val in empty_values:
            df = df.replace(val, '')
        
        # Remove empty rows
        df = df.loc[~df.apply(lambda x: x.astype(str).str.strip().eq('').all(), axis=1)]
        
        # Remove empty columns
        df = df.loc[:, ~df.apply(lambda x: x.astype(str).str.strip().eq('').all(), axis=0)]
        
        # Reset index
        df = df.reset_index(drop=True)
        
        return df
    
    def get_page_as_image(self, pdf_path, page_num, dpi=300):
        """
        Convert a specific PDF page to a high-quality image.
        
        Args:
            pdf_path: Path to the PDF file
            page_num: Page number to process (starting from 1)
            dpi: DPI for image resolution (higher = better quality but larger file)
            
        Returns:
            PIL Image object of the page or None if conversion fails
        """
        try:
            import fitz  # PyMuPDF
            
            # Use Document instead of open for better compatibility with PyMuPDF versions
            doc = fitz.Document(pdf_path)
            
            # Check if page number is valid
            if page_num < 1 or page_num > len(doc):
                logger.error(f"Page {page_num} does not exist. PDF has {len(doc)} pages.")
                return None
            
            # Get the specified page (0-based index)
            page = doc[page_num - 1]
            
            # Render page to a pixmap with high resolution
            zoom = dpi / 72  # Standard PDF DPI is 72
            matrix = fitz.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix)
            
            # Convert to PIL Image
            from PIL import Image
            import io
            img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            
            # Close the document
            doc.close()
            
            return img
        except Exception as e:
            logger.error(f"Error converting PDF page to image: {e}")
            return None
    
    
    def _generate_table_fingerprint(self, table: pd.DataFrame) -> str:
        """
        Generate a fingerprint for a table to identify duplicates.
        
        Args:
            table: Table to fingerprint
            
        Returns:
            Fingerprint string
        """
        # Use shape, column names, and first/last few values as fingerprint
        shape_str = f"{table.shape[0]}x{table.shape[1]}"
        cols_str = "_".join(str(col) for col in table.columns[:3])
        
        # Get values from first and last rows (if they exist)
        values_str = ""
        if len(table) > 0:
            first_row = "_".join(str(val) for val in table.iloc[0].values[:3])
            values_str += first_row
        
        if len(table) > 1:
            last_row = "_".join(str(val) for val in table.iloc[-1].values[:3])
            values_str += "_" + last_row
        
        return f"{shape_str}_{cols_str}_{values_str}"
    
    def _post_process_tables(self, tables: List[pd.DataFrame]) -> List[pd.DataFrame]:
        """
        Post-process extracted tables to remove duplicates and clean up.
        
        Args:
            tables: List of extracted tables
            
        Returns:
            List of processed tables
        """
        if not tables:
            return []
        
        processed_tables = []
        unique_fingerprints = set()
        
        for table in tables:
            if table is None or table.empty:
                continue
            
            # Clean up the table
            table = self._clean_table(table)
            
            # Generate a fingerprint for deduplication
            fingerprint = self._generate_table_fingerprint(table)
            
            if fingerprint not in unique_fingerprints:
                unique_fingerprints.add(fingerprint)
                processed_tables.append(table)
        
        return processed_tables
    
    def save_tables(self, tables_dict: Dict[int, List[pd.DataFrame]], output_dir: str, 
                   format: str = 'csv', prefix: str = 'table') -> List[str]:
        """
        Save extracted tables to files.
        
        Args:
            tables_dict: Dictionary mapping page numbers to lists of tables
            output_dir: Directory to save the tables
            format: Output format ('csv', 'excel', or 'json')
            prefix: Prefix for output filenames
            
        Returns:
            List of saved file paths
        """
        _t0 = time.time()
        total_input = sum(len(v) for v in tables_dict.values())
        logger.info(
            f"save_tables | START | format={format} | output_dir={output_dir} | "
            f"total_tables={total_input} | prefix={prefix}"
        )

        os.makedirs(output_dir, exist_ok=True)
        saved_files = []

        for page_num, tables in tables_dict.items():
            for i, table in enumerate(tables):
                if table is None or table.empty:
                    logger.debug(f"save_tables | page={page_num} table[{i}] | skipped (empty)")
                    continue

                filename = f"{prefix}_page{page_num}_table{i+1}.{format}"
                filepath = os.path.join(output_dir, filename)

                try:
                    if format == 'csv':
                        table.to_csv(filepath, index=False)
                    elif format == 'excel':
                        table.to_excel(filepath, index=False)
                    elif format == 'json':
                        table.to_json(filepath, orient='records')
                    else:
                        logger.warning(f"save_tables | unsupported format: {format}")
                        continue

                    file_kb = os.path.getsize(filepath) / 1024
                    logger.info(
                        f"save_tables | saved page={page_num} table[{i+1}] | "
                        f"shape={table.shape} | file={filename} | {file_kb:.1f} KB"
                    )
                    saved_files.append(filepath)

                except Exception as e:
                    logger.error(
                        f"save_tables | page={page_num} table[{i+1}] | "
                        f"ERROR saving {filepath}: {e}\n{traceback.format_exc()}"
                    )

        logger.info(
            f"save_tables | DONE | saved={len(saved_files)}/{total_input} | "
            f"elapsed={time.time()-_t0:.2f}s"
        )
        return saved_files

def main():
    """Example usage of the PDFTableExtractor class."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract tables from PDF files")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--output", "-o", default="extracted_tables", help="Output directory")
    parser.add_argument("--format", "-f", default="csv", choices=["csv", "excel", "json"], help="Output format")
    parser.add_argument("--pages", "-p", default="all", help="Pages to process (comma-separated or 'all')")
    parser.add_argument("--ocr", action="store_true", help="Use OCR for table extraction")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for image conversion")
    parser.add_argument("--lang", default="eng", help="OCR language")
    
    args = parser.parse_args()
    
    # Parse pages argument
    if args.pages != 'all':
        try:
            pages = [int(p) for p in args.pages.split(',')]
        except ValueError:
            print("Error: Pages should be comma-separated integers or 'all'")
            return
    else:
        pages = 'all'
    
    # Initialize extractor
    extractor = PDFTableExtractor(
        use_ocr=args.ocr,
        ocr_lang=args.lang,
        dpi=args.dpi
    )
    
    # Extract tables
    print(f"Extracting tables from {args.pdf_path}")
    tables = extractor.extract_tables(args.pdf_path, pages)
    
    # Save tables
    saved_files = extractor.save_tables(tables, args.output, args.format)
    
    print(f"Extracted {sum(len(tables_list) for tables_list in tables.values())} tables")
    print(f"Saved {len(saved_files)} files to {args.output}")

if __name__ == "__main__":
    main()