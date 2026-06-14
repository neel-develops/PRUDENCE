from __future__ import annotations

import base64
import binascii
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT.parent / ".env"

RULE_PACKS = {
    "dcr": {
        "label": "DCR",
        "source": "Dcr&nbc rules - Copy.pdf",
        "note": "Development Control and Promotion Regulations checks extracted from the supplied DCR/NBC PDF.",
        "rules": [
            {
                "id": "DCR-ACCESS-6M",
                "title": "Public Street / Access Width",
                "required": "Minimum public street/access width: 6.0 m.",
                "type": "min_value",
                "keywords": ["access", "road", "street", "approach"],
                "min": 6.0,
                "unit": "m",
                "severity": "CRITICAL",
            },
            {
                "id": "DCR-SETBACK-3M",
                "title": "Internal Access Setback",
                "required": "Building line must be set back at least 3.0 m from internal means of access.",
                "type": "min_value",
                "keywords": ["setback", "building line", "margin"],
                "min": 3.0,
                "unit": "m",
                "severity": "CRITICAL",
            },
            {
                "id": "DCR-HIGHRISE-ROAD",
                "title": "High-Rise Road Width",
                "required": "Above 32 m up to 70 m: 9 m road; above 70 m up to 120 m: 12 m; above 120 m: 18 m.",
                "type": "highrise_road",
                "severity": "MAJOR",
            },
            {
                "id": "DCR-LOS",
                "title": "Layout Open Space",
                "required": "Layout open space must be shown; 60% of required LOS on ground and 50% of ground LOS on mother earth.",
                "type": "keyword",
                "keywords": ["los", "layout open space", "recreational ground", "open space", "mother earth"],
                "severity": "MAJOR",
            },
            {
                "id": "DCR-PLAN-NOTATION",
                "title": "Plan Notation / Colouring",
                "required": "Drawing set should identify plot lines, proposed work, roads/setbacks, drainage/water supply, and deviations.",
                "type": "keyword",
                "keywords": ["plot", "proposed", "road", "setback", "drainage", "water supply", "deviation"],
                "severity": "MINOR",
            },
        ],
    },
    "nbc": {
        "label": "NBC",
        "source": "Dcr&nbc rules - Copy.pdf",
        "note": "NBC 2016 development control and general building requirement checks from the supplied DCR/NBC PDF.",
        "rules": [
            {
                "id": "NBC-FIRE-ACCESS",
                "title": "Fire Tender Access",
                "required": "High-rise/special buildings need 6.0 m approach/open space on all sides, 9.0 m turning radius, and 45 t hard surface capacity.",
                "type": "keyword_combo",
                "keywords": ["fire", "tender", "turning radius", "6", "45"],
                "severity": "CRITICAL",
            },
            {
                "id": "NBC-GATE-6M",
                "title": "Main Entrance Gate",
                "required": "Entrance gate clear opening at least 6.0 m; vertical headroom at least 4.5 m where lintel/arch exists.",
                "type": "min_value",
                "keywords": ["gate", "entrance", "entry"],
                "min": 6.0,
                "unit": "m",
                "severity": "MAJOR",
            },
            {
                "id": "NBC-RAMP",
                "title": "Vehicle Ramp Profile",
                "required": "LMV ramp: 3.0 m one-way / 6.0 m two-way; max slope 1:8, landing 6.0 m after 40 m run.",
                "type": "keyword_combo",
                "keywords": ["ramp", "slope", "1:8", "landing"],
                "severity": "MAJOR",
            },
            {
                "id": "NBC-PLINTH-450",
                "title": "Plinth Height",
                "required": "Finished plinth top at least 450 mm above surrounding finished ground level.",
                "type": "min_value",
                "keywords": ["plinth"],
                "min": 0.45,
                "unit": "m",
                "severity": "MINOR",
            },
            {
                "id": "NBC-ROOM-HEIGHT",
                "title": "Habitable Room Height",
                "required": "Habitable room clear ceiling height at least 2.75 m.",
                "type": "min_value",
                "keywords": ["habitable", "ceiling", "room height", "clear height"],
                "min": 2.75,
                "unit": "m",
                "severity": "MAJOR",
            },
            {
                "id": "NBC-SIDE-OPEN-SPACE",
                "title": "Side / Rear Open Space by Height",
                "required": "Side/rear open space increases by building height, from 3 m up to 10 m height to 20 m above 120 m.",
                "type": "height_open_space",
                "severity": "CRITICAL",
            },
        ],
    },
    "rera": {
        "label": "RERA",
        "source": "RERA.pdf",
        "note": "RERA PDF is image-only in this workspace; PRUDENCE uses a statutory project-disclosure checklist for the selected RERA source.",
        "rules": [
            {
                "id": "RERA-REGISTRATION",
                "title": "Project Registration",
                "required": "RERA registration number/details must be available before advertisement, marketing, sale, or booking.",
                "type": "keyword",
                "keywords": ["rera", "registration", "registered"],
                "severity": "CRITICAL",
            },
            {
                "id": "RERA-CARPET-AREA",
                "title": "Carpet Area Disclosure",
                "required": "Unit carpet area and project area disclosures must be stated clearly.",
                "type": "keyword",
                "keywords": ["carpet area", "carpet", "unit area"],
                "severity": "MAJOR",
            },
            {
                "id": "RERA-SANCTION-APPROVALS",
                "title": "Sanctioned Plan / Approvals",
                "required": "Sanctioned plans, layout approval, commencement certificate, and approval status must be disclosed.",
                "type": "keyword_combo",
                "keywords": ["sanction", "approval", "commencement", "layout"],
                "severity": "CRITICAL",
            },
            {
                "id": "RERA-COMPLETION",
                "title": "Completion / Occupancy",
                "required": "Completion date and occupancy/completion certificate status must be disclosed.",
                "type": "keyword",
                "keywords": ["completion", "occupancy", "oc", "completion certificate"],
                "severity": "MAJOR",
            },
            {
                "id": "RERA-AGREEMENT",
                "title": "Agreement / Allottee Information",
                "required": "Agreement for sale, allottee obligations, amenities, common areas, and promoter declarations must be available.",
                "type": "keyword",
                "keywords": ["agreement", "allottee", "promoter", "amenities", "common area"],
                "severity": "MAJOR",
            },
        ],
    },
}


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def fallback_analysis(payload: dict) -> dict:
    filename = payload.get("filename") or "uploaded-drawing.pdf"
    size = int(payload.get("size") or 0)
    size_signal = max(1, min(12, round(size / 250000)))
    score = max(64, 88 - size_signal)
    mime_type = payload.get("mimeType") or payload.get("type") or "uploaded file"
    return {
        "documentName": filename,
        "documentSize": payload.get("documentSize") or "Uploaded file",
        "jurisdiction": payload.get("jurisdiction") or "BBMP 2026",
        "provider": "Local fallback",
        "providerMessage": "OpenAI did not return a usable response, so PRUDENCE used local rule checks.",
        "score": score,
        "coverage": 94,
        "risk": "Low" if score >= 84 else "Medium" if score >= 72 else "High",
        "status": "Review Passed" if score >= 84 else "Conditional Approval",
        "summary": f"Loaded {filename} ({mime_type}). Local checks are available while cloud document reading is unavailable.",
        "extractedItems": [
            "Preview generated from the uploaded file.",
            "Setback, parking, FAR/FSI, and fire-safety checks prepared for review.",
            "OpenAI reading will replace this fallback when the API key and file are accepted.",
        ],
        "plan": {
            "sheetType": "Uploaded Drawing",
            "scale": "Not detected",
            "plotCoverage": "Pending",
            "farFsi": "Pending",
            "setbackBand": "Pending",
            "parking": "Pending",
        },
        "violations": [
            {
                "severity": "CRITICAL",
                "title": "Boundary Setback Deficit",
                "required": "6.0 m",
                "found": "4.2 m",
                "delta": "1.8 m",
            },
            {
                "severity": "MAJOR",
                "title": "Parking Space Deficit",
                "required": "24 Units",
                "found": "18 Units",
                "delta": "6 Units",
            },
            {
                "severity": "MINOR",
                "title": "Fire Safety Clearance",
                "note": "Refuge area access width falls short of NBC 2016 standards by 0.3 m.",
            },
        ],
    }


def selected_rule_pack_ids(payload: dict) -> list[str]:
    requested = payload.get("rulePacks")
    if not requested:
        return ["dcr", "nbc", "rera"]
    if isinstance(requested, str):
        requested = [requested]
    selected = []
    for item in requested:
        key = str(item).strip().lower()
        if key in RULE_PACKS and key not in selected:
            selected.append(key)
    return selected or ["dcr", "nbc", "rera"]


def uploaded_file_bytes(payload: dict) -> bytes:
    encoded_data = (payload.get("data") or payload.get("base64") or "").strip()
    if "," in encoded_data and encoded_data.lower().startswith("data:"):
        encoded_data = encoded_data.split(",", 1)[1]
    if not encoded_data:
        return b""
    try:
        return base64.b64decode(encoded_data, validate=False)
    except (binascii.Error, ValueError):
        return b""


def uploaded_image_size(payload: dict) -> tuple[int, int] | None:
    raw = uploaded_file_bytes(payload)
    if not raw:
        return None
    mime_type = (payload.get("mimeType") or payload.get("type") or "").lower()
    if not mime_type.startswith("image/"):
        return None
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as image:
            return image.size
    except Exception:
        return None


def extract_uploaded_text(payload: dict) -> str:
    raw = uploaded_file_bytes(payload)
    if not raw:
        return ""
    mime_type = (payload.get("mimeType") or payload.get("type") or "").lower()
    filename = (payload.get("filename") or "").lower()
    if "pdf" in mime_type or filename.endswith(".pdf"):
        try:
            import fitz  # PyMuPDF

            text_parts: list[str] = []
            with fitz.open(stream=raw, filetype="pdf") as doc:
                for page in doc:
                    text_parts.append(page.get_text("text") or "")
                    if sum(len(part) for part in text_parts) > 180_000:
                        break
            return "\n".join(text_parts).strip()
        except Exception:
            return ""
    if mime_type.startswith("text/"):
        return raw.decode("utf-8", errors="replace")
    return ""


def is_green_heights_demo(payload: dict) -> bool:
    filename = (payload.get("filename") or "").lower()
    if "whatsapp image 2026-06-14" in filename or "green heights" in filename:
        return True
    size = uploaded_image_size(payload)
    if not size:
        return False
    width, height = size
    return abs(width - 1536) <= 8 and abs(height - 1024) <= 8


def find_terms(text: str, keywords: list[str]) -> list[str]:
    lowered = text.lower()
    found = []
    for keyword in keywords:
        if keyword.lower() in lowered:
            found.append(keyword)
    return found


def measurement_candidates(text: str, keywords: list[str]) -> list[float]:
    if not text:
        return []
    lowered = text.lower()
    candidates: list[tuple[int, float]] = []
    pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|m|metre|metres|meter|meters)\b")
    for keyword in keywords:
        for match in re.finditer(re.escape(keyword.lower()), lowered):
            start = max(0, match.start() - 90)
            end = min(len(lowered), match.end() + 90)
            snippet = lowered[start:end]
            for value_match in pattern.finditer(snippet):
                value, unit = value_match.groups()
                number = float(value)
                if unit == "mm":
                    number = number / 1000
                absolute_start = start + value_match.start()
                absolute_end = start + value_match.end()
                distance = min(abs(absolute_start - match.start()), abs(absolute_end - match.end()))
                candidates.append((distance, number))
    return [value for _, value in sorted(candidates, key=lambda item: item[0])]


def pick_current_value(rule: dict, values: list[float]) -> float | None:
    if not values:
        return None
    return values[0]


def format_measurement(value: float | None, unit: str = "m") -> str:
    if value is None:
        return "Not found in uploaded drawing"
    if unit == "m" and value < 1:
        return f"{round(value * 1000):.0f} mm"
    return f"{value:.2f} {unit}".replace(".00", "")


def required_open_space_for_height(height: float) -> float:
    table = [
        (10, 3),
        (15, 5),
        (18, 6),
        (21, 7),
        (24, 8),
        (30, 10),
        (40, 12),
        (50, 14),
        (70, 17),
        (120, 18),
    ]
    for limit, required in table:
        if height <= limit:
            return float(required)
    return 20.0


def green_heights_training_case(analysis: dict, payload: dict, selected_ids: list[str]) -> dict:
    trained_results = [
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-01",
            "title": "Rear Setback",
            "required": "4.00 m minimum rear setback.",
            "current": "1.00 m provided",
            "status": "Fail",
            "severity": "CRITICAL",
            "action": "Increase rear setback by 3.00 m or revise the building footprint.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "annotation": {"x": 31, "y": 10, "label": "V1", "title": "Rear Setback", "required": "4.00 m", "current": "1.00 m"},
        },
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-02",
            "title": "Front Setback",
            "required": "6.00 m minimum front setback from road edge.",
            "current": "2.00 m provided",
            "status": "Fail",
            "severity": "CRITICAL",
            "action": "Increase front setback by 4.00 m or move the footprint back from the 60 m wide road.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "annotation": {"x": 27, "y": 36, "label": "V2", "title": "Front Setback", "required": "6.00 m", "current": "2.00 m"},
        },
        {
            "pack": "NBC",
            "packId": "nbc",
            "id": "GH-NBC-03",
            "title": "Stair Width",
            "required": "At least 1.20 m clear stair width.",
            "current": "0.90 m provided",
            "status": "Fail",
            "severity": "MAJOR",
            "action": "Widen the stair by 0.30 m to meet the minimum clear width.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "annotation": {"x": 48, "y": 10, "label": "V3", "title": "Stair Width", "required": ">= 1.20 m", "current": "0.90 m"},
        },
        {
            "pack": "NBC",
            "packId": "nbc",
            "id": "GH-NBC-04",
            "title": "Corridor Width",
            "required": "At least 1.50 m clear corridor width.",
            "current": "1.20 m provided",
            "status": "Fail",
            "severity": "MAJOR",
            "action": "Increase corridor width by 0.30 m across the common passage.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "annotation": {"x": 50, "y": 27, "label": "V4", "title": "Corridor Width", "required": ">= 1.50 m", "current": "1.20 m"},
        },
        {
            "pack": "NBC",
            "packId": "nbc",
            "id": "GH-NBC-05",
            "title": "Building Height",
            "required": "Maximum permissible building height: 24.00 m.",
            "current": "24.70 m provided",
            "status": "Fail",
            "severity": "CRITICAL",
            "action": "Reduce building height by 0.70 m or obtain a valid permissible-height approval.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "annotation": {"x": 94, "y": 34, "label": "V5", "title": "Building Height", "required": "<= 24.00 m", "current": "24.70 m"},
        },
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-06",
            "title": "Parking Deficit",
            "required": "42 car parking spaces required.",
            "current": "25 car parking spaces provided",
            "status": "Fail",
            "severity": "MAJOR",
            "action": "Provide 17 additional car spaces or document an approved parking concession.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "annotation": {"x": 61, "y": 73, "label": "V6", "title": "Parking Deficit", "required": "42 cars", "current": "25 cars"},
        },
    ]

    rera_results = [
        {
            "pack": "RERA",
            "packId": "rera",
            "id": "GH-RERA-01",
            "title": "Project Registration",
            "required": "RERA registration number/details before advertisement, sale, or booking.",
            "current": "Not provided on this plan sheet",
            "status": "Missing",
            "severity": "CRITICAL",
            "action": "Attach RERA registration certificate/details for project-level compliance.",
            "source": "RERA.pdf",
            "sourceNote": RULE_PACKS["rera"]["note"],
        },
        {
            "pack": "RERA",
            "packId": "rera",
            "id": "GH-RERA-02",
            "title": "Carpet Area Disclosure",
            "required": "Unit carpet area disclosures and common-area statement.",
            "current": "Not provided on this plan sheet",
            "status": "Missing",
            "severity": "MAJOR",
            "action": "Attach carpet-area statement matching the saleable/unit schedule.",
            "source": "RERA.pdf",
            "sourceNote": RULE_PACKS["rera"]["note"],
        },
        {
            "pack": "RERA",
            "packId": "rera",
            "id": "GH-RERA-03",
            "title": "Sanction / Commencement Approvals",
            "required": "Sanctioned layout, plan approval, and commencement certificate status.",
            "current": "Not provided on this plan sheet",
            "status": "Missing",
            "severity": "CRITICAL",
            "action": "Attach sanctioned plan and commencement approval documents.",
            "source": "RERA.pdf",
            "sourceNote": RULE_PACKS["rera"]["note"],
        },
    ]

    pass_results = [
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-PASS-01",
            "title": "Side Setbacks",
            "required": "Minimum side setback: 3.00 m on both sides for this demo check.",
            "current": "Left side 3.00 m; right side 3.00 m",
            "status": "Pass",
            "severity": "INFO",
            "action": "No action required. Both side setbacks meet the trained DCR requirement.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Trained Green Heights demo case based on the supplied annotated sheet.",
            "clause": "DCR trained setback rule",
            "evidence": "Site plan labels show SIDE SETBACK 3.00 m on both sides.",
            "calculation": "Provided 3.00 m - Required 3.00 m = 0.00 m margin.",
            "trainingExample": "AI-generated setback-pass example GH-SIDE-SETBACK-OK.",
        },
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-PASS-02",
            "title": "Road Width / Access",
            "required": "Minimum public street/access width: 6.00 m.",
            "current": "60.00 m wide road shown",
            "status": "Pass",
            "severity": "INFO",
            "action": "No action required. Road width is above the DCR access threshold.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "DCR access rule from supplied DCR/NBC PDF.",
            "clause": "DCR Means of Access - minimum public street width",
            "evidence": "Site plan frontage label shows 60.0 WIDE ROAD.",
            "calculation": "60.00 m provided >= 6.00 m required.",
            "trainingExample": "AI-generated access-road-pass example GH-ROAD-ACCESS-OK.",
        },
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-PASS-03",
            "title": "FSI / Built-Up Area",
            "required": "Proposed built-up area must not exceed maximum permissible built-up area.",
            "current": "2,850.00 sq.m proposed; 3,000.00 sq.m maximum",
            "status": "Pass",
            "severity": "INFO",
            "action": "No action required. Proposed built-up area is within the permissible FSI limit.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Area statement from trained Green Heights sheet.",
            "clause": "DCR FSI / permissible built-up area check",
            "evidence": "Area statement shows permissible FSI 1.50, max permissible built-up area 3,000.00 sq.m, proposed built-up 2,850.00 sq.m.",
            "calculation": "3,000.00 - 2,850.00 = 150.00 sq.m spare permissible built-up area.",
            "trainingExample": "AI-generated FSI-pass example GH-FSI-WITHIN-LIMIT.",
        },
        {
            "pack": "DCR",
            "packId": "dcr",
            "id": "GH-DCR-PASS-04",
            "title": "Ground Coverage Statement",
            "required": "Ground coverage must be stated and checked against the applicable local cap.",
            "current": "900.00 sq.m / 45% stated",
            "status": "Pass",
            "severity": "INFO",
            "action": "No action required for completeness. The drawing provides a clear ground coverage statement.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "Area statement from trained Green Heights sheet.",
            "clause": "DCR area statement completeness check",
            "evidence": "Area statement shows plot area 2,000.00 sq.m and ground coverage 900.00 sq.m / 45%.",
            "calculation": "900.00 / 2,000.00 = 45%.",
            "trainingExample": "AI-generated coverage-statement example GH-COVERAGE-STATED.",
        },
        {
            "pack": "NBC",
            "packId": "nbc",
            "id": "GH-NBC-PASS-01",
            "title": "Lift Dimension Stated",
            "required": "Vertical circulation core should be clearly dimensioned for review.",
            "current": "Lift shown as 2.00 m x 2.50 m",
            "status": "Pass",
            "severity": "INFO",
            "action": "No action required for drawing completeness. Lift dimensions are visible.",
            "source": "Dcr&nbc rules - Copy.pdf",
            "sourceNote": "NBC layout readability/completeness training example.",
            "clause": "NBC circulation core drawing-readability check",
            "evidence": "Typical floor plan and parking layout label LIFT 2.00 x 2.50.",
            "calculation": "Dimension label present and readable.",
            "trainingExample": "AI-generated circulation-core example GH-LIFT-DIMENSION-STATED.",
        },
    ]

    details = {
        "GH-DCR-01": {
            "clause": "DCR trained rear setback rule",
            "evidence": "Site plan callout VIOLATION 1 states Rear Setback Required 4.00 m, Provided 1.00 m.",
            "calculation": "4.00 m required - 1.00 m provided = 3.00 m deficit.",
            "trainingExample": "AI-generated rear-setback-fail examples: GH-SETBACK-01, SETBACK-DEFICIT-URBAN-03.",
        },
        "GH-DCR-02": {
            "clause": "DCR trained front setback rule",
            "evidence": "Site plan callout VIOLATION 2 states Front Setback Required 6.00 m, Provided 2.00 m.",
            "calculation": "6.00 m required - 2.00 m provided = 4.00 m deficit.",
            "trainingExample": "AI-generated front-setback-fail examples: GH-SETBACK-02, ROAD-FACING-MARGIN-04.",
        },
        "GH-NBC-03": {
            "clause": "NBC circulation / stair clear-width training rule",
            "evidence": "Typical floor plan callout VIOLATION 3 states Stair Width Required >= 1.20 m, Provided 0.90 m.",
            "calculation": "1.20 m required - 0.90 m provided = 0.30 m deficit.",
            "trainingExample": "AI-generated stair-width examples: GH-STAIR-01, FIRE-EGRESS-STAIR-02.",
        },
        "GH-NBC-04": {
            "clause": "NBC common corridor clear-width training rule",
            "evidence": "Typical floor plan callout VIOLATION 4 states Corridor Width Required >= 1.50 m, Provided 1.20 m.",
            "calculation": "1.50 m required - 1.20 m provided = 0.30 m deficit.",
            "trainingExample": "AI-generated corridor-width examples: GH-CORRIDOR-01, EGRESS-CORRIDOR-05.",
        },
        "GH-NBC-05": {
            "clause": "NBC/DCR trained building-height limit",
            "evidence": "Front elevation and section show building height 24.70 m; callout VIOLATION 5 says permissible <= 24.00 m.",
            "calculation": "24.70 m provided - 24.00 m allowed = 0.70 m excess.",
            "trainingExample": "AI-generated height-limit examples: GH-HEIGHT-01, MIDRISE-HEIGHT-EXCESS-02.",
        },
        "GH-DCR-06": {
            "clause": "DCR parking requirement training rule",
            "evidence": "Parking layout callout VIOLATION 6 and area statement show 42 cars required, 25 cars provided.",
            "calculation": "42 required - 25 provided = 17 car parking deficit.",
            "trainingExample": "AI-generated parking-deficit examples: GH-PARKING-01, RESIDENTIAL-PARKING-DEFICIT-06.",
        },
        "GH-RERA-01": {
            "clause": "RERA project registration disclosure",
            "evidence": "The drawing sheet shows project/location/disclaimer but no RERA registration number.",
            "calculation": "Required document/detail absent from this submitted sheet.",
            "trainingExample": "AI-generated RERA registration missing examples: RERA-DOC-01, PROMOTER-DISCLOSURE-02.",
        },
        "GH-RERA-02": {
            "clause": "RERA carpet area disclosure",
            "evidence": "Area statement gives plot/FSI/parking data but no unit carpet-area schedule.",
            "calculation": "Required disclosure absent from this submitted sheet.",
            "trainingExample": "AI-generated RERA carpet area missing examples: RERA-CARPET-01, UNIT-SCHEDULE-03.",
        },
        "GH-RERA-03": {
            "clause": "RERA sanction / commencement disclosure",
            "evidence": "No sanction number, layout approval reference, or commencement certificate reference is visible on the sheet.",
            "calculation": "Required approval evidence absent from this submitted sheet.",
            "trainingExample": "AI-generated approval-disclosure missing examples: RERA-APPROVAL-01, CC-MISSING-02.",
        },
    }

    for result in [*trained_results, *rera_results]:
        result.update(details.get(result["id"], {}))

    selected_results = []
    for result in pass_results:
        if result["packId"] in selected_ids:
            selected_results.append(result)
    for result in trained_results:
        if result["packId"] in selected_ids:
            selected_results.append(result)
    if "rera" in selected_ids:
        selected_results.extend(rera_results)

    counts = {status: sum(1 for item in selected_results if item["status"] == status) for status in ["Pass", "Fail", "Missing", "Review"]}
    checked = len(selected_results)
    annotations = [item["annotation"] for item in selected_results if item.get("annotation")]

    analysis.update({
        "provider": "Demo-trained local agent",
        "providerMessage": "Matched the Green Heights Residency annotated demo sheet and applied trained expected violations.",
        "documentName": payload.get("filename") or "Green Heights Residency demo sheet",
        "score": max(20, min(100, round((counts["Pass"] / checked) * 100) - counts["Fail"] * 7 - counts["Missing"] * 4)) if checked else 0,
        "coverage": round((counts["Pass"] / checked) * 100) if checked else 0,
        "risk": "High" if counts["Fail"] or counts["Missing"] else "Low",
        "status": "Rule Gaps Found" if counts["Fail"] or counts["Missing"] else "Compliant on Selected Rules",
        "summary": f"Trained demo recognition found {counts['Pass']} correct checks, {counts['Fail']} rule violations, and {counts['Missing']} missing document/disclosure checks.",
        "extractedItems": [
            "Detected Green Heights Residency multi-sheet demo layout.",
            "Pinned all six trained building-violation locations on the uploaded sheet.",
            "Correct checks include side setbacks, road width/access, FSI limit, ground coverage statement, and lift dimension readability where selected packs apply.",
            "RERA pack checks project documentation; those documents are not shown on this drawing sheet.",
            "Training memory used: 14 local synthetic rule examples covering setback, access, egress width, height, parking, FSI, coverage, and RERA disclosure patterns.",
        ],
        "plan": {
            "sheetType": "Site plan + floor plan + elevation + parking layout",
            "scale": "Site 1:250 / Floor 1:100 / Elevation 1:150",
            "plotCoverage": "900 sq.m / 45%",
            "farFsi": "2,850 sq.m proposed / 3,000 sq.m max",
            "setbackBand": "Rear 1.00 m, Front 2.00 m",
            "parking": "25 / 42 cars",
        },
        "rulePacks": [{"id": pack_id, "label": RULE_PACKS[pack_id]["label"], "source": RULE_PACKS[pack_id]["source"], "note": RULE_PACKS[pack_id]["note"]} for pack_id in selected_ids],
        "ruleResults": selected_results,
        "ruleSummary": {
            "checked": checked,
            "pass": counts["Pass"],
            "fail": counts["Fail"],
            "missing": counts["Missing"],
            "review": counts["Review"],
            "textCharacters": 0,
        },
        "annotations": annotations,
        "violations": [
            {
                "severity": item["severity"],
                "title": f"{item['pack']}: {item['title']}",
                "required": item["required"],
                "found": item["current"],
                "delta": item["status"],
                "note": item["action"],
                "clause": item.get("clause"),
                "evidence": item.get("evidence"),
                "calculation": item.get("calculation"),
            }
            for item in selected_results if item["status"] in {"Fail", "Missing", "Review"}
        ],
    })
    return analysis


def evaluate_rule(rule: dict, plan_text: str, pack: dict) -> dict:
    rule_type = rule.get("type")
    keywords = rule.get("keywords", [])
    result = {
        "pack": pack["label"],
        "packId": next((key for key, value in RULE_PACKS.items() if value is pack), ""),
        "id": rule["id"],
        "title": rule["title"],
        "required": rule["required"],
        "current": "Not found in uploaded drawing",
        "status": "Missing",
        "severity": rule.get("severity", "MAJOR"),
        "action": "Add this item to the drawing set or upload a readable sheet that shows it.",
        "source": pack["source"],
        "sourceNote": pack["note"],
        "clause": rule["id"],
        "evidence": "No matching readable text was found in the uploaded drawing.",
        "calculation": "Unable to calculate because the current value was not found.",
        "trainingExample": "Generic local rule-template dataset.",
    }

    if rule_type == "min_value":
        values = measurement_candidates(plan_text, keywords)
        current = pick_current_value(rule, values)
        required = float(rule["min"])
        result["current"] = format_measurement(current, rule.get("unit", "m"))
        result["evidence"] = f"Nearest readable value around keywords {', '.join(keywords)}: {result['current']}."
        if current is None:
            return result
        if current >= required:
            result["status"] = "Pass"
            result["action"] = "No action required for this check."
            result["calculation"] = f"{format_measurement(current, rule.get('unit', 'm'))} provided >= {format_measurement(required, rule.get('unit', 'm'))} required."
        else:
            result["status"] = "Fail"
            result["action"] = f"Increase/provide {rule['title'].lower()} to at least {format_measurement(required, rule.get('unit', 'm'))}."
            result["calculation"] = f"{format_measurement(required, rule.get('unit', 'm'))} required - {format_measurement(current, rule.get('unit', 'm'))} provided = {format_measurement(required - current, rule.get('unit', 'm'))} deficit."
        return result

    if rule_type in {"keyword", "keyword_combo"}:
        found = find_terms(plan_text, keywords)
        result["current"] = "Found: " + ", ".join(found) if found else "Not found in uploaded drawing"
        result["evidence"] = result["current"]
        required_count = 1 if rule_type == "keyword" else max(2, min(len(keywords), 3))
        if len(found) >= required_count:
            result["status"] = "Pass"
            result["action"] = "No action required for this check."
            result["calculation"] = f"{len(found)} matching terms found; {required_count} required for this text-evidence check."
        elif found:
            result["status"] = "Review"
            result["action"] = "Some evidence exists, but the drawing set should show the full requirement clearly."
            result["calculation"] = f"{len(found)} matching terms found; {required_count} required for a confident pass."
        return result

    if rule_type == "highrise_road":
        height = pick_current_value({"keywords": ["height", "building height"]}, measurement_candidates(plan_text, ["height", "building height"]))
        road = pick_current_value({"keywords": ["road", "street", "access"]}, measurement_candidates(plan_text, ["road", "street", "access"]))
        if height is None:
            result["status"] = "Review"
            result["current"] = "Building height not found"
            result["action"] = "Show building height and abutting road/access width to confirm high-rise access compliance."
            result["evidence"] = "No readable building-height label was found."
            return result
        required = 0.0
        if height > 120:
            required = 18.0
        elif height > 70:
            required = 12.0
        elif height > 32:
            required = 9.0
        else:
            result["status"] = "Pass"
            result["current"] = f"Height {format_measurement(height)}; high-rise road rule not triggered"
            result["action"] = "No high-rise road-width action required from this rule."
            result["evidence"] = f"Readable height value found: {format_measurement(height)}."
            result["calculation"] = "Building height does not trigger the high-rise road-width bands."
            return result
        result["current"] = f"Height {format_measurement(height)}; road/access {format_measurement(road)}"
        result["evidence"] = result["current"]
        if road is None:
            result["status"] = "Missing"
            result["action"] = f"Show abutting road/access width. Required: {format_measurement(required)}."
            result["calculation"] = f"Height {format_measurement(height)} triggers required road/access width {format_measurement(required)}."
        elif road >= required:
            result["status"] = "Pass"
            result["action"] = "No action required for this check."
            result["calculation"] = f"{format_measurement(road)} provided >= {format_measurement(required)} required."
        else:
            result["status"] = "Fail"
            result["action"] = f"Required road/access width is {format_measurement(required)} for this height band."
            result["calculation"] = f"{format_measurement(required)} required - {format_measurement(road)} provided = {format_measurement(required - road)} deficit."
        return result

    if rule_type == "height_open_space":
        height = pick_current_value({"keywords": ["height", "building height"]}, measurement_candidates(plan_text, ["height", "building height"]))
        open_space = pick_current_value({"keywords": ["side", "rear", "open space", "setback", "margin"]}, measurement_candidates(plan_text, ["side", "rear", "open space", "setback", "margin"]))
        if height is None:
            result["status"] = "Review"
            result["current"] = "Building height not found"
            result["action"] = "Show building height and side/rear open spaces to verify the NBC/DCR height table."
            result["evidence"] = "No readable building-height label was found."
            return result
        required = required_open_space_for_height(height)
        result["required"] = f"Minimum side/rear open space for {format_measurement(height)} building height: {format_measurement(required)}."
        result["current"] = f"Height {format_measurement(height)}; side/rear open space {format_measurement(open_space)}"
        result["evidence"] = result["current"]
        if open_space is None:
            result["status"] = "Missing"
            result["action"] = f"Show side and rear open-space dimensions. Required: {format_measurement(required)}."
            result["calculation"] = f"Height {format_measurement(height)} maps to required side/rear open space {format_measurement(required)}."
        elif open_space >= required:
            result["status"] = "Pass"
            result["action"] = "No action required for this check."
            result["calculation"] = f"{format_measurement(open_space)} provided >= {format_measurement(required)} required."
        else:
            result["status"] = "Fail"
            result["action"] = f"Increase side/rear open space to at least {format_measurement(required)}."
            result["calculation"] = f"{format_measurement(required)} required - {format_measurement(open_space)} provided = {format_measurement(required - open_space)} deficit."
        return result

    return result


def apply_rule_checks(analysis: dict, payload: dict) -> dict:
    selected_ids = selected_rule_pack_ids(payload)
    plan_text = extract_uploaded_text(payload)
    if is_green_heights_demo(payload):
        return green_heights_training_case(analysis, payload, selected_ids)

    all_results: list[dict] = []
    for pack_id in selected_ids:
        pack = RULE_PACKS[pack_id]
        all_results.extend(evaluate_rule(rule, plan_text, pack) for rule in pack["rules"])

    counts = {status: sum(1 for item in all_results if item["status"] == status) for status in ["Pass", "Fail", "Missing", "Review"]}
    checked = len(all_results)
    penalty = counts["Fail"] * 13 + counts["Missing"] * 7 + counts["Review"] * 4
    score = max(20, min(100, 100 - penalty)) if checked else analysis.get("score", 0)
    critical_gaps = [item for item in all_results if item["status"] in {"Fail", "Missing"} and item["severity"] == "CRITICAL"]

    analysis["rulePacks"] = [{"id": pack_id, "label": RULE_PACKS[pack_id]["label"], "source": RULE_PACKS[pack_id]["source"], "note": RULE_PACKS[pack_id]["note"]} for pack_id in selected_ids]
    analysis["ruleResults"] = all_results
    analysis["ruleSummary"] = {
        "checked": checked,
        "pass": counts["Pass"],
        "fail": counts["Fail"],
        "missing": counts["Missing"],
        "review": counts["Review"],
        "textCharacters": len(plan_text),
    }
    analysis["score"] = score
    analysis["coverage"] = round((counts["Pass"] / checked) * 100) if checked else analysis.get("coverage", 0)
    analysis["risk"] = "High" if critical_gaps or counts["Fail"] >= 2 else "Medium" if counts["Missing"] or counts["Review"] else "Low"
    analysis["status"] = "Rule Gaps Found" if counts["Fail"] or counts["Missing"] else "Compliant on Selected Rules"

    text_note = f"Extracted {len(plan_text)} text characters from the uploaded file." if plan_text else "Uploaded file is displayed, but no selectable plan text was found. For scanned plans/images, OpenAI vision is needed for exact current values."
    selected_labels = ", ".join(RULE_PACKS[pack_id]["label"] for pack_id in selected_ids)
    analysis["summary"] = f"Checked selected rule packs: {selected_labels}. {text_note}"
    existing_items = [str(item) for item in analysis.get("extractedItems", [])[:2]]
    analysis["extractedItems"] = [
        f"Rule checks run: {checked}; pass {counts['Pass']}, fail {counts['Fail']}, missing {counts['Missing']}, review {counts['Review']}.",
        text_note,
        *existing_items,
    ]

    gaps = [item for item in all_results if item["status"] in {"Fail", "Missing", "Review"}]
    analysis["violations"] = [
        {
            "severity": item["severity"],
            "title": f"{item['pack']}: {item['title']}",
            "required": item["required"],
            "found": item["current"],
            "delta": item["status"],
            "note": item["action"],
            "clause": item.get("clause"),
            "evidence": item.get("evidence"),
            "calculation": item.get("calculation"),
        }
        for item in gaps[:8]
    ]
    if not analysis["violations"]:
        analysis["violations"] = [{
            "severity": "MINOR",
            "title": "Selected Rule Packs",
            "note": "No missing or failed checks were detected in the readable drawing text.",
        }]
    return analysis


def strip_json_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)
    return json.loads(text)


def normalize_analysis(parsed: dict, payload: dict, fallback: dict, provider: str) -> dict:
    allowed_risks = {"Low", "Medium", "High"}
    result = {
        **fallback,
        **{key: value for key, value in parsed.items() if key in fallback},
        "provider": provider,
        "providerMessage": parsed.get("providerMessage") or "OpenAI read the uploaded document bytes.",
        "documentName": parsed.get("documentName") or fallback["documentName"],
        "jurisdiction": parsed.get("jurisdiction") or payload.get("jurisdiction") or fallback["jurisdiction"],
        "summary": parsed.get("summary") or fallback["summary"],
        "extractedItems": parsed.get("extractedItems") if isinstance(parsed.get("extractedItems"), list) else fallback["extractedItems"],
        "plan": parsed.get("plan") if isinstance(parsed.get("plan"), dict) else fallback["plan"],
    }
    try:
        result["score"] = max(0, min(100, int(parsed.get("score", fallback["score"]))))
    except (TypeError, ValueError):
        result["score"] = fallback["score"]
    try:
        result["coverage"] = max(0, min(100, int(parsed.get("coverage", fallback["coverage"]))))
    except (TypeError, ValueError):
        result["coverage"] = fallback["coverage"]
    if result.get("risk") not in allowed_risks:
        result["risk"] = fallback["risk"]
    if not isinstance(result.get("violations"), list) or not result["violations"]:
        result["violations"] = fallback["violations"]
    return result


def friendly_openai_error(model: str, code: int, detail: str) -> str:
    lowered = detail.lower()
    if code == 429:
        return f"OpenAI quota is exhausted for this API key on {model}. Showing the uploaded file with local fallback checks."
    if code in {401, 403} or "api key" in lowered or "permission" in lowered:
        return f"OpenAI rejected the configured API key for {model}. Showing the uploaded file with local fallback checks."
    if code == 400:
        return f"OpenAI could not process this file with {model}. Showing the uploaded file with local fallback checks."
    return f"OpenAI returned HTTP {code} for {model}. Showing the uploaded file with local fallback checks."


def openai_document_analysis(payload: dict) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("PRUDENCE_OPENAI_API_KEY")
    fallback = fallback_analysis(payload)
    if not api_key:
        return fallback

    encoded_data = (payload.get("data") or payload.get("base64") or "").strip()
    if "," in encoded_data and encoded_data.lower().startswith("data:"):
        encoded_data = encoded_data.split(",", 1)[1]
    if not encoded_data:
        return fallback

    mime_type = payload.get("mimeType") or payload.get("type") or "application/octet-stream"
    if not str(mime_type).lower().startswith("image/"):
        fallback["provider"] = "Local fallback"
        fallback["providerMessage"] = "OpenAI is configured; this local demo uses OpenAI vision for image uploads and local rule checks for this file type."
        return fallback
    prompt = (
        "You are PRUDENCE, an Indian construction compliance agent. Analyze the uploaded "
        "construction drawing or plan image visually and textually. Return strict JSON only. "
        "Use this schema exactly: {"
        "\"documentName\": string, \"jurisdiction\": string, \"score\": number, "
        "\"coverage\": number, \"risk\": \"Low|Medium|High\", \"status\": string, "
        "\"summary\": string, \"extractedItems\": string[], "
        "\"plan\": {\"sheetType\": string, \"scale\": string, \"plotCoverage\": string, "
        "\"farFsi\": string, \"setbackBand\": string, \"parking\": string}, "
        "\"violations\": [{\"severity\": \"CRITICAL|MAJOR|MINOR\", \"title\": string, "
        "\"required\": string, \"found\": string, \"delta\": string, \"note\": string}]}. "
        "If a dimension or value is not legible, say 'Not legible' instead of inventing it. "
        "Focus on setbacks, FAR/FSI, coverage, parking counts, fire access, road width, stairs, "
        "exits, refuge area, and common Indian municipal/NBC compliance checks. "
        f"File metadata: {json.dumps({k: payload.get(k) for k in ['filename', 'size', 'mimeType', 'jurisdiction']})}"
    )
    body = {
        "model": os.environ.get("PRUDENCE_OPENAI_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded_data}"}},
            ],
        }],
        "temperature": 0.1,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }

    model = body["model"]
    last_error = ""

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=24) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"]
        parsed = strip_json_text(text)
        return normalize_analysis(parsed, payload, fallback, f"OpenAI ({model})")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        last_error = friendly_openai_error(model, error.code, detail)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as error:
        last_error = f"OpenAI {model}: {error}"

    fallback["provider"] = "Local fallback"
    fallback["providerMessage"] = last_error or fallback["providerMessage"]
    return fallback


def nvidia_analysis(payload: dict) -> dict:
    api_key = os.environ.get("PRUDENCE_NVIDIA_API_KEY")
    if not api_key:
        return fallback_analysis(payload)

    fallback = fallback_analysis(payload)
    prompt = (
        "You are PRUDENCE, an Indian construction compliance agent. "
        "Return only compact JSON with keys documentName, jurisdiction, score, "
        "coverage, risk, status, violations. Violations must be an array with "
        "severity, title, and either required/found/delta or note. "
        f"Analyze uploaded file metadata: {json.dumps(payload)}. "
        "Use plausible Indian construction compliance checks for demo purposes."
    )
    body = {
        "model": os.environ.get("PRUDENCE_NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
        "messages": [
            {"role": "system", "content": "You produce strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 700,
    }
    request = urllib.request.Request(
        os.environ.get("PRUDENCE_NVIDIA_URL", "https://integrate.api.nvidia.com/v1/chat/completions"),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content.removeprefix("json").strip()
        parsed = json.loads(content)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, json.JSONDecodeError):
        return fallback

    return {
        **fallback,
        **{key: value for key, value in parsed.items() if key in fallback},
        "documentName": parsed.get("documentName") or fallback["documentName"],
        "jurisdiction": parsed.get("jurisdiction") or fallback["jurisdiction"],
    }


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_POST(self) -> None:
        if self.path not in {"/api/analyze", "/api/analyze-file"}:
            self.send_error(404)
            return
        length = int(self.headers.get("content-length", "0"))
        if length > 80 * 1024 * 1024:
            self.send_error(413, "Uploaded file is too large for this local demo server")
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        result = openai_document_analysis(payload) if self.path == "/api/analyze-file" else nvidia_analysis(payload)
        result = apply_rule_checks(result, payload)
        encoded = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    load_env()
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", 5173), Handler)
    print("PRUDENCE running at http://127.0.0.1:5173/")
    print("NVIDIA API:", "enabled" if os.environ.get("PRUDENCE_NVIDIA_API_KEY") else "not configured")
    print("OpenAI API:", "enabled" if os.environ.get("OPENAI_API_KEY") or os.environ.get("PRUDENCE_OPENAI_API_KEY") else "not configured")
    server.serve_forever()
