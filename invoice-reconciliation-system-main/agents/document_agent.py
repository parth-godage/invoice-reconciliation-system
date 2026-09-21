"""
Document Intelligence Agent
---------------------------

Production-oriented invoice document extraction agent.

Responsibilities:
- Detect PDF/image documents
- Extract native PDF text
- Fall back to OCR for scanned PDFs/images
- Extract invoice metadata
- Extract ALL line items from common PDF table layouts
- Normalize extracted values
- Calculate extraction confidence
- Return structured data compatible with the reconciliation graph
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pdf2image import convert_from_path

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None
    PDFPLUMBER_AVAILABLE = False

try:
    from PIL import Image
    import pytesseract

    OCR_AVAILABLE = True
except ImportError:
    Image = None
    pytesseract = None
    OCR_AVAILABLE = False


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class DocumentType(Enum):
    PDF = "pdf"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ExtractionMethod(Enum):
    NATIVE_PDF = "native_pdf"
    OCR = "ocr"
    FAILED = "failed"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class AgentOutput:
    data: Dict[str, Any]
    confidence: float
    explanation: str
    metadata: Dict[str, Any]


@dataclass
class InvoiceData:
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_reference: Optional[str] = None

    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None

    customer_name: Optional[str] = None
    customer_address: Optional[str] = None

    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: Optional[str] = None

    line_items: List[Dict[str, Any]] = None

    payment_terms: Optional[str] = None
    raw_text: Optional[str] = None

    def __post_init__(self):
        if self.line_items is None:
            self.line_items = []


# ============================================================================
# AGENT
# ============================================================================

class DocumentIntelligenceAgent:
    """
    Extract structured invoice information from PDF/image documents.

    The extraction strategy is:

        Native PDF text
              |
              +--> table extraction
              |
              +--> line-based fallback
              |
              v
        structured invoice

    If native PDF extraction is unusable:

        PDF -> image -> OCR -> structured invoice
    """

    def __init__(self, tesseract_cmd: Optional[str] = None):
        if tesseract_cmd and OCR_AVAILABLE:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        self.poppler_path = os.getenv(
            "POPPLER_PATH",
            r"C:\poppler\poppler-25.12.0\Library\bin",
        )

        self._check_dependencies()

    # ========================================================================
    # DEPENDENCY CHECK
    # ========================================================================

    def _check_dependencies(self) -> None:
        if not PDFPLUMBER_AVAILABLE:
            logger.warning(
                "pdfplumber is not available. Native PDF extraction disabled."
            )

        if not OCR_AVAILABLE:
            logger.warning(
                "PIL/pytesseract is not available. OCR disabled."
            )

    # ========================================================================
    # MAIN PROCESS
    # ========================================================================

    def process(self, document_path: str) -> AgentOutput:
        try:
            path = Path(document_path)

            if not path.exists():
                return self._create_error_output(
                    f"Document not found: {document_path}"
                )

            doc_type = self._detect_document_type(path)

            if doc_type == DocumentType.UNKNOWN:
                return self._create_error_output(
                    f"Unsupported document type: {path.suffix}"
                )

            extraction_result = self._extract_text(path, doc_type)

            if extraction_result.method == ExtractionMethod.FAILED:
                return self._create_error_output(
                    f"Text extraction failed: {extraction_result.error}"
                )

            raw_text = extraction_result.text or ""

            if len(raw_text.strip()) < 10:
                return self._create_error_output(
                    "Insufficient text extracted from document"
                )

            invoice_data = self._parse_invoice_data(
                raw_text,
                source_path=path,
            )

            confidence = self._calculate_confidence(
                invoice_data,
                raw_text,
                extraction_result.method,
                extraction_result.quality_score,
            )

            explanation = self._generate_explanation(
                invoice_data,
                extraction_result.method,
                confidence,
            )

            output_data = self._prepare_output_data(
                invoice_data,
                raw_text,
            )

            metadata = {
                "document_type": doc_type.value,
                "extraction_method": extraction_result.method.value,
                "text_length": len(raw_text),
                "extraction_quality": extraction_result.quality_score,
                "line_item_count": len(invoice_data.line_items),
                "ocr_used": extraction_result.method == ExtractionMethod.OCR,
            }

            return AgentOutput(
                data=output_data,
                confidence=confidence,
                explanation=explanation,
                metadata=metadata,
            )

        except Exception as exc:
            logger.error(
                "Unexpected document processing error: %s",
                exc,
                exc_info=True,
            )

            return self._create_error_output(
                f"Unexpected error: {exc}"
            )

    # ========================================================================
    # DOCUMENT TYPE
    # ========================================================================

    def _detect_document_type(self, path: Path) -> DocumentType:
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            return DocumentType.PDF

        if suffix in {
            ".jpg",
            ".jpeg",
            ".png",
            ".tiff",
            ".tif",
            ".bmp",
            ".gif",
        }:
            return DocumentType.IMAGE

        return DocumentType.UNKNOWN

    # ========================================================================
    # EXTRACTION RESULT
    # ========================================================================

    @dataclass
    class ExtractionResult:
        text: str
        method: ExtractionMethod
        quality_score: float
        error: Optional[str] = None

    # ========================================================================
    # TEXT EXTRACTION
    # ========================================================================

    def _extract_text(
        self,
        path: Path,
        doc_type: DocumentType,
    ) -> ExtractionResult:

        if doc_type == DocumentType.PDF:
            return self._extract_from_pdf(path)

        if doc_type == DocumentType.IMAGE:
            return self._extract_from_image(path)

        return self.ExtractionResult(
            text="",
            method=ExtractionMethod.FAILED,
            quality_score=0.0,
            error="Unsupported document type",
        )

    # ========================================================================
    # PDF EXTRACTION
    # ========================================================================

    def _extract_from_pdf(self, path: Path) -> ExtractionResult:
        """
        Extract native text from PDF.

        Native extraction is preferred because it preserves:
        - numbers
        - currency
        - line structure
        - table information

        OCR is only used when native extraction is clearly unusable.
        """

        if PDFPLUMBER_AVAILABLE:
            try:
                text_parts: List[str] = []

                with pdfplumber.open(path) as pdf:
                    for page_number, page in enumerate(pdf.pages, start=1):

                        page_text = page.extract_text(
                            x_tolerance=2,
                            y_tolerance=3,
                        )

                        if page_text:
                            text_parts.append(
                                f"\n--- PAGE {page_number} ---\n"
                            )
                            text_parts.append(page_text)

                full_text = "\n".join(text_parts).strip()

                if self._native_text_is_usable(full_text):
                    return self.ExtractionResult(
                        text=full_text,
                        method=ExtractionMethod.NATIVE_PDF,
                        quality_score=0.95,
                    )

                logger.warning(
                    "Native PDF text appears incomplete. Falling back to OCR."
                )

            except Exception as exc:
                logger.warning(
                    "Native PDF extraction failed: %s",
                    exc,
                )

        if OCR_AVAILABLE:
            return self._ocr_pdf_fallback(path)

        return self.ExtractionResult(
            text="",
            method=ExtractionMethod.FAILED,
            quality_score=0.0,
            error=(
                "Native PDF extraction failed and OCR is unavailable."
            ),
        )

    # ========================================================================
    # IMAGE EXTRACTION
    # ========================================================================

    def _extract_from_image(self, path: Path) -> ExtractionResult:
        if not OCR_AVAILABLE:
            return self.ExtractionResult(
                text="",
                method=ExtractionMethod.FAILED,
                quality_score=0.0,
                error="OCR dependencies are unavailable.",
            )

        try:
            image = Image.open(path)
            text = self._ocr_image_text(image)

            if not text.strip():
                return self.ExtractionResult(
                    text="",
                    method=ExtractionMethod.FAILED,
                    quality_score=0.0,
                    error="OCR produced no usable text.",
                )

            return self.ExtractionResult(
                text=text,
                method=ExtractionMethod.OCR,
                quality_score=self._assess_ocr_quality(text),
            )

        except Exception as exc:
            return self.ExtractionResult(
                text="",
                method=ExtractionMethod.FAILED,
                quality_score=0.0,
                error=f"Image OCR failed: {exc}",
            )

    # ========================================================================
    # OCR PDF FALLBACK
    # ========================================================================

    def _ocr_pdf_fallback(self, path: Path) -> ExtractionResult:
        if not OCR_AVAILABLE:
            return self.ExtractionResult(
                text="",
                method=ExtractionMethod.FAILED,
                quality_score=0.0,
                error="OCR is unavailable.",
            )

        try:
            kwargs: Dict[str, Any] = {
                "dpi": 300,
            }

            if self.poppler_path and Path(self.poppler_path).exists():
                kwargs["poppler_path"] = self.poppler_path

            images = convert_from_path(
                str(path),
                **kwargs,
            )

            extracted_pages: List[str] = []

            for index, image in enumerate(images, start=1):
                text = self._ocr_image_text(image)

                if text.strip():
                    extracted_pages.append(
                        f"\n--- PAGE {index} ---\n{text}"
                    )

            extracted_text = "\n".join(extracted_pages).strip()

            if not extracted_text:
                return self.ExtractionResult(
                    text="",
                    method=ExtractionMethod.FAILED,
                    quality_score=0.0,
                    error="OCR produced no usable text.",
                )

            return self.ExtractionResult(
                text=extracted_text,
                method=ExtractionMethod.OCR,
                quality_score=self._assess_ocr_quality(
                    extracted_text
                ),
            )

        except Exception as exc:
            logger.error(
                "PDF OCR fallback failed: %s",
                exc,
            )

            return self.ExtractionResult(
                text="",
                method=ExtractionMethod.FAILED,
                quality_score=0.0,
                error=f"OCR fallback error: {exc}",
            )

    def _ocr_image_text(self, image: Any) -> str:
        """OCR an image with automatic orientation correction."""

        if not OCR_AVAILABLE:
            return ""

        try:
            # Normalize EXIF orientation when available.
            try:
                from PIL import ImageOps
                image = ImageOps.exif_transpose(image)
            except Exception:
                pass

            # First attempt orientation detection. OSD is not always available
            # or reliable, so failure simply falls back to the original image.
            corrected = image
            try:
                osd = pytesseract.image_to_osd(
                    image,
                    config="--psm 0",
                )
                rotate_match = re.search(
                    r"Rotate:\s*(\d+)",
                    osd,
                    re.IGNORECASE,
                )

                if rotate_match:
                    rotate_degrees = int(rotate_match.group(1)) % 360
                    if rotate_degrees:
                        corrected = image.rotate(
                            (360 - rotate_degrees) % 360,
                            expand=True,
                        )
            except Exception:
                corrected = image

            # OCR on the corrected image. PSM 6 is best for structured invoices;
            # PSM 11 is useful for sparse/irregular layouts.
            candidates: List[str] = []

            for psm in (6, 11):
                try:
                    text = pytesseract.image_to_string(
                        corrected,
                        config=f"--psm {psm}",
                    )
                    if text and text.strip():
                        candidates.append(text)
                except Exception:
                    continue

            if not candidates:
                return ""

            return max(
                candidates,
                key=self._ocr_candidate_score,
            )

        except Exception as exc:
            logger.warning("OCR image processing failed: %s", exc)
            return ""

    def _ocr_candidate_score(self, text: str) -> float:
        """Rank OCR candidates using invoice-specific signals."""

        if not text:
            return 0.0

        lower = text.lower()
        score = 0.0

        for signal in (
            "invoice",
            "supplier",
            "vendor",
            "po reference",
            "item",
            "qty",
            "quantity",
            "unit price",
            "line total",
            "subtotal",
            "tax",
            "grand total",
        ):
            if signal in lower:
                score += 2.0

        numeric_count = len(
            re.findall(
                r"\b\d+(?:[.,]\d+)?\b",
                text,
            )
        )
        score += min(numeric_count, 30) * 0.1
        score += min(len(text.strip()), 3000) / 3000.0

        return score

    # ========================================================================
    # NATIVE TEXT QUALITY
    # ========================================================================

    def _native_text_is_usable(self, text: str) -> bool:
        if not text or len(text.strip()) < 30:
            return False

        lower = text.lower()

        invoice_signals = [
            "invoice",
            "subtotal",
            "total",
            "amount",
            "quantity",
            "description",
            "price",
            "vendor",
            "supplier",
        ]

        signal_count = sum(
            1 for signal in invoice_signals
            if signal in lower
        )

        numeric_count = len(
            re.findall(
                r"\b\d+(?:\.\d{1,2})?\b",
                text,
            )
        )

        return signal_count >= 2 and numeric_count >= 3

    # ========================================================================
    # OCR QUALITY
    # ========================================================================

    def _assess_ocr_quality(self, text: str) -> float:
        if not text or len(text.strip()) < 10:
            return 0.0

        score = 1.0

        special_char_ratio = (
            len(re.findall(r"[^\w\s.,$€£¥:/()%#\-]", text))
            / max(len(text), 1)
        )

        if special_char_ratio > 0.10:
            score -= 0.25

        words = text.split()

        if words:
            single_char_ratio = sum(
                1 for word in words if len(word) == 1
            ) / len(words)

            if single_char_ratio > 0.20:
                score -= 0.20

            average_word_length = (
                sum(len(word) for word in words)
                / len(words)
            )

            if average_word_length < 2:
                score -= 0.20

        return max(0.0, min(1.0, score))

    # ========================================================================
    # PARSE INVOICE
    # ========================================================================

    def _parse_invoice_data(
        self,
        text: str,
        source_path: Optional[Path] = None,
    ) -> InvoiceData:

        invoice = InvoiceData(
            raw_text=text
        )

        normalized = self._normalize_text(text)

        invoice.invoice_number = self._extract_invoice_number(
            text,
            normalized,
        )

        invoice.po_reference = self._extract_po_reference(
            text,
            normalized,
        )

        invoice.invoice_date = self._extract_date(
            text,
            normalized,
            "invoice",
        )

        invoice.due_date = self._extract_date(
            text,
            normalized,
            "due",
        )

        invoice.vendor_name = self._extract_vendor_name(
            text,
            normalized,
        )

        invoice.vendor_address = self._extract_address(
            text,
            normalized,
            "vendor",
        )

        invoice.customer_name = self._extract_customer_name(
            text,
            normalized,
        )

        invoice.customer_address = self._extract_address(
            text,
            normalized,
            "customer",
        )

        amounts = self._extract_amounts(
            text,
            normalized,
        )

        invoice.subtotal = amounts.get("subtotal")
        invoice.tax = amounts.get("tax")
        invoice.total = amounts.get("total")
        invoice.currency = amounts.get(
            "currency",
            "USD",
        )

        # IMPORTANT:
        # Try robust table extraction first.
        invoice.line_items = self._extract_line_items(
            text=text,
            source_path=source_path,
        )

        invoice.payment_terms = self._extract_payment_terms(
            text,
            normalized,
        )

        return invoice

    # ========================================================================
    # NORMALIZATION
    # ========================================================================

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n")
        text = text.replace("\r", "\n")

        # Preserve line boundaries.
        lines = [
            re.sub(r"[ \t]+", " ", line).strip()
            for line in text.split("\n")
        ]

        return "\n".join(
            line for line in lines if line
        )

    # ========================================================================
    # INVOICE NUMBER
    # ========================================================================

    def _extract_invoice_number(
        self,
        text: str,
        normalized: str,
    ) -> Optional[str]:

        patterns = [
            r"\binvoice\s*(?:#|number|no\.?|num\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]*)",
            r"\binv\.?\s*(?:#|number|no\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-_\/]*)",
            r"\binvoice\s*[:\-]\s*([A-Z0-9][A-Z0-9\-_\/]*)",
            r"\binvoice\s+([A-Z0-9][A-Z0-9\-_\/]{2,})",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                normalized,
                re.IGNORECASE,
            )

            if match:
                value = match.group(1).strip()

                if value.lower() not in {
                    "date",
                    "number",
                    "no",
                    "total",
                }:
                    return value

        return None

    # ========================================================================
    # DATE
    # ========================================================================

    def _extract_date(
        self,
        text: str,
        normalized: str,
        date_type: str,
    ) -> Optional[str]:
        """Extract and normalize an invoice/due date to ISO YYYY-MM-DD."""

        date_patterns = [
            r"\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b",
            r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b",
            r"\b[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\b",
        ]

        if date_type == "invoice":
            keywords = (
                "invoice date",
                "issued date",
                "billing date",
                "issue date",
                "date",
            )
        else:
            keywords = (
                "due date",
                "payment due",
                "pay by",
                "due",
            )

        lower = normalized.lower()

        # First try the date close to its label.
        for keyword in keywords:
            position = lower.find(keyword)
            if position == -1:
                continue

            window = normalized[
                max(0, position - 40):
                min(len(normalized), position + 140)
            ]

            for pattern in date_patterns:
                match = re.search(pattern, window, re.IGNORECASE)
                if match:
                    return self._normalize_date_value(match.group(0))

        # Fallback: first plausible date for invoice date only.
        if date_type == "invoice":
            for pattern in date_patterns:
                match = re.search(pattern, normalized, re.IGNORECASE)
                if match:
                    return self._normalize_date_value(match.group(0))

        return None

    def _normalize_date_value(self, value: str) -> Optional[str]:
        """Normalize common invoice date formats to YYYY-MM-DD."""

        value = str(value).strip()

        formats = (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d.%m.%Y",
            "%m-%d-%Y",
            "%m/%d/%Y",
            "%m.%d.%Y",
            "%d-%m-%y",
            "%d/%m/%y",
            "%d.%m.%y",
            "%m-%d-%y",
            "%m/%d/%y",
            "%m.%d.%y",
            "%B %d, %Y",
            "%B %d %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%b %d %Y",
            "%d %b %Y",
        )

        for fmt in formats:
            try:
                parsed = datetime.strptime(value, fmt)
                # Treat 2-digit years using Python's standard 1969/2068 window.
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    # ========================================================================
    # VENDOR
    # ========================================================================

    def _extract_vendor_name(
        self,
        text: str,
        normalized: str,
    ) -> Optional[str]:
        """Extract the supplier/vendor name without page labels or dates."""

        lines = [
            line.strip()
            for line in normalized.split("\n")
            if line.strip()
        ]

        # Explicit vendor/supplier labels.
        explicit_patterns = [
            r"(?:vendor|supplier|seller|bill\s*from|from)\s*[:\-]\s*(.+)",
            r"(?:vendor|supplier|seller|bill\s*from|from)\s+(.+)",
        ]

        for pattern in explicit_patterns:
            for line in lines:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    value = self._clean_entity_name(match.group(1))
                    value = self._strip_trailing_date(value)
                    if self._is_valid_vendor_name(value):
                        return value

        # Common generated/invoice layout:
        # Supplier Invoice Date
        # ACME Company 2026-03-08
        for index, line in enumerate(lines):
            if "supplier" in line.lower() or "vendor" in line.lower():
                for candidate in lines[index + 1:index + 4]:
                    value = self._strip_trailing_date(candidate)
                    if self._is_valid_vendor_name(value):
                        return value

        # Look near the top for a company name. Explicitly reject page markers
        # and invoice metadata so "PAGE 1" cannot become the vendor.
        for line in lines[:12]:
            value = self._strip_trailing_date(line)
            if self._is_valid_vendor_name(value):
                return value

        return None

    def _strip_trailing_date(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None

        value = value.strip()

        date_patterns = [
            r"\s+\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\s*$",
            r"\s+\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\s*$",
            r"\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}\s*$",
            r"\s+\d{1,2}\s+[A-Z][a-z]+\s+\d{4}\s*$",
        ]

        for pattern in date_patterns:
            value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()

        return value.strip(" :-|,")

    def _is_valid_vendor_name(self, value: Optional[str]) -> bool:
        if not value:
            return False

        lower = value.lower().strip()

        blocked_exact = {
            "invoice",
            "tax invoice",
            "supplier",
            "vendor",
            "seller",
            "invoice date",
            "supplier invoice date",
            "bill to",
            "ship to",
            "customer",
            "po reference",
            "page",
            "page 1",
            "page 2",
            "page 3",
        }

        if lower in blocked_exact:
            return False

        if lower.startswith("page "):
            return False

        if any(
            phrase in lower
            for phrase in (
                "invoice no",
                "invoice number",
                "invoice date",
                "po reference",
                "item qty",
                "description quantity",
                "grand total",
                "synthetic evaluation invoice",
            )
        ):
            return False

        if re.fullmatch(r"[\d\s$€£¥₹,.\-/:]+", value):
            return False

        return 3 <= len(value) <= 120 and bool(re.search(r"[A-Za-z]", value))

    # ========================================================================
    # CUSTOMER
    # ========================================================================

    def _extract_customer_name(
        self,
        text: str,
        normalized: str,
    ) -> Optional[str]:

        patterns = [
            r"(?:bill\s*to|customer|client|ship\s*to|sold\s*to)\s*[:\-]\s*(.+)",
            r"(?:bill\s*to|customer|client|ship\s*to|sold\s*to)\s+(.+)",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                normalized,
                re.IGNORECASE,
            )

            if match:
                value = self._clean_entity_name(
                    match.group(1)
                )

                if value:
                    return value

        return None

    # ========================================================================
    # ENTITY CLEANING
    # ========================================================================

    def _clean_entity_name(
        self,
        value: str,
    ) -> Optional[str]:

        value = value.strip()

        # Remove trailing invoice fields.
        value = re.split(
            r"\b(?:address|phone|email|invoice|date|total)\b",
            value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        value = value.strip(" :-|,")

        if len(value) < 3:
            return None

        if len(value) > 120:
            value = value[:120].strip()

        return value

    # ========================================================================
    # ADDRESS
    # ========================================================================

    def _extract_address(
        self,
        text: str,
        normalized: str,
        entity_type: str,
    ) -> Optional[str]:

        if entity_type == "vendor":
            name = self._extract_vendor_name(
                text,
                normalized,
            )
        else:
            name = self._extract_customer_name(
                text,
                normalized,
            )

        if not name:
            return None

        position = normalized.lower().find(
            name.lower()
        )

        if position == -1:
            return None

        window = normalized[
            position:position + 300
        ]

        address_pattern = (
            r"\b\d{1,6}\s+"
            r"[A-Za-z0-9 .,#\-]+"
            r"(?:street|st|avenue|ave|road|rd|"
            r"boulevard|blvd|drive|dr|lane|ln|"
            r"way|circle|cir|parkway|pkwy)"
            r"[A-Za-z0-9 .,#\-]*"
            r"(?:\b\d{5}(?:-\d{4})?\b)?"
        )

        match = re.search(
            address_pattern,
            window,
            re.IGNORECASE,
        )

        if match:
            return match.group(0).strip()

        return None

    # ========================================================================
    # AMOUNTS
    # ========================================================================

    def _extract_amounts(
        self,
        text: str,
        normalized: str,
    ) -> Dict[str, Any]:
        """Extract monetary totals without confusing line totals with invoice totals."""

        amounts: Dict[str, Any] = {}

        currency_match = re.search(
            r"([$€£¥₹]|USD|EUR|GBP|JPY|INR)",
            normalized,
            re.IGNORECASE,
        )

        if currency_match:
            currency = currency_match.group(1)
            currency_map = {
                "$": "USD",
                "€": "EUR",
                "£": "GBP",
                "¥": "JPY",
                "₹": "INR",
            }
            amounts["currency"] = currency_map.get(
                currency,
                currency.upper(),
            )
        else:
            amounts["currency"] = "USD"

        # IMPORTANT: use a number pattern that cannot truncate 180018.60 to 180.
        number = r"(-?\d+(?:,\d{3})*(?:\.\d{1,2})?)"

        # Most specific total labels first. Generic "total" is deliberately
        # excluded here because "Line Total" must never be treated as invoice total.
        amounts["total"] = self._extract_labeled_amount(
            normalized,
            [
                "grand total",
                "amount due",
                "total due",
                "balance due",
                "invoice total",
            ],
            number,
        )

        if amounts["total"] is None:
            amounts["total"] = self._extract_generic_total(normalized, number)

        amounts["subtotal"] = self._extract_labeled_amount(
            normalized,
            [
                "subtotal",
                "sub total",
                "net total",
            ],
            number,
        )

        amounts["tax"] = self._extract_labeled_amount(
            normalized,
            [
                "gst / tax",
                "gst/tax",
                "sales tax",
                "tax",
                "vat",
                "gst",
            ],
            number,
        )

        return amounts

    def _extract_labeled_amount(
        self,
        text: str,
        labels: List[str],
        number_pattern: str,
    ) -> Optional[float]:
        """Find a monetary amount on the same logical line as a label."""

        lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in text.splitlines()
            if line.strip()
        ]

        # Longest labels first avoids partial matches.
        labels = sorted(labels, key=len, reverse=True)

        for label in labels:
            label_pattern = re.compile(
                rf"^\s*{re.escape(label)}\s*[:\-]?\s*"
                rf"(?:[$€£¥₹]\s*)?{number_pattern}\s*$",
                re.IGNORECASE,
            )

            for line in lines:
                match = label_pattern.search(line)
                if match:
                    try:
                        return float(match.group(1).replace(",", ""))
                    except (ValueError, TypeError):
                        pass

                # Also allow text before the label, but only when the line
                # still clearly identifies the amount.
                match = re.search(
                    rf"\b{re.escape(label)}\b\s*[:\-]?\s*"
                    rf"(?:[$€£¥₹]\s*)?{number_pattern}\b",
                    line,
                    re.IGNORECASE,
                )
                if match:
                    try:
                        return float(match.group(1).replace(",", ""))
                    except (ValueError, TypeError):
                        pass

        return None

    def _extract_generic_total(
        self,
        text: str,
        number_pattern: str,
    ) -> Optional[float]:
        """Fallback for a plain 'Total' label, excluding 'Line Total'."""

        for line in text.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            lower = clean.lower()

            if "line total" in lower:
                continue

            if not re.search(r"\btotal\b", lower):
                continue

            # Reject table/header rows that contain multiple numbers.
            if re.search(r"\b(?:item|description|qty|quantity|unit price)\b", lower):
                continue

            match = re.search(
                rf"\btotal\b\s*[:\-]?\s*"
                rf"(?:[$€£¥₹]\s*)?{number_pattern}",
                clean,
                re.IGNORECASE,
            )
            if match:
                try:
                    return float(match.group(1).replace(",", ""))
                except (ValueError, TypeError):
                    continue

        return None

    def _extract_po_reference(
        self,
        text: str,
        normalized: str,
    ) -> Optional[str]:
        """Extract a purchase-order reference such as PO-0003 or PO-2024-001."""

        patterns = [
            r"\bPO\s*(?:Reference|Ref(?:erence)?|Number|No\.?)\s*[:#\-]?\s*"
            r"([A-Z0-9][A-Z0-9._/\-]*)",
            r"\bPO\s*[:#\-]\s*([A-Z0-9][A-Z0-9._/\-]*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value.upper()

        # Last-resort: a standalone PO-looking token near a PO label.
        for line in normalized.splitlines():
            if "po" not in line.lower():
                continue
            match = re.search(
                r"\b(PO[-_][A-Z0-9][A-Z0-9._/\-]*)\b",
                line,
                re.IGNORECASE,
            )
            if match:
                return match.group(1).upper()

        return None

    # ========================================================================
    # LINE ITEMS
    # ========================================================================

    def _extract_line_items(
        self,
        text: str,
        source_path: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """
        Robust line-item extraction.

        Strategy:

        1. If PDF exists -> use pdfplumber table extraction.
        2. Parse detected tables.
        3. Fall back to line-based regex parsing.
        4. Deduplicate results.
        """

        items: List[Dict[str, Any]] = []

        # ------------------------------------------------------------
        # 1. PDF TABLE EXTRACTION
        # ------------------------------------------------------------

        if (
            source_path
            and source_path.suffix.lower() == ".pdf"
            and PDFPLUMBER_AVAILABLE
        ):
            try:
                items.extend(
                    self._extract_pdf_tables(
                        source_path
                    )
                )
            except Exception as exc:
                logger.warning(
                    "PDF table extraction failed: %s",
                    exc,
                )

        # ------------------------------------------------------------
        # 2. TEXT FALLBACK
        # ------------------------------------------------------------

        if not items:
            items.extend(
                self._extract_line_items_from_text(
                    text
                )
            )

        # ------------------------------------------------------------
        # 3. CLEAN + DEDUPLICATE
        # ------------------------------------------------------------

        items = self._clean_line_items(items)

        return items

    # ========================================================================
    # PDF TABLE EXTRACTION
    # ========================================================================

    def _extract_pdf_tables(
        self,
        path: Path,
    ) -> List[Dict[str, Any]]:

        results: List[Dict[str, Any]] = []

        with pdfplumber.open(path) as pdf:

            for page_number, page in enumerate(
                pdf.pages,
                start=1,
            ):

                tables = page.extract_tables(
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 5,
                        "snap_tolerance": 4,
                        "join_tolerance": 4,
                    }
                )

                # Some PDFs do not have visible borders.
                if not tables:
                    tables = page.extract_tables(
                        {
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "intersection_tolerance": 5,
                            "snap_tolerance": 4,
                            "join_tolerance": 4,
                        }
                    )

                for table in tables:

                    if not table:
                        continue

                    rows = [
                        [
                            self._clean_cell(cell)
                            for cell in row
                        ]
                        for row in table
                        if row
                    ]

                    if not rows:
                        continue

                    header_index = self._find_header_row(
                        rows
                    )

                    if header_index is not None:
                        headers = rows[header_index]

                        for row in rows[
                            header_index + 1:
                        ]:
                            item = self._row_to_line_item(
                                headers,
                                row,
                            )

                            if item:
                                results.append(item)

                    else:
                        for row in rows:
                            item = self._guess_line_item_from_row(
                                row
                            )

                            if item:
                                results.append(item)

        logger.info(
            "Extracted %d line items from PDF tables",
            len(results),
        )

        return results

    # ========================================================================
    # TABLE HEADER DETECTION
    # ========================================================================

    def _find_header_row(
        self,
        rows: List[List[str]],
    ) -> Optional[int]:

        keywords = {
            "description",
            "item",
            "product",
            "service",
            "qty",
            "quantity",
            "price",
            "unit price",
            "rate",
            "amount",
            "total",
            "unit",
        }

        for index, row in enumerate(rows[:5]):

            joined = " ".join(
                cell.lower()
                for cell in row
                if cell
            )

            score = 0

            for keyword in keywords:
                if keyword in joined:
                    score += 1

            if score >= 2:
                return index

        return None

    # ========================================================================
    # TABLE ROW PARSER
    # ========================================================================

    def _row_to_line_item(
        self,
        headers: List[str],
        row: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Convert a pdfplumber table row into a line item.

        Important: never guess quantity from the first integer blindly.
        When columns are ambiguous, validate the candidate quantity/unit-price/
        line-total relationship using quantity * unit_price ~= line_total.
        """
        if not row or len(row) < 2:
            return None

        # Keep positional alignment with the headers. Do not remove empty cells
        # before reading known columns because doing so shifts column indexes.
        header_map: Dict[str, int] = {}
        for index, header in enumerate(headers):
            normalized = self._normalize_header(header)
            if normalized and normalized not in header_map:
                header_map[normalized] = index

        description = self._get_column(
            row, header_map,
            ["description", "item description", "item", "product", "service"]
        )
        quantity_raw = self._get_column(
            row, header_map, ["quantity", "qty", "units"]
        )
        unit_price_raw = self._get_column(
            row, header_map, ["unit price", "price", "rate", "unit cost"]
        )
        unit = self._get_column(row, header_map, ["unit", "uom"])
        line_total_raw = self._get_column(
            row, header_map,
            ["line total", "extended amount", "extended price", "amount", "total", "extended"]
        )

        quantity = self._parse_number(quantity_raw)
        unit_price = self._parse_number(unit_price_raw)
        line_total = self._parse_number(line_total_raw)

        if not description:
            description = self._first_textual_cell(row)

        # Collect every numeric cell with its original position.
        numeric_cells: List[tuple[int, float]] = []
        for index, cell in enumerate(row):
            value = self._parse_number(cell)
            if value is not None:
                numeric_cells.append((index, value))

        # If one or more columns were not identified, infer them using
        # arithmetic consistency rather than "first integer wins".
        inferred = self._infer_numeric_columns(
            headers=headers,
            row=row,
            numeric_cells=numeric_cells,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )

        if quantity is None:
            quantity = inferred.get("quantity")
        if unit_price is None:
            unit_price = inferred.get("unit_price")
        if line_total is None:
            line_total = inferred.get("line_total")

        if not description or self._is_non_item_text(description):
            return None
        if quantity is None or quantity <= 0:
            return None
        if unit_price is None or unit_price < 0:
            return None

        if line_total is None:
            line_total = quantity * unit_price

        # Final arithmetic guard. This prevents a malformed table row from
        # becoming a false quantity/price discrepancy downstream.
        if not self._amounts_are_consistent(quantity, unit_price, line_total):
            repaired = self._repair_numeric_triplet(
                numeric_cells=numeric_cells,
                quantity=quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
            if repaired:
                quantity, unit_price, line_total = repaired

        if not self._amounts_are_consistent(quantity, unit_price, line_total):
            logger.warning(
                "Skipping inconsistent invoice row: description=%r qty=%r "
                "unit_price=%r line_total=%r",
                description, quantity, unit_price, line_total,
            )
            return None

        return {
            "item_id": self._make_item_id(description),
            "description": description.strip(),
            "quantity": float(quantity),
            "unit_price": float(unit_price),
            "unit": unit.strip() if unit else "unit",
            "line_total": float(line_total),
        }

    def _infer_numeric_columns(
        self,
        headers: List[str],
        row: List[str],
        numeric_cells: List[tuple[int, float]],
        quantity: Optional[float],
        unit_price: Optional[float],
        line_total: Optional[float],
    ) -> Dict[str, Optional[float]]:
        """
        Infer missing numeric columns.

        Preference order:
        1. Header-position evidence.
        2. Arithmetic-consistent candidate triplet.
        3. Conservative fallback.
        """
        result = {
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        }

        values = [value for _, value in numeric_cells]
        if not values:
            return result

        # If exactly two numeric values exist and quantity is known, the other
        # two roles can be recovered safely.
        if result["quantity"] is not None and len(values) >= 2:
            if result["unit_price"] is None and result["line_total"] is None:
                for i in range(len(values)):
                    for j in range(len(values)):
                        if i == j:
                            continue
                        candidate_price = values[i]
                        candidate_total = values[j]
                        if self._amounts_are_consistent(
                            result["quantity"], candidate_price, candidate_total
                        ):
                            result["unit_price"] = candidate_price
                            result["line_total"] = candidate_total
                            return result

        # Search every ordered pair for a valid price/total and an integer-ish
        # quantity. This handles serial numbers, row indexes, and extra numeric
        # columns appearing before the actual Qty column.
        candidates = []
        for q_idx, q in numeric_cells:
            if q <= 0 or q > 100000:
                continue
            for p_idx, price in numeric_cells:
                if p_idx == q_idx or price < 0:
                    continue
                for t_idx, total in numeric_cells:
                    if t_idx in (q_idx, p_idx) or total < 0:
                        continue
                    if self._amounts_are_consistent(q, price, total):
                        integer_bonus = 1.0 if float(q).is_integer() else 0.0
                        positional_bonus = 0.0
                        if q_idx < p_idx <= t_idx:
                            positional_bonus += 1.0
                        candidates.append(
                            (integer_bonus + positional_bonus, q, price, total)
                        )

        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            _, q, price, total = candidates[0]
            if result["quantity"] is None:
                result["quantity"] = q
            if result["unit_price"] is None:
                result["unit_price"] = price
            if result["line_total"] is None:
                result["line_total"] = total

        # Conservative fallback only when arithmetic inference was impossible.
        if result["quantity"] is None:
            result["quantity"] = self._first_reasonable_quantity(values)
        if result["unit_price"] is None and len(values) >= 2:
            result["unit_price"] = values[-2]
        if result["line_total"] is None and values:
            result["line_total"] = values[-1]

        return result

    def _amounts_are_consistent(
        self,
        quantity: Optional[float],
        unit_price: Optional[float],
        line_total: Optional[float],
    ) -> bool:
        if quantity is None or unit_price is None or line_total is None:
            return False
        if quantity <= 0 or unit_price < 0 or line_total < 0:
            return False

        expected = quantity * unit_price
        tolerance = max(0.05, abs(line_total) * 0.001)
        return abs(expected - line_total) <= tolerance

    def _repair_numeric_triplet(
        self,
        numeric_cells: List[tuple[int, float]],
        quantity: Optional[float],
        unit_price: Optional[float],
        line_total: Optional[float],
    ) -> Optional[tuple[float, float, float]]:
        """Find the most plausible arithmetic-consistent numeric triplet."""
        candidates = []

        for q_idx, q in numeric_cells:
            if q <= 0 or q > 100000:
                continue
            for p_idx, price in numeric_cells:
                if p_idx == q_idx or price < 0:
                    continue
                for t_idx, total in numeric_cells:
                    if t_idx in (q_idx, p_idx) or total < 0:
                        continue
                    if not self._amounts_are_consistent(q, price, total):
                        continue

                    score = 0.0
                    if q.is_integer():
                        score += 3.0
                    if q_idx < p_idx < t_idx:
                        score += 2.0

                    # If known values exist, strongly prefer preserving them.
                    if quantity is not None and abs(q - quantity) < 1e-9:
                        score += 5.0
                    if unit_price is not None and abs(price - unit_price) < 1e-9:
                        score += 5.0
                    if line_total is not None and abs(total - line_total) < 1e-9:
                        score += 5.0

                    candidates.append((score, q, price, total))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        _, q, price, total = candidates[0]
        return float(q), float(price), float(total)

    # ========================================================================
    # HEADER NORMALIZATION
    # ========================================================================

    def _normalize_header(
        self,
        value: str,
    ) -> str:

        value = self._clean_cell(value).lower()

        value = re.sub(
            r"[^a-z0-9 ]+",
            " ",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        ).strip()

        aliases = {
            "qty": "quantity",
            "qty.": "quantity",
            "unit cost": "unit price",
            "unit rate": "unit price",
            "rate": "unit price",
            "amount": "amount",
            "extended amount": "line total",
            "extended price": "line total",
        }

        return aliases.get(
            value,
            value,
        )

    # ========================================================================
    # COLUMN HELPER
    # ========================================================================

    def _get_column(
        self,
        row: List[str],
        header_map: Dict[str, int],
        candidates: List[str],
    ) -> Optional[str]:

        for candidate in candidates:
            candidate = candidate.lower()

            if candidate in header_map:
                index = header_map[candidate]

                if index < len(row):
                    value = row[index]

                    if value:
                        return value

        return None

    # ========================================================================
    # TEXT LINE ITEM FALLBACK
    # ========================================================================

    def _extract_line_items_from_text(
        self,
        text: str,
    ) -> List[Dict[str, Any]]:

        items: List[Dict[str, Any]] = []

        lines = [
            re.sub(
                r"\s+",
                " ",
                line,
            ).strip()
            for line in text.splitlines()
        ]

        in_table = False

        for line in lines:

            if not line:
                continue

            lower = line.lower()

            # Detect table start.
            if any(
                phrase in lower
                for phrase in [
                    "description quantity",
                    "item quantity",
                    "product quantity",
                    "description qty",
                    "item qty",
                    "qty price",
                    "quantity unit price",
                ]
            ):
                in_table = True
                continue

            if self._is_table_header(line):
                in_table = True
                continue

            # Stop around totals.
            if in_table and re.match(
                r"^(subtotal|tax|vat|gst|grand total|total|amount due|balance due)\b",
                lower,
            ):
                continue

            item = self._parse_line_item(line)

            if item:
                items.append(item)

        # If table wasn't explicitly detected,
        # try every line anyway.
        if not items:
            for line in lines:
                item = self._parse_line_item(line)

                if item:
                    items.append(item)

        return items

    # ========================================================================
    # TABLE HEADER CHECK
    # ========================================================================

    def _is_table_header(
        self,
        line: str,
    ) -> bool:

        lower = line.lower()

        keywords = [
            "description",
            "item",
            "product",
            "quantity",
            "qty",
            "unit price",
            "price",
            "amount",
            "total",
        ]

        return sum(
            keyword in lower
            for keyword in keywords
        ) >= 2

    # ========================================================================
    # TEXT LINE PARSER
    # ========================================================================

    def _parse_line_item(
        self,
        line: str,
    ) -> Optional[Dict[str, Any]]:

        if len(line) < 5:
            return None

        if self._is_non_item_text(line):
            return None

        # Format:
        # Description 2 100.00 200.00
        pattern = re.compile(
            r"^(.+?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(?:[$€£¥₹]\s*)?"
            r"(\d[\d,]*(?:\.\d{1,2})?)\s+"
            r"(?:[$€£¥₹]\s*)?"
            r"(\d[\d,]*(?:\.\d{1,2})?)"
            r"\s*$"
        )

        match = pattern.match(line)

        if match:
            description = match.group(1).strip()

            quantity = self._parse_number(
                match.group(2)
            )

            unit_price = self._parse_number(
                match.group(3)
            )

            line_total = self._parse_number(
                match.group(4)
            )

            if (
                description
                and quantity is not None
                and unit_price is not None
            ):
                return {
                    "item_id": self._make_item_id(
                        description
                    ),
                    "description": description,
                    "quantity": float(quantity),
                    "unit_price": float(unit_price),
                    "unit": "unit",
                    "line_total": float(
                        line_total
                        if line_total is not None
                        else quantity * unit_price
                    ),
                }

        # Alternative:
        # 1 Laptop Stand 2 50.00 100.00
        pattern = re.compile(
            r"^(\d+)\s+"
            r"(.+?)\s+"
            r"(\d+(?:\.\d+)?)\s+"
            r"(?:[$€£¥₹]\s*)?"
            r"(\d[\d,]*(?:\.\d{1,2})?)\s+"
            r"(?:[$€£¥₹]\s*)?"
            r"(\d[\d,]*(?:\.\d{1,2})?)"
            r"\s*$"
        )

        match = pattern.match(line)

        if match:
            description = match.group(2).strip()

            quantity = self._parse_number(
                match.group(3)
            )

            unit_price = self._parse_number(
                match.group(4)
            )

            line_total = self._parse_number(
                match.group(5)
            )

            if (
                description
                and quantity is not None
                and unit_price is not None
            ):
                return {
                    "item_id": self._make_item_id(
                        description
                    ),
                    "description": description,
                    "quantity": float(quantity),
                    "unit_price": float(unit_price),
                    "unit": "unit",
                    "line_total": float(
                        line_total
                        if line_total is not None
                        else quantity * unit_price
                    ),
                }

        return None

    # ========================================================================
    # GENERIC ROW GUESSING
    # ========================================================================

    def _guess_line_item_from_row(
        self,
        row: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Conservative table-row fallback with arithmetic validation."""
        cleaned = [self._clean_cell(cell) for cell in row]
        if len(cleaned) < 3:
            return None

        description = self._first_textual_cell(cleaned)
        if not description or self._is_non_item_text(description):
            return None

        numeric_cells = []
        for index, cell in enumerate(cleaned):
            value = self._parse_number(cell)
            if value is not None:
                numeric_cells.append((index, value))

        if len(numeric_cells) < 2:
            return None

        inferred = self._infer_numeric_columns(
            headers=[],
            row=cleaned,
            numeric_cells=numeric_cells,
            quantity=None,
            unit_price=None,
            line_total=None,
        )

        quantity = inferred.get("quantity")
        unit_price = inferred.get("unit_price")
        line_total = inferred.get("line_total")

        if quantity is None or unit_price is None:
            return None

        if line_total is None:
            line_total = quantity * unit_price

        if not self._amounts_are_consistent(quantity, unit_price, line_total):
            return None

        return {
            "item_id": self._make_item_id(description),
            "description": description,
            "quantity": float(quantity),
            "unit_price": float(unit_price),
            "unit": "unit",
            "line_total": float(line_total),
        }

    # ========================================================================
    # LINE ITEM CLEANING
    # ========================================================================

    def _clean_line_items(
        self,
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        cleaned: List[Dict[str, Any]] = []
        seen = set()

        for item in items:

            description = str(
                item.get(
                    "description",
                    "",
                )
            ).strip()

            if not description:
                continue

            quantity = self._safe_float(
                item.get("quantity")
            )

            unit_price = self._safe_float(
                item.get("unit_price")
            )

            line_total = self._safe_float(
                item.get("line_total")
            )

            if quantity is None or quantity <= 0:
                continue

            if unit_price is None or unit_price < 0:
                continue

            if line_total is None:
                line_total = quantity * unit_price

            item_id = (
                item.get("item_id")
                or self._make_item_id(description)
            )

            dedupe_key = (
                self._normalize_item_text(
                    description
                ),
                round(quantity, 6),
                round(unit_price, 6),
            )

            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)

            cleaned.append(
                {
                    "item_id": str(item_id),
                    "description": description,
                    "quantity": float(quantity),
                    "unit_price": float(unit_price),
                    "unit": str(
                        item.get(
                            "unit",
                            "unit",
                        )
                    ).strip()
                    or "unit",
                    "line_total": float(line_total),
                }
            )

        return cleaned

    # ========================================================================
    # HELPERS
    # ========================================================================

    def _clean_cell(
        self,
        value: Any,
    ) -> str:

        if value is None:
            return ""

        value = str(value)

        value = value.replace(
            "\n",
            " ",
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value.strip()

    def _parse_number(
        self,
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        value = str(value).strip()

        if not value:
            return None

        # Remove currency symbols.
        value = re.sub(
            r"[$€£¥₹]",
            "",
            value,
        )

        # Remove commas.
        value = value.replace(
            ",",
            "",
        )

        # Keep only number characters.
        match = re.search(
            r"-?\d+(?:\.\d+)?",
            value,
        )

        if not match:
            return None

        try:
            return float(
                match.group(0)
            )
        except ValueError:
            return None

    def _safe_float(
        self,
        value: Any,
    ) -> Optional[float]:

        try:
            if value is None:
                return None

            return float(value)

        except (
            ValueError,
            TypeError,
        ):
            return None

    def _first_textual_cell(
        self,
        row: List[str],
    ) -> Optional[str]:

        for cell in row:
            if not cell:
                continue

            if self._parse_number(cell) is not None:
                # Don't treat pure numeric cells as descriptions.
                if re.fullmatch(
                    r"[\s$€£¥₹,\d.]+",
                    cell,
                ):
                    continue

            if re.search(
                r"[A-Za-z]",
                cell,
            ):
                return cell.strip()

        return None

    def _first_reasonable_quantity(
        self,
        values: List[float],
    ) -> Optional[float]:

        for value in values:
            if (
                value > 0
                and value <= 100000
                and value.is_integer()
            ):
                return value

        for value in values:
            if 0 < value <= 100000:
                return value

        return None

    def _is_non_item_text(
        self,
        text: str,
    ) -> bool:

        lower = text.lower().strip()

        blocked = [
            "description",
            "quantity",
            "qty",
            "unit price",
            "price",
            "amount",
            "subtotal",
            "sub total",
            "tax",
            "vat",
            "gst",
            "total",
            "grand total",
            "amount due",
            "balance due",
            "invoice",
            "payment terms",
            "notes",
            "thank you",
        ]

        return any(
            lower == value
            or lower.startswith(value + " ")
            for value in blocked
        )

    def _make_item_id(
        self,
        description: str,
    ) -> str:

        normalized = self._normalize_item_text(
            description
        )

        return normalized[:100]

    def _normalize_item_text(
        self,
        text: str,
    ) -> str:

        text = str(text).lower()

        text = re.sub(
            r"[^a-z0-9]+",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    # ========================================================================
    # PAYMENT TERMS
    # ========================================================================

    def _extract_payment_terms(
        self,
        text: str,
        normalized: str,
    ) -> Optional[str]:

        patterns = [
            r"\bnet\s+\d+\b",
            r"\bdue\s+upon\s+receipt\b",
            r"\bcash\s+on\s+delivery\b",
            r"\bpayment\s+terms?\s*[:\-]?\s*([A-Za-z0-9 ,\-]+)",
            r"\bterms?\s*[:\-]?\s*([A-Za-z0-9 ,\-]+)",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                normalized,
                re.IGNORECASE,
            )

            if match:
                return match.group(0).strip()

        return None

    # ========================================================================
    # CONFIDENCE
    # ========================================================================

    def _calculate_confidence(
        self,
        invoice: InvoiceData,
        raw_text: str,
        extraction_method: ExtractionMethod,
        extraction_quality: float,
    ) -> float:

        if extraction_method == ExtractionMethod.NATIVE_PDF:
            base_confidence = 0.90
        elif extraction_method == ExtractionMethod.OCR:
            base_confidence = 0.65
        else:
            return 0.0

        fields = {
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "vendor_name": invoice.vendor_name,
            "total": invoice.total,
            "subtotal": invoice.subtotal,
            "tax": invoice.tax,
            "customer_name": invoice.customer_name,
            "due_date": invoice.due_date,
            "payment_terms": invoice.payment_terms,
        }

        important_weights = {
            "invoice_number": 0.20,
            "invoice_date": 0.10,
            "vendor_name": 0.20,
            "total": 0.20,
            "subtotal": 0.05,
            "tax": 0.05,
            "customer_name": 0.05,
            "due_date": 0.05,
            "payment_terms": 0.02,
        }

        field_score = 0.0

        for field, weight in important_weights.items():
            if fields.get(field) is not None:
                field_score += weight

        # Line items are extremely important for reconciliation.
        line_score = 0.0

        if invoice.line_items:
            line_score = 0.13

        consistency_bonus = 0.0

        if (
            invoice.subtotal is not None
            and invoice.tax is not None
            and invoice.total is not None
        ):
            calculated = (
                invoice.subtotal
                + invoice.tax
            )

            if abs(
                calculated - invoice.total
            ) <= 0.05:
                consistency_bonus = 0.07

        confidence = (
            base_confidence * 0.45
            + field_score * 0.35
            + line_score
            + consistency_bonus
        )

        # Blend extraction quality.
        confidence = (
            confidence * 0.80
            + extraction_quality * 0.20
        )

        # Critical missing fields penalty.
        critical_missing = 0

        if not invoice.invoice_number:
            critical_missing += 1

        if not invoice.vendor_name:
            critical_missing += 1

        if invoice.total is None:
            critical_missing += 1

        if critical_missing:
            confidence *= (
                1.0
                - 0.15 * critical_missing
            )

        # No line items should reduce confidence.
        if not invoice.line_items:
            confidence *= 0.80

        return max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

    # ========================================================================
    # EXPLANATION
    # ========================================================================

    def _generate_explanation(
        self,
        invoice: InvoiceData,
        extraction_method: ExtractionMethod,
        confidence: float,
    ) -> str:

        parts: List[str] = []

        if extraction_method == ExtractionMethod.NATIVE_PDF:
            parts.append(
                "Text extracted using native PDF parsing."
            )
        elif extraction_method == ExtractionMethod.OCR:
            parts.append(
                "Text extracted using OCR "
                "(Optical Character Recognition)."
            )
        else:
            parts.append(
                "Text extraction failed."
            )

        extracted_fields: List[str] = []

        if invoice.invoice_number:
            extracted_fields.append(
                "invoice number"
            )

        if invoice.invoice_date:
            extracted_fields.append(
                "invoice date"
            )

        if invoice.po_reference:
            extracted_fields.append(
                "PO reference"
            )

        if invoice.vendor_name:
            extracted_fields.append(
                "vendor name"
            )

        if invoice.total is not None:
            extracted_fields.append(
                "total amount"
            )

        if invoice.customer_name:
            extracted_fields.append(
                "customer name"
            )

        if invoice.line_items:
            extracted_fields.append(
                f"{len(invoice.line_items)} line items"
            )

        if extracted_fields:
            parts.append(
                "Successfully extracted: "
                + ", ".join(extracted_fields)
                + "."
            )
        else:
            parts.append(
                "No structured data could be extracted."
            )

        missing: List[str] = []

        if not invoice.invoice_number:
            missing.append("invoice number")

        if not invoice.vendor_name:
            missing.append("vendor name")

        if invoice.total is None:
            missing.append("total amount")

        if not invoice.line_items:
            missing.append("line items")

        if missing:
            parts.append(
                "Missing important fields: "
                + ", ".join(missing)
                + "."
            )

        if confidence >= 0.85:
            parts.append(
                "High confidence in extraction quality."
            )
        elif confidence >= 0.65:
            parts.append(
                "Moderate confidence - "
                "some fields may require verification."
            )
        elif confidence >= 0.45:
            parts.append(
                "Low confidence - "
                "manual review recommended."
            )
        else:
            parts.append(
                "Very low confidence - "
                "extraction may be unreliable."
            )

        return " ".join(parts)

    # ========================================================================
    # OUTPUT
    # ========================================================================

    def _prepare_output_data(
        self,
        invoice: InvoiceData,
        raw_text: str,
    ) -> Dict[str, Any]:

        return {
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.invoice_date,
            "due_date": invoice.due_date,
            "po_reference": invoice.po_reference,

            "vendor": {
                "name": invoice.vendor_name,
                "address": invoice.vendor_address,
            },

            "customer": {
                "name": invoice.customer_name,
                "address": invoice.customer_address,
            },

            "amounts": {
                "subtotal": invoice.subtotal,
                "tax": invoice.tax,
                "total": invoice.total,
                "currency": invoice.currency,
            },

            "line_items": invoice.line_items,

            "payment_terms": invoice.payment_terms,

            "raw_text_preview": (
                raw_text[:1000]
                if raw_text
                else None
            ),
        }

    # ========================================================================
    # ERROR OUTPUT
    # ========================================================================

    def _create_error_output(
        self,
        error_message: str,
        confidence: float = 0.0,
    ) -> AgentOutput:

        return AgentOutput(
            data={
                "error": error_message
            },
            confidence=confidence,
            explanation=(
                "Document processing failed: "
                f"{error_message}"
            ),
            metadata={
                "error": True
            },
        )