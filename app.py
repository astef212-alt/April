import json
import os
import logging
from functools import wraps

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func

from database import db, Round, Hole, Shot
from garmin_client import GarminGolfClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///golf_shots.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "garmin_email" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def _get_client() -> GarminGolfClient:
    client = GarminGolfClient(session["garmin_email"], session["garmin_password"])
    client.login()
    return client


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    rounds = Round.query.order_by(Round.date.desc()).all()

    # Build chart data
    chart_data = _build_chart_data(rounds)

    # Aggregate stats
    stats = _aggregate_stats(rounds)

    return render_template("dashboard.html", rounds=rounds, chart_data=chart_data, stats=stats)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("login.html")
        try:
            client = GarminGolfClient(email, password)
            client.login()
            session["garmin_email"] = email
            session["garmin_password"] = password
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))
        except Exception as e:
            logger.error("Garmin login failed: %s", e)
            flash("Login failed – check your Garmin credentials.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/sync", methods=["POST"])
@login_required
def sync():
    """Fetch the latest golf rounds from Garmin Connect and store them."""
    try:
        client = _get_client()
        activities = client.get_golf_activities(start=0, limit=100)
        added = 0
        skipped = 0
        for activity in activities:
            activity_id = str(activity.get("activityId"))
            if Round.query.filter_by(garmin_activity_id=activity_id).first():
                skipped += 1
                continue
            details = client.get_activity_details(activity_id)
            parsed = client.parse_round(activity, details)
            _persist_round(parsed)
            added += 1

        db.session.commit()
        flash(f"Sync complete: {added} new round(s) added, {skipped} already up to date.", "success")
    except Exception as e:
        db.session.rollback()
        logger.error("Sync error: %s", e, exc_info=True)
        flash(f"Sync failed: {e}", "error")

    return redirect(url_for("index"))


@app.route("/rounds/<int:round_id>")
@login_required
def round_detail(round_id):
    r = Round.query.get_or_404(round_id)
    return render_template("round_detail.html", round=r)


@app.route("/api/stats")
@login_required
def api_stats():
    rounds = Round.query.order_by(Round.date.asc()).all()
    return jsonify(_build_chart_data(rounds))


@app.route("/api/rounds")
@login_required
def api_rounds():
    rounds = Round.query.order_by(Round.date.desc()).all()
    return jsonify([r.to_dict() for r in rounds])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _persist_round(parsed: dict):
    holes_data = parsed.pop("holes", [])
    r = Round(**parsed)
    db.session.add(r)
    db.session.flush()  # get r.id

    for h_data in holes_data:
        shots_data = h_data.pop("shots", [])
        hole = Hole(round_id=r.id, **h_data)
        db.session.add(hole)
        db.session.flush()

        for s_data in shots_data:
            shot = Shot(hole_id=hole.id, **s_data)
            db.session.add(shot)


def _build_chart_data(rounds: list[Round]) -> dict:
    labels = [r.date.strftime("%b %d") for r in rounds]
    scores = [r.total_score for r in rounds]
    putts = [r.total_putts for r in rounds]
    fairway_pcts = [r.fairway_pct for r in rounds]
    gir_pcts = [r.gir_pct for r in rounds]
    return {
        "labels": labels,
        "scores": scores,
        "putts": putts,
        "fairway_pcts": fairway_pcts,
        "gir_pcts": gir_pcts,
    }


def _aggregate_stats(rounds: list[Round]) -> dict:
    if not rounds:
        return {}

    valid_scores = [r.total_score for r in rounds if r.total_score]
    valid_putts = [r.total_putts for r in rounds if r.total_putts]
    valid_fw = [r.fairway_pct for r in rounds if r.fairway_pct is not None]
    valid_gir = [r.gir_pct for r in rounds if r.gir_pct is not None]

    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else None

    return {
        "rounds_played": len(rounds),
        "avg_score": avg(valid_scores),
        "best_score": min(valid_scores) if valid_scores else None,
        "avg_putts": avg(valid_putts),
        "avg_fairway_pct": avg(valid_fw),
        "avg_gir_pct": avg(valid_gir),
    }


if __name__ == "__main__":
    app.run(debug=True, port=5000)
