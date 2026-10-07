from flask import Flask, jsonify, render_template_string
from threading import Lock, Thread, Condition
import time
import board
import adafruit_dht
from gpiozero import MotionSensor, DistanceSensor

app = Flask(__name__)

# Mutex for sensor access
mutex = Lock()

# Separate lock for dashboard data
data_lock = Lock()

# Controls the order in which sensor threads get the mutex
turn_condition = Condition()
turn = 0

data = {
    "temperature": None,
    "humidity": None,
    "motion": False,
    "distance": None,
    "mutex_owner": "Waiting..."
}

# Sensors
dht = adafruit_dht.DHT11(board.D4, use_pulseio=False)
pir = MotionSensor(17)
ultrasonic = DistanceSensor(echo=24, trigger=23, max_distance=2)


# ---------------- DHT11 ----------------

def dht_read():
    try:
        temperature = dht.temperature
        humidity = dht.humidity

        with data_lock:
            if temperature is not None:
                data["temperature"] = temperature

            if humidity is not None:
                data["humidity"] = humidity

    except Exception as e:
        print("DHT11 error:", e)


# ---------------- PIR ----------------

def pir_read():
    try:
        motion = pir.is_active

        with data_lock:
            data["motion"] = motion

    except Exception as e:
        print("PIR error:", e)


# ---------------- Ultrasonic ----------------

def ultrasonic_read():
    try:
        distance = ultrasonic.distance * 100

        with data_lock:
            data["distance"] = round(distance, 1)

    except Exception as e:
        print("Ultrasonic error:", e)


# ---------------- Sensor Worker ----------------

def sensor_worker(index, name, read_function):

    global turn

    while True:

        # Wait for this sensor's turn
        with turn_condition:

            while turn != index:
                turn_condition.wait()

        try:

            # Enter mutex
            with mutex:

                # Show who currently owns the mutex
                with data_lock:
                    data["mutex_owner"] = name

                print("MUTEX LOCKED BY:", name)

                # Read the sensor
                read_function()

                # Keep ownership visible on dashboard
                time.sleep(1.0)

        finally:

            # Give mutex turn to next sensor
            with turn_condition:
                turn = (turn + 1) % 3
                turn_condition.notify_all()

            print("MUTEX RELEASED:", name)

        time.sleep(0.1)


# ---------------- Dashboard ----------------

HTML = """
<!DOCTYPE html>
<html>

<head>

    <title>Raspberry Pi Mutex Dashboard</title>

    <meta http-equiv="refresh" content="1">

    <style>

        body {
            font-family: Arial, sans-serif;
            background: #f4f6f8;
            margin: 0;
            padding: 30px;
            text-align: center;
        }

        h1 {
            color: #172554;
            margin-bottom: 25px;
        }

        .mutex-box {
            background: black;
            color: white;
            padding: 25px;
            border-radius: 15px;
            margin: 0 auto 30px auto;
            max-width: 700px;
            font-size: 28px;
            font-weight: bold;
        }

        .cards {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            max-width: 900px;
            margin: auto;
        }

        .card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }

        .card h2 {
            margin-top: 0;
        }

        .value {
            font-size: 35px;
            font-weight: bold;
        }

        .temp {
            border-top: 8px solid orange;
        }

        .humidity {
            border-top: 8px solid cyan;
        }

        .motion {
            border-top: 8px solid green;
        }

        .distance {
            border-top: 8px solid purple;
        }

        footer {
            margin-top: 30px;
            color: #555;
        }

    </style>

</head>

<body>

    <h1>🔒 Raspberry Pi Mutex Sensor Dashboard</h1>

    <div class="mutex-box">
        🔒 MUTEX OWNER<br><br>
        {{ data["mutex_owner"] }}
    </div>

    <div class="cards">

        <div class="card temp">
            <h2>🌡️ Temperature</h2>
            <div class="value">
                {{ data["temperature"] }} °C
            </div>
        </div>

        <div class="card humidity">
            <h2>💧 Humidity</h2>
            <div class="value">
                {{ data["humidity"] }} %
            </div>
        </div>

        <div class="card motion">
            <h2>🚶 Motion</h2>
            <div class="value">
                {% if data["motion"] %}
                    DETECTED
                {% else %}
                    NOT DETECTED
                {% endif %}
            </div>
        </div>

        <div class="card distance">
            <h2>📏 Distance</h2>
            <div class="value">
                {{ data["distance"] }} cm
            </div>
        </div>

    </div>

    <footer>
        Raspberry Pi 4 | Mutex Synchronization Project
    </footer>

</body>

</html>
"""


@app.route("/")
def dashboard():

    with data_lock:
        current_data = data.copy()

    return render_template_string(HTML, data=current_data)


@app.route("/api/data")
def api_data():

    with data_lock:
        current_data = data.copy()

    return jsonify(current_data)


# ---------------- Start Program ----------------

if __name__ == "__main__":

    # Three separate sensor threads
    Thread(
        target=sensor_worker,
        args=(0, "DHT11 Thread", dht_read),
        daemon=True
    ).start()

    Thread(
        target=sensor_worker,
        args=(1, "PIR Thread", pir_read),
        daemon=True
    ).start()

    Thread(
        target=sensor_worker,
        args=(2, "Ultrasonic Thread", ultrasonic_read),
        daemon=True
    ).start()

    print("Starting Mutex Sensor Dashboard...")
    print("Order: DHT11 → PIR → Ultrasonic")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )