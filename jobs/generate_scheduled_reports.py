"""
Cron-friendly PDF report generator.

Run this from a cloud scheduler or local cron. Keywords can come from CLI args or
from REPORT_KEYWORDS as a comma-separated list.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

APP_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(APP_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(APP_ROOT_PATH))

from core.env import APP_ROOT, load_app_env
from logic import generate_pdf_report, search_social_keyword

try:
    from google.cloud import storage
except ImportError:  # pragma: no cover - optional cloud dependency
    storage = None


def _slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "keyword"


def _env_keywords() -> list[str]:
    return [item.strip() for item in (os.getenv("REPORT_KEYWORDS") or "").split(",") if item.strip()]


def _clients_file_keywords(path: str) -> list[str]:
    if not path:
        return []
    client_path = Path(path).expanduser()
    if not client_path.exists():
        raise FileNotFoundError(f"Client config file does not exist: {client_path}")

    payload = json.loads(client_path.read_text(encoding="utf-8"))
    keywords: list[str] = []
    for client in payload.get("clients", []):
        client_keywords = client.get("keywords", {})
        if isinstance(client_keywords, list):
            keywords.extend(str(item).strip() for item in client_keywords)
            continue
        keywords.extend(str(item).strip() for item in client_keywords.get("any", []))
    return [keyword for keyword in keywords if keyword]


def _resolve_keywords(args: argparse.Namespace) -> list[str]:
    keywords = [item.strip() for item in args.keywords if item.strip()]
    if keywords:
        return keywords
    config_keywords = _clients_file_keywords(args.clients_file)
    if config_keywords:
        return config_keywords
    return _env_keywords()


def _upload_to_gcs(local_path: Path, bucket_name: str, prefix: str) -> str:
    if storage is None:
        raise RuntimeError("google-cloud-storage is not installed.")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    object_name = f"{prefix.strip('/')}/{local_path.name}" if prefix else local_path.name
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(local_path))
    return f"gs://{bucket_name}/{object_name}"


def _write_report(keyword: str, output_dir: Path) -> Path:
    status, _html, _cleared_keyword, searched_keyword, records_payload = search_social_keyword(keyword)
    if not records_payload or records_payload == "[]":
        raise RuntimeError(status)

    pdf_status, temp_pdf_path = generate_pdf_report(records_payload, searched_keyword)
    if not temp_pdf_path:
        raise RuntimeError(pdf_status)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = output_dir / f"{timestamp}-{_slugify(searched_keyword)}.pdf"
    shutil.copyfile(temp_pdf_path, final_path)
    return final_path


def main() -> int:
    load_app_env()
    parser = argparse.ArgumentParser(description="Generate scheduled sentiment PDF reports.")
    parser.add_argument("keywords", nargs="*", help="Keywords to search. Falls back to REPORT_KEYWORDS.")
    parser.add_argument(
        "--clients-file",
        default=os.getenv("REPORT_CLIENTS_FILE", ""),
        help="Optional JSON client config file. Falls back to REPORT_CLIENTS_FILE.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(APP_ROOT / "reports"),
        help="Directory where generated PDFs should be written.",
    )
    parser.add_argument(
        "--gcs-bucket",
        default=os.getenv("REPORT_GCS_BUCKET", ""),
        help="Optional Google Cloud Storage bucket for generated PDFs.",
    )
    parser.add_argument(
        "--gcs-prefix",
        default=os.getenv("REPORT_GCS_PREFIX", "sentiment-reports"),
        help="Object prefix when uploading PDFs to Google Cloud Storage.",
    )
    args = parser.parse_args()

    keywords = _resolve_keywords(args)
    if not keywords:
        print("No keywords supplied. Pass CLI keywords or set REPORT_KEYWORDS.", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir).expanduser().resolve()
    failures = 0
    for keyword in keywords:
        try:
            path = _write_report(keyword, output_dir)
            if args.gcs_bucket:
                uri = _upload_to_gcs(path, args.gcs_bucket, args.gcs_prefix)
                print(f"{keyword}: wrote {path} and uploaded {uri}")
            else:
                print(f"{keyword}: wrote {path}")
        except Exception as exc:
            failures += 1
            print(f"{keyword}: failed: {exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
