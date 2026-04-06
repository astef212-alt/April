import json
import logging
from datetime import datetime

import garminconnect

logger = logging.getLogger(__name__)


class GarminGolfClient:
    """Thin wrapper around garminconnect for golf-specific data."""

    def __init__(self, email: str, password: str):
        self.client = garminconnect.Garmin(email, password)

    def login(self):
        self.client.login()

    def get_golf_activities(self, start: int = 0, limit: int = 100) -> list[dict]:
        """Return all golf activities, newest first."""
        activities = self.client.get_activities(start, limit)
        return [
            a for a in activities
            if a.get("activityType", {}).get("typeKey") == "golf"
        ]

    def get_activity_details(self, activity_id: str) -> dict:
        return self.client.get_activity_details(activity_id)

    def parse_round(self, activity: dict, details: dict) -> dict:
        """
        Normalise raw Garmin API data into a clean dict ready to persist.

        Garmin golf activities may carry data in several shapes depending on
        device model (Approach series vs. watch) and firmware.  This method
        is deliberately defensive – every field defaults to None when absent.
        """
        summary = activity.get("summaryDTO", activity)

        # ---- top-level round info ----------------------------------------
        raw_date = (
            activity.get("startTimeLocal")
            or activity.get("beginTimestamp")
            or summary.get("startTimeLocal")
        )
        try:
            date = datetime.strptime(raw_date[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            date = datetime.utcnow()

        course_name = (
            activity.get("activityName")
            or activity.get("locationName")
            or "Unknown Course"
        )

        duration = int(
            activity.get("duration")
            or summary.get("duration")
            or 0
        )

        # ---- golf-specific summary ----------------------------------------
        golf_summary = (
            details.get("golfSummary")
            or activity.get("golfSummary")
            or {}
        )

        total_score = _int(golf_summary.get("totalScore") or activity.get("averageHR"))  # fallback is wrong but safe
        total_score = _int(golf_summary.get("totalScore"))
        putts = _int(golf_summary.get("totalPutts"))
        fairways_hit = _int(golf_summary.get("fairwaysHit"))
        fairways_played = _int(golf_summary.get("fairwaysPlayed"))
        gir = _int(golf_summary.get("greensInRegulation"))
        holes_played = _int(golf_summary.get("holesPlayed")) or 18

        # ---- hole-by-hole scores ------------------------------------------
        raw_holes = (
            details.get("golfHoleScores")
            or activity.get("golfHoleScores")
            or []
        )
        holes = [_parse_hole(h) for h in raw_holes]

        return {
            "garmin_activity_id": str(activity.get("activityId")),
            "date": date,
            "course_name": course_name,
            "total_score": total_score,
            "holes_played": holes_played,
            "total_putts": putts,
            "fairways_hit": fairways_hit,
            "fairways_played": fairways_played,
            "greens_in_regulation": gir,
            "duration_seconds": duration,
            "raw_data": json.dumps({"activity": activity, "details": details}),
            "holes": holes,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("true", "1", "yes")


def _parse_hole(raw: dict) -> dict:
    shots_raw = raw.get("shots") or raw.get("golfShots") or []
    return {
        "hole_number": _int(raw.get("holeNumber") or raw.get("hole")),
        "par": _int(raw.get("par")),
        "score": _int(raw.get("strokes") or raw.get("score")),
        "putts": _int(raw.get("putts")),
        "fairway_hit": _bool(raw.get("fairwayHit") or raw.get("fairway")),
        "gir": _bool(raw.get("gir") or raw.get("greenInRegulation")),
        "drive_distance": _int(raw.get("driveDistance")),
        "shots": [_parse_shot(s, i + 1) for i, s in enumerate(shots_raw)],
    }


def _parse_shot(raw: dict, default_number: int) -> dict:
    return {
        "shot_number": _int(raw.get("shotNumber")) or default_number,
        "club": raw.get("club") or raw.get("clubType"),
        "distance_yards": _int(raw.get("distanceInYards") or raw.get("distance")),
        "start_lat": raw.get("startLat") or raw.get("lat"),
        "start_lon": raw.get("startLon") or raw.get("lon"),
        "end_lat": raw.get("endLat"),
        "end_lon": raw.get("endLon"),
    }
