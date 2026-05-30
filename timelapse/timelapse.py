# /// script
# dependencies = [
#     "pillow",
# ]
# ///
"""Timelapse compiler and daytime filter tool using EXIF metadata and ffmpeg."""

import argparse
import concurrent.futures
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

DEFAULT_BAR_HEIGHT = 460


def get_image_iso(image_path: Path) -> int | None:
    """Extract ISO speed rating from image EXIF data."""
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
            if exif:
                # 34855 is the standard EXIF tag for ISOSpeedRatings
                iso = exif.get(34855)
                if iso is not None:
                    return int(iso)
    except Exception as e:
        print(f"\nWarning: Could not read EXIF for {image_path.name}: {e}", file=sys.stderr)
    return None


FILENAME_PATTERN = re.compile(r"(\d{8})_(\d{6})")


def get_image_datetime(image_path: Path) -> datetime | None:
    """Extract datetime from filename or EXIF metadata."""
    # 1. Try parsing from the filename first (instant)
    match = FILENAME_PATTERN.search(image_path.name)
    if match:
        try:
            return datetime.strptime(f"{match.group(1)}_{match.group(2)}", "%Y%m%d_%H%M%S")
        except ValueError:
            pass

    # 2. Fallback to EXIF metadata (requires opening file)
    try:
        with Image.open(image_path) as img:
            exif = img._getexif()
            if exif:
                # 36867 is DateTimeOriginal, 306 is DateTime
                for tag in (36867, 306):
                    dt_str = exif.get(tag)
                    if dt_str:
                        return datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def main():
    """Parse CLI arguments, filter images, and compile the timelapse video."""
    parser = argparse.ArgumentParser(
        description="Compile a timelapse from a directory of photos, optionally filtering for daytime photos."
    )
    parser.add_argument("dir_path", type=str, help="Path to the directory containing source photos.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="timelapse.mp4",
        help="Path for the output video file (default: timelapse.mp4)",
    )
    parser.add_argument(
        "--daytime-only", action="store_true", help="Filter out night photos (keeps only photos where ISO < 800)"
    )
    parser.add_argument("--daily", action="store_true", help="Select only a single photo per calendar day.")
    parser.add_argument(
        "--target-hour",
        type=int,
        default=None,
        help="Target hour (0-23) to choose for the daily photo (default: 12 / noon). Requires --daily.",
    )
    parser.add_argument("--fps", type=int, default=24, help="Framerate of the output video (default: 24)")
    parser.add_argument(
        "--resolution",
        type=str,
        choices=["original", "4k", "1080p"],
        default="4k",
        help="Resolution to scale the output video to (default: 4k)",
    )
    parser.add_argument(
        "--crop-bar",
        action="store_true",
        help="Crop the camera info bar from the bottom of each frame.",
    )
    parser.add_argument(
        "--bar-height",
        type=int,
        default=DEFAULT_BAR_HEIGHT,
        help=f"Height in pixels of the bottom bar to crop (default: {DEFAULT_BAR_HEIGHT}). Requires --crop-bar.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run: list photos and build ffmpeg command without encoding."
    )

    args = parser.parse_args()

    if args.target_hour is not None and not args.daily:
        parser.error("--target-hour requires --daily.")

    if args.bar_height != DEFAULT_BAR_HEIGHT and not args.crop_bar:
        parser.error("--bar-height requires --crop-bar.")

    target_hour = args.target_hour if args.target_hour is not None else 12

    source_dir = Path(args.dir_path).resolve()
    if not source_dir.is_dir():
        print(f"Error: Directory '{source_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning '{source_dir}' for images...")
    extensions = {".jpg", ".jpeg", ".png"}
    all_files = sorted([p for p in source_dir.iterdir() if p.suffix.lower() in extensions and p.is_file()])

    if not all_files:
        print("No matching photos found in the source directory.", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(all_files)} total photos.")

    selected_files = []

    if args.daytime_only:
        print("Filtering for daytime photos (ISO < 800) using 16 threads...")
        # Use a thread pool to parallelize reading EXIF data from disk
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            # Submit all files to the thread pool
            future_to_path = {executor.submit(get_image_iso, path): path for path in all_files}

            for i, future in enumerate(concurrent.futures.as_completed(future_to_path), 1):
                file_path = future_to_path[future]
                try:
                    iso = future.result()
                    if iso is not None and iso < 800:
                        selected_files.append(file_path)
                except Exception as e:
                    print(f"\nError processing EXIF for {file_path.name}: {e}", file=sys.stderr)

                # Print progress indicator
                if i % 50 == 0 or i == len(all_files):
                    sys.stdout.write(f"\rChecked {i}/{len(all_files)} photos...")
                    sys.stdout.flush()
        print()  # New line after progress indicator

        # as_completed returns futures as they finish, which ruins chronological sorting.
        # We must re-sort the selected files alphabetically by their filenames to restore order.
        selected_files.sort(key=lambda p: p.name)
    else:
        selected_files = all_files

    if args.daily:
        print(f"Selecting one photo per day closest to {target_hour:02d}:00...")
        by_day = {}
        for file_path in selected_files:
            dt = get_image_datetime(file_path)
            if dt:
                d = dt.date()
                if d not in by_day:
                    by_day[d] = []
                by_day[d].append((file_path, dt))
            else:
                print(f"Warning: Could not determine date for {file_path.name}, skipping.")

        selected_files = []
        for d in sorted(by_day.keys()):
            day_photos = by_day[d]
            chosen = min(day_photos, key=lambda x: abs(x[1].hour - target_hour))
            selected_files.append(chosen[0])

    if not selected_files:
        print("No photos matched the filtering criteria.", file=sys.stderr)
        sys.exit(1)

    duration_sec = len(selected_files) / args.fps
    print(f"Selected {len(selected_files)} photos for the timelapse.")
    print(f"Expected video duration: {duration_sec:.1f} seconds (at {args.fps} FPS).")

    # Write paths to a unique concat file in the current directory
    # using tempfile.NamedTemporaryFile with delete=False so we keep it.
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="timelapse_files_", suffix=".txt", dir=".", delete=False, encoding="utf-8"
    ) as temp_file:
        concat_file_path = Path(temp_file.name).resolve()
        print(f"Writing file list to '{concat_file_path}'...")
        for file_path in selected_files:
            # Escape single quotes in path if any exist
            escaped_path = str(file_path).replace("'", "'\\''")
            temp_file.write(f"file '{escaped_path}'\n")

    # Build the ffmpeg command
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",  # Overwrite output files without asking
        "-f",
        "concat",  # Use concat demuxer
        "-safe",
        "0",  # Allow absolute paths in concat file
        "-r",
        str(args.fps),  # Input framerate
        "-i",
        str(concat_file_path),
        "-c:v",
        "libx264",  # Video codec
        "-pix_fmt",
        "yuv420p",  # Pixel format for compatibility
    ]

    # Build video filter chain (crop must come before scale)
    vf_filters = []
    if args.crop_bar:
        vf_filters.append(f"crop=iw:ih-{args.bar_height}:0:0")
    if args.resolution == "4k":
        vf_filters.append("scale=3840:-2")
    elif args.resolution == "1080p":
        vf_filters.append("scale=1920:-2")
    elif args.resolution == "original":
        vf_filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    if vf_filters:
        ffmpeg_cmd.extend(["-vf", ",".join(vf_filters)])

    # Output path
    ffmpeg_cmd.append(args.output)

    # Print the command
    print("\nffmpeg command built:")
    print(" ".join(ffmpeg_cmd))

    if args.dry_run:
        print("\nDry run completed. ffmpeg encoding skipped.")
        return

    print(f"\nRunning ffmpeg to encode video to '{args.output}'...")
    try:
        # Run ffmpeg synchronously, displaying output to terminal
        subprocess.run(ffmpeg_cmd, check=True)
        print(f"\nSuccess! Timelapse saved to '{args.output}'")
    except subprocess.CalledProcessError as e:
        print(f"\nError: ffmpeg failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except FileNotFoundError:
        print("\nError: ffmpeg is not installed or not in system PATH.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
