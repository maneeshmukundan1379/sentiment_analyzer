"""
Cron-friendly PDF report generator.

Run this from a cloud scheduler or local cron. Keywords can come from CLI args or
from REPORT_KEYWORDS as a comma-separated list.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys

APP_ROOT_PATH = Path(__file__).resolve().parents[1]
if str(APP_ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(APP_ROOT_PATH))

from core.client_config import ClientReportConfig, KeywordRules, load_client_report_configs
from core.env import APP_ROOT, load_app_env
from core.platforms import SEARCH_ACTIVE_PLATFORMS
from logic import generate_pdf_report, search_keyword_rules

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


def _clients_file_configs(path: str) -> list[ClientReportConfig]:
    if not path:
        return []
    client_path = Path(path).expanduser()
    if not client_path.exists():
        raise FileNotFoundError(f"Client config file does not exist: {client_path}")
    return load_client_report_configs(client_path)


def _resolve_report_configs(args: argparse.Namespace) -> list[ClientReportConfig]:
    keywords = [item.strip() for item in args.keywords if item.strip()]
    if keywords:
        return [
            ClientReportConfig(
                name=keyword,
                keywords=KeywordRules(any=(keyword,)),
                platforms=(),
            )
            for keyword in keywords
        ]

    client_configs = _clients_file_configs(args.clients_file)
    if client_configs:
        return client_configs

    return [
        ClientReportConfig(
            name=keyword,
            keywords=KeywordRules(any=(keyword,)),
            platforms=(),
        )
        for keyword in _env_keywords()
    ]


def _upload_to_gcs(local_path: Path, bucket_name: str, prefix: str) -> str:
    if storage is None:
        raise RuntimeError("google-cloud-storage is not installed.")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    object_name = f"{prefix.strip('/')}/{local_path.name}" if prefix else local_path.name
    blob = bucket.blob(object_name)
    blob.upload_from_filename(str(local_path))
    return f"gs://{bucket_name}/{object_name}"


def _write_report(config: ClientReportConfig, output_dir: Path) -> Path:
    active_platforms = config.platforms or SEARCH_ACTIVE_PLATFORMS
    status, _html, _cleared_keyword, searched_keyword, records_payload = search_keyword_rules(
        config.keywords,
        display_keyword=config.name,
        active_platforms=active_platforms,
    )
    if not records_payload or records_payload == "[]":
        raise RuntimeError(status)

    pdf_status, temp_pdf_path = generate_pdf_report(
        records_payload,
        searched_keyword,
        report_name=config.name,
        platforms=active_platforms,
    )
    if not temp_pdf_path:
        raise RuntimeError(pdf_status)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = output_dir / f"{timestamp}-{_slugify(config.name or searched_keyword)}.pdf"
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolved report configs without collecting data or generating PDFs.",
    )
    args = parser.parse_args()

    configs = _resolve_report_configs(args)
    if not configs:
        print("No report configs supplied. Pass CLI keywords, --clients-file, or REPORT_KEYWORDS.", file=sys.stderr)
        return 2
    if args.dry_run:
        for config in configs:
            platforms = ", ".join(config.platforms or SEARCH_ACTIVE_PLATFORMS)
            terms = ", ".join(config.keywords.any)
            print(f"{config.name}: keywords=[{terms}] platforms=[{platforms}] schedule={config.schedule}")
        return 0

    output_dir = Path(args.output_dir).expanduser().resolve()
    failures = 0
    for config in configs:
        try:
            path = _write_report(config, output_dir)
            if args.gcs_bucket:
                uri = _upload_to_gcs(path, args.gcs_bucket, args.gcs_prefix)
                print(f"{config.name}: wrote {path} and uploaded {uri}")
            else:
                print(f"{config.name}: wrote {path}")
        except Exception as exc:
            failures += 1
            print(f"{config.name}: failed: {exc}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
