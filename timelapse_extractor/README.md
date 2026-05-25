# GoPro Timelapse Extractor

A Python tool to extract "top of the hour" images and movies from GoPro trail cam source directories. It renames files based on their capture timestamp (ISO format) and organizes them into primary, extra, and movie directories.

## Features

- **Metadata-based**: Uses EXIF (JPG) and Hachoir (MP4) to extract actual capture times.
- **Top of the Hour Filter**: Automatically selects files captured in the first minute of each hour (`minute == 0`).
- **Smart Sorting**:
  - **Primary**: The first image of each hour (perfect for consistent timelapses).
  - **Extras**: Subsequent images from the same hour (kept "just in case").
  - **Movies**: All top-of-the-hour video captures.
- **Dry Run**: Preview all move and rename operations before they happen.
- **Collision Handling**: Automatically appends `_1`, `_2`, etc., if multiple files share the same timestamp.
- **Cross-Platform**: Works on macOS, Windows, and Linux.

## Requirements

This script uses `uv` for seamless dependency management.

- [uv](https://github.com/astral-sh/uv) installed on your system.
- Python 3.11+

## Usage

1. **Make the script executable:**
   ```bash
   chmod +x extract_timelapse.py
   ```

2. **Run a dry run (Recommended):**
   ```bash
   ./extract_timelapse.py \
     --source /path/to/gopro/files \
     --primary /path/to/dest/images/primary \
     --extra /path/to/dest/images/extras \
     --movies /path/to/dest/movies \
     --dry-run
   ```

3. **Perform the move:**
   Remove the `--dry-run` flag to execute the file moves.

## Command Line Options

| Option | Shorthand | Description |
| :--- | :--- | :--- |
| `--source` | `-s` | **Required.** Parent directory to scan recursively. |
| `--primary` | `-p` | **Required.** Target for the first JPG of each hour. |
| `--extra` | `-e` | **Required.** Target for additional JPGs from the top of the hour. |
| `--movies` | `-m` | **Required.** Target for top-of-hour MP4s. |
| `--dry-run` | | Report intended actions without moving files. |

## File Naming Convention

Files are renamed to `YYYYMMDD_HHMMSS.ext` based on their internal metadata. If a collision occurs at the destination, it becomes `YYYYMMDD_HHMMSS_1.ext`.
