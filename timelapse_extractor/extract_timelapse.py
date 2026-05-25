#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "exif",
#     "hachoir",
# ]
# ///
"""Extract 'top of the hour' timelapse files and rename them by timestamp."""

import argparse
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from exif import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_jpg_timestamp(path: Path):
    """Extract DateTimeOriginal from JPG EXIF."""
    try:
        with open(path, "rb") as f:
            img = Image(f)
            if img.has_exif:
                dt_str = getattr(img, "datetime_original", None)
                if dt_str:
                    return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        logger.debug(f"Error reading JPG EXIF {path}: {e}")
    return None


def get_mp4_timestamp(path: Path):
    """Extract creation_date from MP4 metadata."""
    try:
        parser = createParser(str(path))
        if not parser:
            return None
        with parser:
            metadata = extractMetadata(parser)
            if metadata:
                return metadata.get("creation_date")
    except Exception as e:
        logger.debug(f"Error reading MP4 metadata {path}: {e}")
    return None


def get_unique_path(base_dir: Path, filename: str, used_paths: set) -> Path:
    """Generate a unique path by appending a counter if the destination exists or is already planned."""
    name = filename.rsplit(".", 1)[0]
    ext = filename.rsplit(".", 1)[1] if "." in filename else ""
    ext = f".{ext}" if ext else ""

    target = base_dir / filename
    counter = 1

    while target.exists() or target in used_paths:
        target = base_dir / f"{name}_{counter}{ext}"
        counter += 1

    used_paths.add(target)
    return target


def main():
    """Extract timelapse files based on top-of-the-hour timestamps."""
    parser = argparse.ArgumentParser(
        description="Extract 'top of the hour' timelapse files and rename them by timestamp."
    )
    parser.add_argument("-s", "--source", type=Path, required=True, help="Source parent directory to scan recursively")
    parser.add_argument(
        "-p",
        "--primary",
        dest="primary_image_dest",
        type=Path,
        required=True,
        help="Target directory for the first JPG of each hour",
    )
    parser.add_argument(
        "-e",
        "--extra",
        dest="extra_image_dest",
        type=Path,
        required=True,
        help="Target directory for additional JPGs from the top of the hour",
    )
    parser.add_argument(
        "-m", "--movies", dest="movie_dest", type=Path, required=True, help="Target directory for top-of-hour MP4s"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report intended actions without moving files")

    args = parser.parse_args()

    # Validation
    if not args.source.is_dir():
        logger.error(f"Source directory does not exist: {args.source}")
        sys.exit(1)
    for d in [args.primary_image_dest, args.extra_image_dest, args.movie_dest]:
        if not d.is_dir():
            logger.error(f"Destination directory does not exist: {d}")
            sys.exit(1)

    used_paths = set()
    seen_hours = set()  # Track YYYYMMDD_HH
    files_processed = 0

    logger.info(f"Starting extraction from {args.source}...")
    if args.dry_run:
        logger.info("DRY RUN MODE: No files will be moved.")

    for root, _, filenames in os.walk(args.source):
        for filename in sorted(filenames):
            path = Path(root) / filename
            ext = path.suffix.lower()

            ts = None
            dest_dir = None

            if ext == ".jpg":
                ts = get_jpg_timestamp(path)
            elif ext == ".mp4":
                ts = get_mp4_timestamp(path)
                dest_dir = args.movie_dest
            else:
                continue

            files_processed += 1

            if ts and ts.minute == 0:
                # For JPGs, decide between primary and extra
                if ext == ".jpg":
                    hour_key = ts.strftime("%Y%m%d_%H")
                    if hour_key not in seen_hours:
                        dest_dir = args.primary_image_dest
                        seen_hours.add(hour_key)
                    else:
                        dest_dir = args.extra_image_dest

                new_filename = ts.strftime("%Y%m%d_%H%M%S") + ext
                dest_path = get_unique_path(dest_dir, new_filename, used_paths)

                log_prefix = "[DRY RUN] " if args.dry_run else ""
                logger.info(f"{log_prefix}Moving {path.relative_to(args.source)} -> {dest_path}")

                if not args.dry_run:
                    try:
                        shutil.move(str(path), str(dest_path))
                    except Exception as e:
                        logger.error(f"Failed to move {path}: {e}")
            else:
                log_prefix = "[DRY RUN] " if args.dry_run else ""
                logger.info(
                    f"{log_prefix}Skipping {path.relative_to(args.source)} (Minute: {ts.minute if ts else 'N/A'})"
                )

    status_msg = "to be moved" if args.dry_run else "moved"
    logger.info(f"Processing complete. Files scanned: {files_processed}, Files {status_msg}: {len(used_paths)}")


if __name__ == "__main__":
    main()
