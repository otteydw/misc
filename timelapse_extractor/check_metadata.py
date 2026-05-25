#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "exif",
#     "hachoir",
# ]
# ///
"""Diagnostic script to verify metadata extraction for trail cam files."""

import os
from datetime import datetime

from exif import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser


def get_jpg_timestamp(path):
    """Extract DateTimeOriginal from JPG EXIF."""
    try:
        with open(path, "rb") as f:
            img = Image(f)
            if img.has_exif:
                # format: YYYY:MM:DD HH:MM:SS
                dt_str = getattr(img, "datetime_original", None)
                if dt_str:
                    return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception as e:
        print(f"Error reading JPG {path}: {e}")
    return None


def get_mp4_timestamp(path):
    """Extract creation_date from MP4 metadata."""
    try:
        parser = createParser(path)
        if not parser:
            print(f"Unable to parse MP4: {path}")
            return None
        with parser:
            metadata = extractMetadata(parser)
            if metadata:
                creation_date = metadata.get("creation_date")
                return creation_date
    except Exception as e:
        print(f"Error reading MP4 {path}: {e}")
    return None


def main():
    """Run diagnostic on example files."""
    files = [
        "/Volumes/media/Timelapse/from_gopro/100MEDIA/DSCF0001.JPG",
        "/Volumes/media/Timelapse/from_gopro/100MEDIA/DSCF0004.MP4",
    ]

    for f in files:
        if not os.path.exists(f):
            print(f"File not found: {f}")
            continue

        ext = os.path.splitext(f)[1].lower()
        ts = None
        if ext == ".jpg":
            ts = get_jpg_timestamp(f)
        elif ext == ".mp4":
            ts = get_mp4_timestamp(f)

        print(f"File: {f}")
        print(f"Extracted Timestamp: {ts}")
        if ts:
            print(f"Minute: {ts.minute}")
        print("-" * 20)


if __name__ == "__main__":
    main()
