# ruff: noqa: D100, D103, D200
# mypy: disable-error-code="assignment,attr-defined,arg-type,operator,return-value"
import csv
import random
from collections import defaultdict
from datetime import date, datetime
from fractions import Fraction

CSV_FILE = "/Volumes/media/20260103-trailcam_offload_full/photos_exif.csv"
PICS_PATH = "/Volumes/media/20260103-trailcam_offload_full"

ISO_DAY_MAX = 800  # day/night split
USE_RANDOM = True  # False = pick "best" instead
RANDOM_SEED = 42  # reproducible randomness

# Keep images ON or AFTER this timestamp (ISO format)
CUTOFF_TIMESTAMP = "2025-05-01T00:00:00"

# Camera was moved roughly June 13 → July 10
# Exclude with a 1-day safety buffer on each side
BLACKOUT_START = date(2025, 6, 12)  # June 13 minus 1 day
BLACKOUT_END = date(2025, 7, 11)  # July 10 plus 1 day

EXCLUDED_FILES = {
    "DSCF0573.JPG",
}


def is_in_blackout(d: date) -> bool:
    return BLACKOUT_START <= d <= BLACKOUT_END


def parse_exposure(exposure_str: str) -> float:
    """Convert EXIF exposure like '1/30' or '0.005' to seconds."""
    if not exposure_str:
        return float("inf")

    try:
        return float(Fraction(exposure_str))
    except Exception:
        return float("inf")


# Load CSV
records = []

with open(CSV_FILE, newline="") as f:
    reader = csv.reader(f)
    for row in reader:
        (
            path,
            ts,
            iso,
            exposure,
            light_value,
            brightness,
            flash,
            image_uid,
        ) = row

        dt = datetime.fromisoformat(ts)
        iso = int(iso)
        exposure_sec = parse_exposure(exposure)
        light_value = float(light_value) if light_value else None

        records.append(
            {
                "path": path,
                "datetime": dt,
                "date": dt.date(),
                "iso": iso,
                "exposure": exposure_sec,
                "light_value": light_value,
                "uid": image_uid,
            }
        )

print(f"Loaded {len(records)} records")

records = [r for r in records if r["path"].split("/")[-1] not in EXCLUDED_FILES]

before = len(records)
records = [r for r in records if not is_in_blackout(r["date"])]
after = len(records)

print(f"Removed {before - after} records due to camera-move blackout")

if CUTOFF_TIMESTAMP:
    cutoff_dt = datetime.fromisoformat(CUTOFF_TIMESTAMP)
    records = [r for r in records if r["datetime"] >= cutoff_dt]

print(f"Records after cutoff: {len(records)}")

# Filter daytime images
daytime = [r for r in records if r["iso"] < ISO_DAY_MAX]
print(f"Daytime images: {len(daytime)}")

# Group by calendar day
by_day = defaultdict(list)
for r in daytime:
    by_day[r["date"]].append(r)

print(f"Days with daytime images: {len(by_day)}")

# Select one image per day
random.seed(RANDOM_SEED)
selected = []

for day, imgs in sorted(by_day.items()):
    if USE_RANDOM:
        chosen = random.choice(imgs)
    else:
        # "Best" = brightest (highest LightValue),
        # tie-breaker: shortest exposure
        chosen = max(
            imgs,
            key=lambda r: (
                r["light_value"] if r["light_value"] is not None else -999,
                -r["exposure"],
            ),
        )

    selected.append(chosen)

print(f"Selected {len(selected)} images (1 per day)")

# Output results
for r in selected[:10]:
    print(r["datetime"].isoformat(), r["path"])

# # Optional: write file list for ffmpeg concat
# with open("timelapse_files.txt", "w") as f:
#     for r in selected:
#         f.write(f"file '{r['path']}'\n")

# print("Wrote timelapse_files.txt")

# Ensure chronological order (extra safety)
selected.sort(key=lambda r: r["datetime"])

# Write CSV for verification
with open("timelapse_selected.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "path"])
    for r in selected:
        writer.writerow([r["datetime"].isoformat(), r["path"]])

print("Wrote timelapse_selected.csv")

# (Optional) also keep ffmpeg file list
with open("timelapse_files.txt", "w") as f:
    for r in selected:
        f.write(f"file '{PICS_PATH}/{r['path']}'\n")
