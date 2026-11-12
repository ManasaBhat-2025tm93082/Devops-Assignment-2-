"""ACEest Fitness & Gym - Flask web application.

Web/API port of the original Tkinter desktop versions (see legacy_versions/).
Provides program templates, calorie estimation, BMI, client management,
weekly progress tracking, workout logging and membership checks.
"""
import os
import socket
import sqlite3
from datetime import date

from flask import Flask, g, jsonify, render_template, request

APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")

PROGRAMS = {
    "Fat Loss (FL)": {
        "workout": "Mon: Back Squat 5x5 + Core\nTue: EMOM 20min Assault Bike\n"
                   "Wed: Bench Press + 21-15-9\nThu: Deadlift + Box Jumps\n"
                   "Fri: Zone 2 Cardio 30min",
        "diet": "Breakfast: Egg Whites + Oats\nLunch: Grilled Chicken + Brown Rice\n"
                "Dinner: Fish Curry + Millet Roti\nTarget: ~2000 kcal",
        "calorie_factor": 22,
    },
    "Muscle Gain (MG)": {
        "workout": "Mon: Squat 5x5\nTue: Bench 5x5\nWed: Deadlift 4x6\n"
                   "Thu: Front Squat 4x8\nFri: Incline Press 4x10\nSat: Barbell Rows 4x10",
        "diet": "Breakfast: Eggs + Peanut Butter Oats\nLunch: Chicken Biryani\n"
                "Dinner: Mutton Curry + Rice\nTarget: ~3200 kcal",
        "calorie_factor": 35,
    },
    "Beginner (BG)": {
        "workout": "Full Body Circuit:\n- Air Squats\n- Ring Rows\n- Push-ups\n"
                   "Focus: Technique & Consistency",
        "diet": "Balanced Tamil Meals\nIdli / Dosa / Rice + Dal\nProtein Target: 120g/day",
        "calorie_factor": 26,
    },
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    age INTEGER, height REAL, weight REAL,
    program TEXT, calories INTEGER,
    membership_status TEXT DEFAULT 'Active',
    membership_end TEXT
);
CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL, week TEXT NOT NULL, adherence INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL, date TEXT NOT NULL,
    workout_type TEXT NOT NULL, duration_min INTEGER NOT NULL, notes TEXT
);
"""


# ---------- Pure business logic (easy to unit test) ----------
def calculate_calories(weight_kg, program):
    """Estimated daily calories = weight * program calorie factor."""
    if program not in PROGRAMS:
        raise ValueError(f"Unknown program: {program}")
    if weight_kg is None or weight_kg <= 0:
        raise ValueError("Weight must be greater than 0")
    return int(weight_kg * PROGRAMS[program]["calorie_factor"])


def calculate_bmi(weight_kg, height_cm):
    """Return (bmi, category)."""
    if weight_kg <= 0 or height_cm <= 0:
        raise ValueError("Weight and height must be greater than 0")
    h_m = height_cm / 100
    bmi = round(weight_kg / (h_m * h_m), 1)
    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"
    return bmi, category


def membership_state(status, end_date):
    """Return 'Active', 'Expired' or the stored status."""
    if status != "Active":
        return status or "Unknown"
    if end_date:
        try:
            if date.fromisoformat(end_date) < date.today():
                return "Expired"
        except ValueError:
            return "Invalid date"
    return "Active"


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["DATABASE"] = os.environ.get("ACEEST_DB", "aceest_fitness.db")
    if test_config:
        app.config.update(test_config)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        get_db().executescript(SCHEMA)

    def error(msg, code=400):
        return jsonify({"error": msg}), code

    def client_or_none(name):
        return get_db().execute("SELECT * FROM clients WHERE name=?", (name,)).fetchone()

    # ---------- Routes ----------
    @app.after_request
    def add_version_header(response):
        response.headers["X-App-Version"] = APP_VERSION
        return response

    @app.get("/")
    def index():
        return render_template("index.html", version=APP_VERSION)

    @app.get("/version")
    def version():
        return jsonify({"version": APP_VERSION, "pod": socket.gethostname()})

    @app.get("/api")
    def api_info():
        return jsonify({"app": "ACEest Fitness & Gym", "status": "running",
                        "endpoints": ["/health", "/programs", "/clients"]})

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/programs")
    def list_programs():
        return jsonify({"programs": list(PROGRAMS.keys())})

    @app.get("/programs/<name>")
    def get_program(name):
        if name not in PROGRAMS:
            return error("Program not found", 404)
        p = PROGRAMS[name]
        return jsonify({"name": name, "workout": p["workout"], "diet": p["diet"],
                        "calorie_factor": p["calorie_factor"]})

    @app.get("/calories")
    def calories():
        program = request.args.get("program", "")
        try:
            weight = float(request.args.get("weight", ""))
            return jsonify({"program": program,
                            "calories": calculate_calories(weight, program)})
        except ValueError as exc:
            return error(str(exc))

    @app.get("/bmi")
    def bmi():
        try:
            value, category = calculate_bmi(float(request.args.get("weight", "")),
                                            float(request.args.get("height", "")))
            return jsonify({"bmi": value, "category": category})
        except ValueError as exc:
            return error(str(exc))

    @app.post("/clients")
    def add_client():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        program = data.get("program")
        if not name:
            return error("Client name is required")
        if program and program not in PROGRAMS:
            return error("Unknown program")
        if client_or_none(name):
            return error("Client already exists", 409)
        cal = None
        weight = data.get("weight")
        if program and weight:
            try:
                cal = calculate_calories(float(weight), program)
            except ValueError as exc:
                return error(str(exc))
        db = get_db()
        db.execute(
            "INSERT INTO clients (name,age,height,weight,program,calories,membership_end)"
            " VALUES (?,?,?,?,?,?,?)",
            (name, data.get("age"), data.get("height"), weight, program, cal,
             data.get("membership_end")))
        db.commit()
        return jsonify({"message": f"Client {name} saved", "calories": cal}), 201

    @app.get("/clients")
    def list_clients():
        rows = get_db().execute("SELECT * FROM clients ORDER BY name").fetchall()
        return jsonify({"clients": [dict(r) for r in rows]})

    @app.get("/clients/<name>")
    def get_client(name):
        row = client_or_none(name)
        if not row:
            return error("Client not found", 404)
        return jsonify(dict(row))

    @app.delete("/clients/<name>")
    def delete_client(name):
        if not client_or_none(name):
            return error("Client not found", 404)
        db = get_db()
        db.execute("DELETE FROM clients WHERE name=?", (name,))
        db.execute("DELETE FROM progress WHERE client_name=?", (name,))
        db.execute("DELETE FROM workouts WHERE client_name=?", (name,))
        db.commit()
        return jsonify({"message": f"Client {name} deleted"})

    @app.get("/clients/<name>/bmi")
    def client_bmi(name):
        row = client_or_none(name)
        if not row:
            return error("Client not found", 404)
        if not row["weight"] or not row["height"]:
            return error("Client needs weight and height for BMI")
        value, category = calculate_bmi(row["weight"], row["height"])
        return jsonify({"client": name, "bmi": value, "category": category})

    @app.get("/clients/<name>/membership")
    def client_membership(name):
        row = client_or_none(name)
        if not row:
            return error("Client not found", 404)
        return jsonify({"client": name,
                        "membership": membership_state(row["membership_status"],
                                                       row["membership_end"]),
                        "membership_end": row["membership_end"]})

    @app.post("/clients/<name>/progress")
    def add_progress(name):
        if not client_or_none(name):
            return error("Client not found", 404)
        data = request.get_json(silent=True) or {}
        adherence = data.get("adherence")
        if not isinstance(adherence, int) or not 0 <= adherence <= 100:
            return error("Adherence must be an integer between 0 and 100")
        week = data.get("week") or date.today().strftime("%Y-W%W")
        db = get_db()
        db.execute("INSERT INTO progress (client_name,week,adherence) VALUES (?,?,?)",
                   (name, week, adherence))
        db.commit()
        return jsonify({"message": "Progress saved", "week": week}), 201

    @app.get("/clients/<name>/progress")
    def get_progress(name):
        if not client_or_none(name):
            return error("Client not found", 404)
        rows = get_db().execute(
            "SELECT week, adherence FROM progress WHERE client_name=? ORDER BY id",
            (name,)).fetchall()
        items = [dict(r) for r in rows]
        avg = round(sum(i["adherence"] for i in items) / len(items), 1) if items else 0
        return jsonify({"client": name, "progress": items, "average_adherence": avg})

    @app.post("/clients/<name>/workouts")
    def add_workout(name):
        if not client_or_none(name):
            return error("Client not found", 404)
        data = request.get_json(silent=True) or {}
        wtype = (data.get("workout_type") or "").strip()
        duration = data.get("duration_min")
        if not wtype:
            return error("workout_type is required")
        if not isinstance(duration, int) or duration <= 0:
            return error("duration_min must be a positive integer")
        db = get_db()
        db.execute("INSERT INTO workouts (client_name,date,workout_type,duration_min,notes)"
                   " VALUES (?,?,?,?,?)",
                   (name, data.get("date") or date.today().isoformat(), wtype,
                    duration, data.get("notes", "")))
        db.commit()
        return jsonify({"message": "Workout logged"}), 201

    @app.get("/clients/<name>/workouts")
    def get_workouts(name):
        if not client_or_none(name):
            return error("Client not found", 404)
        rows = get_db().execute(
            "SELECT date, workout_type, duration_min, notes FROM workouts"
            " WHERE client_name=? ORDER BY date DESC, id DESC", (name,)).fetchall()
        return jsonify({"client": name, "workouts": [dict(r) for r in rows]})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
