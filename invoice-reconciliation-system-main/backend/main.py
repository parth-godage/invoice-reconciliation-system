from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from pathlib import Path
from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any, get_args, get_origin, get_type_hints
import json

from graph.orchestration import run_reconciliation
from models import PurchaseOrder


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="AI Invoice Reconciliation API",
    description=(
        "FastAPI backend for the LangGraph "
        "Invoice Reconciliation System"
    ),
    version="1.0.0",
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"

INVOICE_DIR = DATA_DIR / "invoices"

PURCHASE_ORDER_FILE = DATA_DIR / "purchase_orders.json"


# ============================================================
# BASIC ROUTES
# ============================================================

@app.get("/")
def root():
    return {
        "message": "AI Invoice Reconciliation API is running",
        "status": "online",
        "version": "1.0.0",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "invoice-reconciliation-api",
    }


# ============================================================
# DATE HELPERS
# ============================================================

def parse_datetime(value: Any):
    """
    Convert common date strings into datetime objects.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):

        value = value.strip()

        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
        ]

        for fmt in formats:

            try:
                return datetime.strptime(
                    value,
                    fmt,
                )
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            pass

    return value


# ============================================================
# GENERIC DATACLASS CONVERSION
# ============================================================

def build_dataclass_from_dict(
    cls,
    data: dict,
):
    """
    Build a dataclass from a dictionary while using
    the dataclass's actual field names and type hints.

    This makes the adapter tolerant of nested dataclasses,
    lists and datetime fields.
    """

    if not is_dataclass(cls):
        return data

    try:
        type_hints = get_type_hints(cls)
    except Exception:
        type_hints = {}

    allowed_fields = {
        field.name
        for field in fields(cls)
    }

    result = {}

    for field_name in allowed_fields:

        if field_name not in data:
            continue

        value = data[field_name]

        field_type = type_hints.get(
            field_name
        )

        result[field_name] = convert_to_type(
            value,
            field_type,
        )

    return cls(**result)


def convert_to_type(
    value,
    target_type,
):
    """
    Recursively convert JSON data to the target
    Python/dataclass type where possible.
    """

    if value is None:
        return None

    if target_type is None:
        return convert_generic(value)

    origin = get_origin(target_type)

    args = get_args(target_type)

    # --------------------------------------------------------
    # List / list[T]
    # --------------------------------------------------------

    if origin is list:

        item_type = (
            args[0]
            if args
            else None
        )

        if isinstance(value, list):

            return [
                convert_to_type(
                    item,
                    item_type,
                )
                for item in value
            ]

        return value

    # --------------------------------------------------------
    # Dict / dict[K, V]
    # --------------------------------------------------------

    if origin is dict:

        if isinstance(value, dict):

            return {
                key: convert_generic(item)
                for key, item in value.items()
            }

        return value

    # --------------------------------------------------------
    # Dataclass
    # --------------------------------------------------------

    try:

        if is_dataclass(target_type):

            if isinstance(value, dict):

                return build_dataclass_from_dict(
                    target_type,
                    value,
                )

    except TypeError:
        pass

    # --------------------------------------------------------
    # datetime
    # --------------------------------------------------------

    if target_type is datetime:

        return parse_datetime(value)

    # --------------------------------------------------------
    # Primitive types
    # --------------------------------------------------------

    try:

        if target_type is float:
            return float(value)

        if target_type is int:
            return int(value)

        if target_type is str:
            return str(value)

        if target_type is bool:
            return bool(value)

    except (TypeError, ValueError):
        return value

    return convert_generic(value)


def convert_generic(value):
    """
    Generic recursive conversion when no exact type
    information is available.
    """

    if isinstance(value, dict):

        return {
            key: convert_generic(item)
            for key, item in value.items()
        }

    if isinstance(value, list):

        return [
            convert_generic(item)
            for item in value
        ]

    if isinstance(value, str):

        parsed = parse_datetime(value)

        return parsed

    return value


# ============================================================
# PURCHASE ORDER FIELD MAPPING
# ============================================================

def normalize_purchase_order(
    data: dict,
):
    """
    Convert the JSON schema into the application's
    PurchaseOrder schema.

    Actual JSON:

        po_number
        supplier
        date
        total
        currency
        line_items

    Application model:

        po_number
        vendor_name
        po_date
        total_amount
        ...
    """

    if not isinstance(data, dict):

        raise ValueError(
            "Purchase order must be a JSON object."
        )

    normalized = dict(data)

    # --------------------------------------------------------
    # Field mapping
    # --------------------------------------------------------

    normalized["po_number"] = (
        data.get("po_number")
        or data.get("purchase_order_number")
        or data.get("number")
    )

    normalized["vendor_name"] = (
        data.get("vendor_name")
        or data.get("supplier")
        or data.get("vendor")
    )

    normalized["po_date"] = (
        data.get("po_date")
        or data.get("date")
    )

    normalized["total_amount"] = (
        data.get("total_amount")
        if data.get("total_amount") is not None
        else data.get("total")
    )

    # --------------------------------------------------------
    # Validate required fields
    # --------------------------------------------------------

    missing = []

    if not normalized["po_number"]:
        missing.append("po_number")

    if not normalized["vendor_name"]:
        missing.append("vendor_name/supplier")

    if normalized["po_date"] is None:
        missing.append("po_date/date")

    if normalized["total_amount"] is None:
        missing.append("total_amount/total")

    if missing:

        raise ValueError(
            "Purchase order is missing required fields: "
            + ", ".join(missing)
        )

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    normalized["po_date"] = parse_datetime(
        normalized["po_date"]
    )

    # --------------------------------------------------------
    # Amount
    # --------------------------------------------------------

    normalized["total_amount"] = float(
        normalized["total_amount"]
    )

    return normalized


# ============================================================
# CREATE PURCHASE ORDER
# ============================================================

def create_purchase_order(
    data: dict,
):
    """
    Create the project's existing PurchaseOrder object
    from purchase_orders.json.
    """

    if not is_dataclass(PurchaseOrder):

        raise RuntimeError(
            "models.PurchaseOrder must be a dataclass."
        )

    normalized = normalize_purchase_order(
        data
    )

    # --------------------------------------------------------
    # Use the actual model's fields
    # --------------------------------------------------------

    allowed_fields = {
        field.name
        for field in fields(PurchaseOrder)
    }

    # --------------------------------------------------------
    # Resolve actual model type hints
    # --------------------------------------------------------

    try:
        type_hints = get_type_hints(
            PurchaseOrder
        )
    except Exception:
        type_hints = {}

    model_data = {}

    for field_name in allowed_fields:

        if field_name not in normalized:
            continue

        value = normalized[field_name]

        target_type = type_hints.get(
            field_name
        )

        model_data[field_name] = convert_to_type(
            value,
            target_type,
        )

    # --------------------------------------------------------
    # Safety fallback for required fields
    # --------------------------------------------------------

    required_mapping = {
        "po_number": normalized["po_number"],
        "vendor_name": normalized["vendor_name"],
        "po_date": normalized["po_date"],
        "total_amount": normalized["total_amount"],
    }

    for field_name, value in required_mapping.items():

        if (
            field_name in allowed_fields
            and field_name not in model_data
        ):
            model_data[field_name] = value

    # --------------------------------------------------------
    # Create PurchaseOrder
    # --------------------------------------------------------

    try:

        return PurchaseOrder(
            **model_data
        )

    except TypeError as exc:

        raise RuntimeError(
            "Unable to create PurchaseOrder "
            f"for {normalized['po_number']}: {exc}"
        ) from exc


# ============================================================
# LOAD PURCHASE ORDERS
# ============================================================

def load_purchase_orders():
    """
    Load purchase orders from:

        data/purchase_orders.json

    Expected structure:

        {
            "purchase_orders": [
                {...},
                {...}
            ]
        }
    """

    # --------------------------------------------------------
    # File exists?
    # --------------------------------------------------------

    if not PURCHASE_ORDER_FILE.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Purchase-order file not found: "
                f"{PURCHASE_ORDER_FILE}"
            ),
        )

    if not PURCHASE_ORDER_FILE.is_file():

        raise HTTPException(
            status_code=400,
            detail=(
                "Purchase-order path is not a file: "
                f"{PURCHASE_ORDER_FILE}"
            ),
        )

    # --------------------------------------------------------
    # Read JSON
    # --------------------------------------------------------

    try:

        with open(
            PURCHASE_ORDER_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

    except json.JSONDecodeError as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Invalid JSON in purchase_orders.json: "
                f"{exc}"
            ),
        )

    except OSError as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to read purchase_orders.json: "
                f"{exc}"
            ),
        )

    # --------------------------------------------------------
    # Extract PO records
    # --------------------------------------------------------

    if isinstance(data, dict):

        records = data.get(
            "purchase_orders"
        )

        if records is None:

            records = [data]

    elif isinstance(data, list):

        records = data

    else:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unsupported structure in "
                "purchase_orders.json."
            ),
        )

    if not isinstance(records, list):

        raise HTTPException(
            status_code=500,
            detail=(
                "'purchase_orders' must be a list."
            ),
        )

    if not records:

        raise HTTPException(
            status_code=404,
            detail=(
                "purchase_orders.json contains "
                "no purchase orders."
            ),
        )

    # --------------------------------------------------------
    # Convert all POs
    # --------------------------------------------------------

    purchase_orders = []

    for index, record in enumerate(
        records,
        start=1,
    ):

        if not isinstance(record, dict):

            raise HTTPException(
                status_code=500,
                detail=(
                    f"Purchase order #{index} "
                    "is not a JSON object."
                ),
            )

        try:

            purchase_order = (
                create_purchase_order(
                    record
                )
            )

            purchase_orders.append(
                purchase_order
            )

        except Exception as exc:

            po_number = record.get(
                "po_number",
                f"#{index}",
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    f"Failed converting purchase "
                    f"order {po_number}: {exc}"
                ),
            ) from exc

    return purchase_orders


# ============================================================
# DATA STATUS
# ============================================================

@app.get("/data-status")
def data_status():
    """
    Return project data information.
    """

    # --------------------------------------------------------
    # Invoices
    # --------------------------------------------------------

    invoice_files = []

    if INVOICE_DIR.exists():

        invoice_files = [
            file.name
            for file in sorted(
                INVOICE_DIR.iterdir()
            )
            if (
                file.is_file()
                and file.suffix.lower()
                in [
                    ".pdf",
                    ".png",
                    ".jpg",
                    ".jpeg",
                ]
            )
        ]

    # --------------------------------------------------------
    # Purchase orders
    # --------------------------------------------------------

    purchase_order_exists = (
        PURCHASE_ORDER_FILE.exists()
        and PURCHASE_ORDER_FILE.is_file()
    )

    purchase_order_count = 0

    if purchase_order_exists:

        try:

            purchase_orders = (
                load_purchase_orders()
            )

            purchase_order_count = len(
                purchase_orders
            )

        except Exception:

            purchase_order_count = 0

    return {
        "project_root": str(
            PROJECT_ROOT
        ),

        "data_directory": str(
            DATA_DIR
        ),

        "invoice_directory": str(
            INVOICE_DIR
        ),

        "purchase_order_file": str(
            PURCHASE_ORDER_FILE
        ),

        "invoice_count": len(
            invoice_files
        ),

        "purchase_order_count": (
            purchase_order_count
        ),

        "purchase_order_file_exists": (
            purchase_order_exists
        ),

        "invoices": invoice_files,

        "purchase_orders": (
            [PURCHASE_ORDER_FILE.name]
            if purchase_order_exists
            else []
        ),
    }


# ============================================================
# LIST INVOICES
# ============================================================

@app.get("/invoices")
def list_invoices():
    """
    Return all invoices from data/invoices.
    """

    if not INVOICE_DIR.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                "Invoice directory not found: "
                f"{INVOICE_DIR}"
            ),
        )

    invoices = []

    for file in sorted(
        INVOICE_DIR.iterdir()
    ):

        if not file.is_file():
            continue

        if file.suffix.lower() not in [
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
        ]:
            continue

        invoices.append(
            {
                "filename": file.name,
                "path": str(file),
                "extension": file.suffix.lower(),
            }
        )

    return {
        "count": len(invoices),
        "invoices": invoices,
    }


# ============================================================
# RECONCILIATION
# ============================================================

@app.post("/reconcile")
def reconcile_existing_invoice(
    invoice_filename: str,
):
    """
    Run the existing invoice through the
    LangGraph reconciliation workflow.
    """

    if not invoice_filename:

        raise HTTPException(
            status_code=400,
            detail=(
                "invoice_filename is required."
            ),
        )

    # --------------------------------------------------------
    # Security: filename only
    # --------------------------------------------------------

    invoice_name = Path(
        invoice_filename
    ).name

    if invoice_name != invoice_filename:

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid invoice filename."
            ),
        )

    invoice_path = (
        INVOICE_DIR / invoice_name
    )

    # --------------------------------------------------------
    # Check invoice
    # --------------------------------------------------------

    if not invoice_path.exists():

        raise HTTPException(
            status_code=404,
            detail=(
                f"Invoice not found: "
                f"{invoice_filename}"
            ),
        )

    if not invoice_path.is_file():

        raise HTTPException(
            status_code=400,
            detail=(
                "Selected invoice is not a file."
            ),
        )

    # --------------------------------------------------------
    # Load POs
    # --------------------------------------------------------

    purchase_orders = (
        load_purchase_orders()
    )

    # --------------------------------------------------------
    # Run LangGraph
    # --------------------------------------------------------

    try:

        result = run_reconciliation(
            document_path=str(
                invoice_path
            ),
            purchase_orders=purchase_orders,
            checkpoint_memory=True,
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Reconciliation failed: "
                f"{exc}"
            ),
        ) from exc

    # --------------------------------------------------------
    # Return structured response
    # --------------------------------------------------------

    return {
        "success": True,

        "invoice": invoice_filename,

        "purchase_order_count": len(
            purchase_orders
        ),

        "current_step": result.get(
            "current_step"
        ),

        "execution_trace": result.get(
            "execution_trace",
            [],
        ),

        "errors": result.get(
            "errors",
            [],
        ),

        "document_result": result.get(
            "document_result"
        ),

        "extracted_invoice": result.get(
            "extracted_invoice"
        ),

        "matching_result": result.get(
            "matching_result"
        ),

        "discrepancy_result": result.get(
            "discrepancy_result"
        ),

        "resolution_recommendation": result.get(
            "resolution_recommendation"
        ),
    }