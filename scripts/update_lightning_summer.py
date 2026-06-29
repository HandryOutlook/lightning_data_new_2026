import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError


# ============================================================
# CONFIG
# ============================================================

OUTPUT_FILE = Path("lightning_data_2026_summer.json")

SOURCE_URLS = [
    "https://ukwx.duckdns.org/lightning/archive/uk/2026-06-25.json",
    "https://ukwx.duckdns.org/lightning/archive/uk/2026-06-26.json",
    "https://ukwx.duckdns.org/lightning/archive/uk/2026-06-27.json",
]

START_TIME = "2026-06-25T02:51:42Z"
END_TIME = "2026-06-27T10:05:39.461048Z"


# ============================================================
# TIME HELPERS
# ============================================================

def parse_iso_utc(value: str) -> datetime:
    """
    Parse an ISO 8601 UTC timestamp ending with Z.
    """
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def unix_to_datetime(value: int | float) -> datetime:
    """
    Convert UKWX Unix timestamp seconds to UTC datetime.
    """
    return datetime.fromtimestamp(value, tz=timezone.utc)


def unix_to_iso_utc(value: int | float) -> str:
    """
    Convert UKWX Unix timestamp seconds to ISO UTC string.
    UKWX timestamps are second precision, so output keeps seconds only.
    """
    return unix_to_datetime(value).strftime("%Y-%m-%dT%H:%M:%SZ")


# ============================================================
# LOCAL FILE HELPERS
# ============================================================

def load_existing_lightning(path: Path) -> list:
    """
    Load existing lightning data from the repo.

    Supports either:
    1. {"lightning_strikes": [...]}
    2. [...]
    """
    if not path.exists():
        print(f"{path} does not exist. Creating a new file.")
        return []

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if isinstance(data, dict):
        return data.get("lightning_strikes", [])

    if isinstance(data, list):
        return data

    raise ValueError(f"Unsupported JSON structure in {path}")


def save_lightning(path: Path, strikes: list) -> None:
    """
    Save in the repo's expected format.
    """
    output = {
        "lightning_strikes": strikes
    }

    with path.open("w", encoding="utf-8") as file:
        json.dump(output, file, indent=4, ensure_ascii=False)

    file_size = path.stat().st_size
    print(f"Saved {len(strikes)} strikes to {path} ({file_size:,} bytes).")


# ============================================================
# FETCH HELPERS
# ============================================================

def fetch_json(url: str):
    """
    Fetch JSON using Python standard library.
    No external dependencies required.
    """
    print(f"Fetching {url}")

    request = Request(
        url,
        headers={
            "User-Agent": "github-actions-lightning-fetcher"
        }
    )

    try:
        with urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)

    except HTTPError as error:
        print(f"HTTP error while fetching {url}: {error.code} {error.reason}")
        return None

    except URLError as error:
        print(f"URL error while fetching {url}: {error.reason}")
        return None

    except json.JSONDecodeError as error:
        print(f"Invalid JSON from {url}: {error}")
        return None


# ============================================================
# VALIDATION + CONVERSION
# ============================================================

def valid_existing_strike(strike: dict) -> bool:
    """
    Validate local lightning strike format:
    {
      "strike_time": "...Z",
      "coordinates": [lon, lat]
    }
    """
    if not isinstance(strike, dict):
        return False

    if "strike_time" not in strike:
        return False

    if "coordinates" not in strike:
        return False

    coordinates = strike["coordinates"]

    if not isinstance(coordinates, list):
        return False

    if len(coordinates) != 2:
        return False

    try:
        parse_iso_utc(strike["strike_time"])
        float(coordinates[0])
        float(coordinates[1])
    except Exception:
        return False

    return True


def valid_ukwx_point(point: dict) -> bool:
    """
    Validate UKWX point format:
    {
      "t": unix_seconds,
      "lat": latitude,
      "lon": longitude
    }
    """
    if not isinstance(point, dict):
        return False

    required_keys = ["t", "lat", "lon"]

    for key in required_keys:
        if key not in point:
            return False

    try:
        float(point["t"])
        float(point["lat"])
        float(point["lon"])
    except Exception:
        return False

    return True


def ukwx_point_to_lightning_strike(point: dict) -> dict:
    """
    Convert UKWX point into repo format.
    """
    return {
        "strike_time": unix_to_iso_utc(point["t"]),
        "coordinates": [
            float(point["lon"]),
            float(point["lat"])
        ]
    }


def strike_key(strike: dict) -> tuple:
    """
    Deduplication key using timestamp + coordinate pair.
    """
    return (
        strike["strike_time"],
        round(float(strike["coordinates"][0]), 6),
        round(float(strike["coordinates"][1]), 6)
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    start_dt = parse_iso_utc(START_TIME)
    end_dt = parse_iso_utc(END_TIME)

    print("Lightning Summer 2026 updater")
    print(f"Output file: {OUTPUT_FILE}")
    print(f"Start time: {START_TIME}")
    print(f"End time:   {END_TIME}")
    print()

    existing_strikes = load_existing_lightning(OUTPUT_FILE)

    existing_strikes = [
        strike for strike in existing_strikes
        if valid_existing_strike(strike)
    ]

    existing_keys = {
        strike_key(strike)
        for strike in existing_strikes
    }

    new_strikes = []

    for url in SOURCE_URLS:
        archive_data = fetch_json(url)

        if archive_data is None:
            print(f"Skipping {url} because it could not be loaded.")
            continue

        points = archive_data.get("points", [])

        if not isinstance(points, list):
            print(f"Skipping {url}: 'points' is not a list.")
            continue

        print(f"Found {len(points)} UKWX points in {url}")

        added_from_this_file = 0

        for point in points:
            if not valid_ukwx_point(point):
                continue

            point_dt = unix_to_datetime(point["t"])

            if not (start_dt <= point_dt <= end_dt):
                continue

            strike = ukwx_point_to_lightning_strike(point)
            key = strike_key(strike)

            if key in existing_keys:
                continue

            existing_keys.add(key)
            new_strikes.append(strike)
            added_from_this_file += 1

        print(f"Added {added_from_this_file} new strikes from this archive.")
        print()

    combined = existing_strikes + new_strikes

    combined.sort(
        key=lambda strike: parse_iso_utc(strike["strike_time"]),
        reverse=True
    )

    save_lightning(OUTPUT_FILE, combined)

    print()
    print("Update complete.")
    print(f"Existing valid strikes before update: {len(existing_strikes)}")
    print(f"New strikes added: {len(new_strikes)}")
    print(f"Total strikes now: {len(combined)}")


if __name__ == "__main__":
    main()
