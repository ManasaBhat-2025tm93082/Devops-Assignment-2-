from datetime import date, timedelta

import pytest

from app import PROGRAMS, calculate_bmi, calculate_calories, create_app, membership_state


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})
    return app.test_client()


def make_client(c, name="Ravi", **extra):
    payload = {"name": name, "program": "Fat Loss (FL)", "weight": 80, "height": 175}
    payload.update(extra)
    return c.post("/clients", json=payload)


# ---------- pure logic ----------
def test_calories_each_program():
    for name, p in PROGRAMS.items():
        assert calculate_calories(70, name) == int(70 * p["calorie_factor"])


def test_calories_invalid():
    with pytest.raises(ValueError):
        calculate_calories(70, "Nope")
    with pytest.raises(ValueError):
        calculate_calories(0, "Fat Loss (FL)")


@pytest.mark.parametrize("w,h,cat", [(50, 180, "Underweight"), (70, 175, "Normal"),
                                     (85, 175, "Overweight"), (110, 175, "Obese")])
def test_bmi_categories(w, h, cat):
    assert calculate_bmi(w, h)[1] == cat


def test_bmi_invalid():
    with pytest.raises(ValueError):
        calculate_bmi(70, 0)


def test_membership_state():
    assert membership_state("Active", None) == "Active"
    assert membership_state("Active", (date.today() + timedelta(days=5)).isoformat()) == "Active"
    assert membership_state("Active", "2000-01-01") == "Expired"
    assert membership_state("Suspended", None) == "Suspended"
    assert membership_state("Active", "garbage") == "Invalid date"


# ---------- basic endpoints ----------
def test_index_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").get_json() == {"status": "ok"}


def test_programs(client):
    assert len(client.get("/programs").get_json()["programs"]) == 3
    r = client.get("/programs/Muscle Gain (MG)")
    assert r.status_code == 200 and "Squat" in r.get_json()["workout"]
    assert client.get("/programs/Unknown").status_code == 404


def test_calories_endpoint(client):
    r = client.get("/calories?program=Muscle Gain (MG)&weight=70")
    assert r.get_json()["calories"] == 2450
    assert client.get("/calories?program=x&weight=70").status_code == 400
    assert client.get("/calories?program=Fat Loss (FL)&weight=abc").status_code == 400


def test_bmi_endpoint(client):
    assert client.get("/bmi?weight=70&height=175").get_json()["bmi"] == 22.9
    assert client.get("/bmi?weight=70").status_code == 400


# ---------- clients ----------
def test_add_and_get_client(client):
    r = make_client(client)
    assert r.status_code == 201 and r.get_json()["calories"] == 1760
    assert client.get("/clients/Ravi").get_json()["program"] == "Fat Loss (FL)"
    assert len(client.get("/clients").get_json()["clients"]) == 1


def test_add_client_validation(client):
    assert client.post("/clients", json={}).status_code == 400
    assert make_client(client, program="Bad").status_code == 400
    make_client(client)
    assert make_client(client).status_code == 409


def test_client_not_found(client):
    for path in ["/clients/x", "/clients/x/bmi", "/clients/x/membership",
                 "/clients/x/progress", "/clients/x/workouts"]:
        assert client.get(path).status_code == 404


def test_delete_client(client):
    make_client(client)
    assert client.delete("/clients/Ravi").status_code == 200
    assert client.delete("/clients/Ravi").status_code == 404


def test_client_bmi(client):
    make_client(client)
    assert client.get("/clients/Ravi/bmi").get_json()["category"] == "Overweight"
    client.post("/clients", json={"name": "NoData"})
    assert client.get("/clients/NoData/bmi").status_code == 400


def test_membership(client):
    make_client(client, membership_end="2000-01-01")
    assert client.get("/clients/Ravi/membership").get_json()["membership"] == "Expired"


# ---------- progress & workouts ----------
def test_progress(client):
    make_client(client)
    r = client.post("/clients/Ravi/progress", json={"adherence": 80, "week": "W1"})
    assert r.status_code == 201
    client.post("/clients/Ravi/progress", json={"adherence": 60, "week": "W2"})
    data = client.get("/clients/Ravi/progress").get_json()
    assert data["average_adherence"] == 70.0 and len(data["progress"]) == 2


def test_progress_validation(client):
    make_client(client)
    assert client.post("/clients/Ravi/progress", json={"adherence": 150}).status_code == 400
    assert client.post("/clients/Nobody/progress", json={"adherence": 50}).status_code == 404


def test_workouts(client):
    make_client(client)
    r = client.post("/clients/Ravi/workouts",
                    json={"workout_type": "Strength", "duration_min": 45, "notes": "PR"})
    assert r.status_code == 201
    w = client.get("/clients/Ravi/workouts").get_json()["workouts"]
    assert w[0]["workout_type"] == "Strength" and w[0]["duration_min"] == 45


def test_workout_validation(client):
    make_client(client)
    assert client.post("/clients/Ravi/workouts", json={"duration_min": 30}).status_code == 400
    assert client.post("/clients/Ravi/workouts",
                       json={"workout_type": "Cardio", "duration_min": -5}).status_code == 400
    assert client.post("/clients/Nobody/workouts",
                       json={"workout_type": "Cardio", "duration_min": 5}).status_code == 404


def test_ui_page(client):
    r = client.get("/")
    assert r.status_code == 200 and b"ACEest" in r.data


def test_api_info(client):
    assert client.get("/api").get_json()["status"] == "running"


def test_version_endpoint(client):
    data = client.get("/version").get_json()
    assert data["version"] and data["pod"]


def test_version_header_and_ui(client):
    r = client.get("/")
    assert r.headers["X-App-Version"]
    assert b"ACEest FUNCTIONAL FITNESS" in r.data
