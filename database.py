from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Round(db.Model):
    __tablename__ = "rounds"

    id = db.Column(db.Integer, primary_key=True)
    garmin_activity_id = db.Column(db.String(64), unique=True, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    course_name = db.Column(db.String(256))
    total_score = db.Column(db.Integer)
    holes_played = db.Column(db.Integer, default=18)
    total_putts = db.Column(db.Integer)
    fairways_hit = db.Column(db.Integer)
    fairways_played = db.Column(db.Integer)
    greens_in_regulation = db.Column(db.Integer)
    duration_seconds = db.Column(db.Integer)
    raw_data = db.Column(db.Text)  # JSON blob of full API response

    holes = db.relationship("Hole", back_populates="round", cascade="all, delete-orphan", order_by="Hole.hole_number")

    @property
    def fairway_pct(self):
        if self.fairways_played and self.fairways_played > 0:
            return round(100 * self.fairways_hit / self.fairways_played, 1)
        return None

    @property
    def gir_pct(self):
        if self.holes_played and self.holes_played > 0:
            return round(100 * self.greens_in_regulation / self.holes_played, 1)
        return None

    @property
    def putts_per_hole(self):
        if self.total_putts and self.holes_played and self.holes_played > 0:
            return round(self.total_putts / self.holes_played, 2)
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "garmin_activity_id": self.garmin_activity_id,
            "date": self.date.isoformat(),
            "course_name": self.course_name,
            "total_score": self.total_score,
            "holes_played": self.holes_played,
            "total_putts": self.total_putts,
            "fairways_hit": self.fairways_hit,
            "fairways_played": self.fairways_played,
            "greens_in_regulation": self.greens_in_regulation,
            "fairway_pct": self.fairway_pct,
            "gir_pct": self.gir_pct,
            "putts_per_hole": self.putts_per_hole,
            "duration_seconds": self.duration_seconds,
        }


class Hole(db.Model):
    __tablename__ = "holes"

    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    hole_number = db.Column(db.Integer, nullable=False)
    par = db.Column(db.Integer)
    score = db.Column(db.Integer)
    putts = db.Column(db.Integer)
    fairway_hit = db.Column(db.Boolean)
    gir = db.Column(db.Boolean)
    drive_distance = db.Column(db.Integer)  # yards

    round = db.relationship("Round", back_populates="holes")
    shots = db.relationship("Shot", back_populates="hole", cascade="all, delete-orphan", order_by="Shot.shot_number")

    @property
    def score_to_par(self):
        if self.score is not None and self.par is not None:
            return self.score - self.par
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "hole_number": self.hole_number,
            "par": self.par,
            "score": self.score,
            "score_to_par": self.score_to_par,
            "putts": self.putts,
            "fairway_hit": self.fairway_hit,
            "gir": self.gir,
            "drive_distance": self.drive_distance,
            "shots": [s.to_dict() for s in self.shots],
        }


class Shot(db.Model):
    __tablename__ = "shots"

    id = db.Column(db.Integer, primary_key=True)
    hole_id = db.Column(db.Integer, db.ForeignKey("holes.id"), nullable=False)
    shot_number = db.Column(db.Integer, nullable=False)
    club = db.Column(db.String(64))
    distance_yards = db.Column(db.Integer)
    start_lat = db.Column(db.Float)
    start_lon = db.Column(db.Float)
    end_lat = db.Column(db.Float)
    end_lon = db.Column(db.Float)

    hole = db.relationship("Hole", back_populates="shots")

    def to_dict(self):
        return {
            "id": self.id,
            "shot_number": self.shot_number,
            "club": self.club,
            "distance_yards": self.distance_yards,
            "start_lat": self.start_lat,
            "start_lon": self.start_lon,
            "end_lat": self.end_lat,
            "end_lon": self.end_lon,
        }
