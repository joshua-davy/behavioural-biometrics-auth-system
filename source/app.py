from cryptography.fernet import Fernet
import hashlib,json,os,random,time,csv,secrets

from io import StringIO
from flask import Flask, render_template, request, redirect, session, Response
from database import get_db, init_db
from graphical_handler import animal_from_index, hash_graphical_secret, graphical_match, valid_selection
from keystroke_handler import KeystrokeHandler
from mouse_handler import parse_samples, valid_samples, valid_sample, build_profile, mouse_statsRange

# toggle switch for demo, this will remain true for final submission
# this encrypts sensitive values before they are stored and decrypted when read back
# applies to the user profile data in DB, users table
ENCRYPT_DB_FIELDS = True
FERNET_KEY = b'9-EmUwjZoK9GlbApLPThUo9i7dUwhgsOcQg3V2yQ-og='
fernet_cipher = Fernet(FERNET_KEY)

### have added these in with encrypt switch, when encrypt off for demo
# all sensitive values will be displayed , when on , they will be encrypted
# used at reg and after login
def encrypt_value(value):
    if value is None:
        return None
    if not ENCRYPT_DB_FIELDS:
        return str(value)
    return fernet_cipher.encrypt(str(value).encode()).decode()

# decrypts when needed for reading then will be encrypted
# will be used for comparison to get the values for reading
def decrypt_value(value):
    if value is None:
        return None
    if not ENCRYPT_DB_FIELDS:
        return value
    return fernet_cipher.decrypt(value.encode()).decode()

def decrypt_float(value):
    decrypted = decrypt_value(value)
    if decrypted is None or decrypted == "":
        return None
    return float(decrypted)

def decrypt_json(value):
    decrypted = decrypt_value(value)
    if decrypted is None or decrypted == "":
        return None
    return json.loads(decrypted)


# Initialise flask app, key enables session storage
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "jd534")

# These pangrams will be cycled, providing the fixed phrase section
# Registration and login use in build_prompt

PANGRAMS = [
    "the quick brown fox jumps over the lazy dog",
    "pack my box with five dozen liquor jugs",
    "how vexingly quick daft zebras jump",
    "bright vixens jump dozy fowl quack",
    "two driven jocks help fax my big quiz",
    "the five boxing wizards jump quickly",
]

LOGIN_AVG_Z_THRESHOLD = 0.40
LOGIN_MAX_Z_THRESHOLD = 0.60

MOUSE_AVG_Z_THRESHOLD = 1.20
MOUSE_MAX_Z_THRESHOLD = 1.80


# Cycles through pangrams and supports build_login_prompt()
# which combines pangram and coverage
def next_pangram(exclude=None):
    choices = [p for p in PANGRAMS if p != exclude]
    if not choices:
        choices = PANGRAMS[:]
    return random.choice(choices)


# Strips and normalises text
def normalise_text(s):
    if s is None:
        return ""
    return " ".join(s.lower().strip().split())

# May update this to more common word patterns but this seems to work fine.
# 4 words total
# Simply chooses either 4 5 or 6 length for string, then loops for i in that range
# if i is mod 2 then Consonant , then next is vowel so B,A,C,E,D etc etc
# removed lesser used consonants as they just disrupt flow
def keyCoverageGen(num_words=4) -> str:
    consonants = "bcdfghjklmnprstvwy"
    vowels = "aeiou"

# simply goes V,C,V,C for word creation
    def create_word():
        length = random.choice([4, 5, 6])
        word = ""
        for i in range(length):
            if i % 2 == 0:
                word += random.choice(consonants)
            else:
                word += random.choice(vowels)
        return word
    return " ".join(create_word() for _ in range(num_words))

# Login prompt is built from half of a pangram and then a coverage phrase which uses more
# natural vowel/consonants mix-ups, typing task is short while making sure user doesn't get used
# to the prompts.
def build_login_prompt(pangram, coverage, pangram_words=4, coverage_words=3):
    p_words = pangram.split()[:pangram_words]
    c_words = coverage.split()[:coverage_words]
    return " ".join(p_words + c_words)

# A round up for debug, contains both metrics from both sections of the register
# Averages each individual metric and combines into one session profile
def combine_metrics(metrics_pangram, metrics_coverage):
    return {
        "avg_dwell_ms": round((metrics_pangram["avg_dwell_ms"] + metrics_coverage["avg_dwell_ms"]) / 2, 2),
        "std_dwell_ms": round((metrics_pangram["std_dwell_ms"] + metrics_coverage["std_dwell_ms"]) / 2, 2),
        "avg_flight_ms": round((metrics_pangram["avg_flight_ms"] + metrics_coverage["avg_flight_ms"]) / 2, 2),
        "std_flight_ms": round((metrics_pangram["std_flight_ms"] + metrics_coverage["std_flight_ms"]) / 2, 2),
        "avg_latency_ms": round((metrics_pangram["avg_latency_ms"] + metrics_coverage["avg_latency_ms"]) / 2, 2),
        "std_latency_ms": round((metrics_pangram["std_latency_ms"] + metrics_coverage["std_latency_ms"]) / 2, 2),
        "avg_interval_ms": round((metrics_pangram["avg_interval_ms"] + metrics_coverage["avg_interval_ms"]) / 2, 2),
        "std_interval_ms": round((metrics_pangram["std_interval_ms"] + metrics_coverage["std_interval_ms"]) / 2, 2),
    }

# Core calculation for keystrokes, compares the keystroke profile at login with the stored profile  using "Z SCORE"
# Smaller the z score means that the login timings are quite close to the registered timings
def stats_range(stored_profile, login_profile, epsilon=1e-6):
    fields = ["avg_dwell_ms", "avg_flight_ms", "avg_latency_ms", "avg_interval_ms"]
    z_scores = {}
    z_values = []

    for field in fields:
        mu = stored_profile[field]
        x = login_profile[field]
        std_field = field.replace("avg", "std")
        # Applies min standard dev, so low variance doenst
        # disrupt extreme z score values at login
        sigma = max(stored_profile.get(std_field, 0.0), 5.0)

        # x=raw , u=mean
        z = abs(x - mu) / (sigma + epsilon)

        z_scores[field] = round(z, 3)
        z_values.append(z)

    avg_z = sum(z_values) / len(z_values) if z_values else 999.0
    max_z = max(z_values) if z_values else 999.0
    # Similarity Score is used for evaluation interpretaion
    # higher = closer to stored profile
    similarity = 1 / (1 + avg_z)

    return round(avg_z, 3), round(max_z, 3), round(similarity, 3), z_scores

# creates the registration code shown to the user after registration
# used in main_register() after mouse registration is complete
# checked later in main_profile() before allowing full re-enrolment
def generate_registration_code():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    parts = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
    return "-".join(parts)

# hashes the registration code before saving it
def hash_registration_code(code):
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()

# builds a backup code from the current stored user profile
# combines keystroke, graphical, and mouse profile data into one hash
# used in main_profile() when the user generates a backup code
def backupCode(keystroke_profile, graphical_hash, mouse_profile):
    combined_text = (
        str(keystroke_profile) +
        str(graphical_hash) +
        str(mouse_profile)
    )
    return hashlib.sha256(combined_text.encode()).hexdigest()

@app.route("/export-combined-attempts")
def export_combined_attempts():
    db = get_db()
    rows = db.execute("""
        SELECT *
        FROM combined_attempts
        ORDER BY id DESC
    """).fetchall()
    db.close()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "id",
        "username",
        "is_impostor",
        "keystroke_result",
        "graphical_result",
        "mouse_result",
        "final_result",
        "login_time_seconds",
        "keystroke_time",
        "graphical_time",
        "mouse_time",
        "login_attempt_number",
        "backup_used",
        "prompt_match",
        "graphical_selected_animal",
        "graphical_selected_colour",
        "keystroke_avg_z",
        "keystroke_max_z",
        "keystroke_similarity",
        "mouse_avg_z",
        "mouse_max_z",
        "mouse_similarity",
        "FAR",
        "FRR",
        "TAR",
        "TRR"
    ])
# all csv headers
    for row in rows:
        writer.writerow([
            row["id"],
            row["username"],
            row["is_impostor"],
            row["keystroke_result"],
            row["graphical_result"],
            row["mouse_result"],
            row["final_result"],
            row["login_time_seconds"],
            row["keystroke_time"],
            row["graphical_time"],
            row["mouse_time"],
            row["login_attempt_number"],
            row["backup_used"],
            row["prompt_match"],
            row["graphical_selected_animal"],
            row["graphical_selected_colour"],
            row["keystroke_avg_z"],
            row["keystroke_max_z"],
            row["keystroke_similarity"],
            row["mouse_avg_z"],
            row["mouse_max_z"],
            row["mouse_similarity"],
            row["FAR"],
            row["FRR"],
            row["TAR"],
            row["TRR"]
        ])

    csv_data = output.getvalue()
    output.close()
    # sends the csv text back to the browser as a downloadable file
    # opening /export-combined-attempts downloads the evaluation dataset
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=combined_attempts.csv"}
    )
# session clearing
def clear_register_session():
    session.pop("main_reg_step", None)
    session.pop("main_reg_username", None)
    session.pop("main_reg_keystroke_sessions", None)
    session.pop("main_reg_graphical_done", None)
    session.pop("main_reg_mouse_done", None)

def clear_login_session():
    session.pop("main_login_username", None)
    session.pop("main_login_prompt", None)
    session.pop("main_login_attempts_left", None)

# main combined registration route
# controls keystroke, graphical, and mouse registration in one flow
# renders main_register.html and saves completed profile data into users
@app.route("/main/register", methods=["GET", "POST"])
def main_register():
    error = None
    success = False
    username = session.get("main_reg_username", "")
    current_step = session.get("main_reg_step", "keystroke")
    keystroke_sessions = session.get("main_reg_keystroke_sessions", [])

    coverage_phrase = None
    pangram = None
    avg_profile = None
    std_profile = None
    registration_code = None

    if request.method == "POST":
        submitted_step = request.form.get("step", "").strip()

        # handles the keystroke registration stage
        # receives typed prompts and keydown/keyup json from main_register.html
        # sends event data to KeystrokeHandler for timing feature extraction
        if submitted_step == "keystroke":
            username = request.form.get("username", "").strip()
            typed = request.form.get("typed", "")
            typed2 = request.form.get("typed2", "")
            events_pangram_raw = request.form.get("events_pangram", "[]")
            events_coverage_raw = request.form.get("events_coverage", "[]")
            expected_pangram = request.form.get("expected_pangram", "").strip()
            expected_coverage = request.form.get("expected_coverage", "").strip()

        # error handling
            if not username:
                error = "ERROR: Please enter a username."
            elif normalise_text(typed) != normalise_text(expected_pangram):
                error = "ERROR: Pangram must be typed exactly as shown."
            elif normalise_text(typed2) != normalise_text(expected_coverage):
                error = "ERROR: Coverage phrase must be typed exactly as shown."
            else:
                try:
                    events_pangram = json.loads(events_pangram_raw)
                    events_coverage = json.loads(events_coverage_raw)
                except Exception:
                    events_pangram = []
                    events_coverage = []

                # rejects the sample if browser timing events are missing
                # both pangram and coverage phrase need timing data for combine_metrics()
                if not events_pangram or not events_coverage:
                    error = "ERROR: Keystroke event data is missing."
                else:
                    # processes the pangram and coverage phrase separately
                    # KeystrokeHandler.process_events() extracts raw timing features
                    # dataSummary() returns averages and standard deviations for each sample
                    handler1 = KeystrokeHandler()
                    handler1.process_events(events_pangram)
                    metrics1 = handler1.dataSummary()

                    handler2 = KeystrokeHandler()
                    handler2.process_events(events_coverage)
                    metrics2 = handler2.dataSummary()

                    combined_profile = combine_metrics(metrics1, metrics2)

                    # stores this keystroke session in flask session memory
                    # three sessions are collected before saving the final profile
                    keystroke_sessions.append(combined_profile)
                    session["main_reg_keystroke_sessions"] = keystroke_sessions
                    session["main_reg_username"] = username

                    # once three keystroke sessions exist, the final profile is built
                    # averages each timing metric across the three registration sessions
                    # this becomes the stored baseline used later by stats_range() in login
                    if len(keystroke_sessions) >= 3:
                        final_profile = {
                            "avg_dwell_ms": round(sum(x["avg_dwell_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "std_dwell_ms": round(sum(x["std_dwell_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "avg_flight_ms": round(sum(x["avg_flight_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "std_flight_ms": round(sum(x["std_flight_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "avg_latency_ms": round(sum(x["avg_latency_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "std_latency_ms": round(sum(x["std_latency_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "avg_interval_ms": round(sum(x["avg_interval_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                            "std_interval_ms": round(sum(x["std_interval_ms"] for x in keystroke_sessions) / len(keystroke_sessions), 3),
                        }

                        # checks whether this username already has a registration code hash
                        # if it exists, it is kept so re-enrolment does not replace the original code
                        db = get_db()
                        existing_user = db.execute(
                            "SELECT registration_code_hash FROM users WHERE username=?",(username,)).fetchone()

                        existing_registration_code_hash = None
                        if existing_user:
                            existing_registration_code_hash = existing_user["registration_code_hash"]

                        # saves the completed keystroke profile into users
                        # coverage_phrase is also saved because build_login_prompt() uses it later
                        # encrypt_value() protects stored values when encryption is enabled
                        db.execute("""
                            INSERT OR REPLACE INTO users (
                                username,
                                coverage_phrase,
                                avg_dwell_ms, std_dwell_ms,
                                avg_flight_ms, std_flight_ms,
                                avg_latency_ms, std_latency_ms,
                                avg_interval_ms, std_interval_ms,
                                registration_code_hash
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            username,
                            encrypt_value(expected_coverage),
                            encrypt_value(final_profile["avg_dwell_ms"]),
                            encrypt_value(final_profile["std_dwell_ms"]),
                            encrypt_value(final_profile["avg_flight_ms"]),
                            encrypt_value(final_profile["std_flight_ms"]),
                            encrypt_value(final_profile["avg_latency_ms"]),
                            encrypt_value(final_profile["std_latency_ms"]),
                            encrypt_value(final_profile["avg_interval_ms"]),
                            encrypt_value(final_profile["std_interval_ms"]),
                            existing_registration_code_hash
                        ))
                        db.commit()
                        db.close()

                        # moves registration to the graphical password stage
                        session["main_reg_step"] = "graphical"
                        current_step = "graphical"
                    else:
                        current_step = "keystroke"


        # handles graphical password registration
        # receives animal index and colour from main_register.html
        # stores only the hashed animal-colour secret in users
        elif submitted_step == "graphical":
            username = session.get("main_reg_username", "")
            animal_index_raw = request.form.get("graphical_animal_index", "").strip()
            colour = request.form.get("graphical_colour", "").strip().lower()


            # converts the selected animal index into the real animal name
            # animal_from_index() is defined in graphical_handler.py
            animal = animal_from_index(animal_index_raw)
            if not username:
                error = "ERROR: Username session is missing."
            elif not valid_selection(animal, colour):
                error = "ERROR: Please select a valid animal and colour."
            else:

                # hashes the selected animal and colour
                # graphical_match() uses the same hashing method during login
                # the raw graphical password is never stored
                password_hash = hash_graphical_secret(animal, colour)

                db = get_db()
                # adds the graphical hash to the existing user row
                # the user row was first created during the keystroke registration stage
                db.execute("""UPDATE users SET graphical_password_hash=? WHERE username=?""", (
                    encrypt_value(password_hash),
                    username
                ))
                db.commit()
                db.close()

                session["main_reg_step"] = "mouse"
                session["main_reg_graphical_done"] = True
                current_step = "mouse"

        # handles mouse dynamics registration
        # receives three mouse timing samples from main_register.html
        # build_profile() turns them into average and standard deviation profiles
        elif submitted_step == "mouse":
            username = session.get("main_reg_username", "")
            samples_raw = request.form.get("mouse_samples", "[]")

            # converts mouse timing json into python lists
            # parse_samples() is defined in mouse_handler.py
            samples = parse_samples(samples_raw)

            # erro handling
            # valid_samples() confirms the registration contains usable timing samples
            if not username:
                error = "ERROR: Username session is missing."
            elif not valid_samples(samples):
                error = "ERROR: Mouse registration data is invalid."
            else:

                # builds the stored mouse profile from registration samples
                # avg_profile and std_profile are later used by mouse_statsRange() in login
                profile = build_profile(samples)
                avg_profile = profile["avg_profile"]
                std_profile = profile["std_profile"]

                # checks whether a registration code hash already exists
                # this matters when a user is re-enrolling instead of registering for the first time
                db = get_db()
                existing_user = db.execute(
                    "SELECT registration_code_hash FROM users WHERE username=?",
                    (username,)
                ).fetchone()

                # creates a new registration code only for first-time registration
                # the raw code is shown once in main_register.html
                # the hash is stored and checked later in main_profile()
                existing_registration_code_hash = None
                if existing_user:
                    existing_registration_code_hash = existing_user["registration_code_hash"]

                if not existing_registration_code_hash:
                    registration_code = generate_registration_code()
                    existing_registration_code_hash = hash_registration_code(registration_code)


                # saves the mouse profile and registration code hash into users
                # mouse profiles are json strings because they store lists of transition timings
                # encrypt_value() protects them when encryption is enabled
                db.execute(
                    """UPDATE users SET mouse_avg_profile=?, mouse_std_profile=?, registration_code_hash=? WHERE username=?""",
                    (
                        encrypt_value(json.dumps(avg_profile)),
                        encrypt_value(json.dumps(std_profile)),
                        existing_registration_code_hash,
                        username
                    ))
                db.commit()
                db.close()

                # marks registration as complete
                # clear_register_session() removes temporary registration progress
                # success and registration_code are passed back to main_register.html
                session["main_reg_mouse_done"] = True
                success = True
                clear_login_session()
                clear_register_session()

    if current_step == "keystroke":
        coverage_phrase = keyCoverageGen()
        pangram = PANGRAMS[len(keystroke_sessions) % len(PANGRAMS)]

        # renders the combined registration template
        # current_step controls which stage the flask template displays
        # registration_code is only shown after full registration is complete

    return render_template(
        "main_register.html",
        error=error,
        success=success,
        username=username,
        current_step=current_step,
        keystroke_count=len(keystroke_sessions),
        pangram=pangram,
        coverage=coverage_phrase,
        avg_profile=avg_profile,
        std_profile=std_profile,
        registration_code=registration_code
    )


# main combined login route
# receives keystroke, graphical, mouse, and backup login data from main_login.html
# logs each full attempt into combined_attempts for evaluation
@app.route("/main/login", methods=["GET", "POST"])
def main_login():
    # default values sent to main_login.html
    # keeps the page stable before login, after errors, and after failed attempts
    error = None
    if request.method == "GET" and request.args.get("fresh") == "1":
        clear_login_session()
        return redirect("/main/login")

    username = session.get("main_login_username", "")
    prompt = session.get("main_login_prompt")

    final_result = None
    keystroke_result = "not checked"
    graphical_result = "not checked"
    mouse_result = "not checked"

    # keystroke debug and evaluation values
    # filled after stats_range() compares login timings with the stored profile
    keystroke_avg_z = None
    keystroke_max_z = None
    keystroke_similarity = None

    # mouse debug and evaluation values
    # filled after mouse_statsRange() compares the login sample with the stored profile
    mouse_avg_z = None
    mouse_max_z = None
    mouse_similarity = None
    mouse_z_breakdown = None

    # graphical and debug values shown in the template after checking login
    # useful for demo explanation and for confirming what the system processed
    graphical_selected_animal = None
    graphical_selected_colour = None
    prompt_match = None
    mouse_sample_debug = None

    total_login_time = None

    # tracks login retry attempts for the current session
    # login_attempt_number is written into combined_attempts for retry analysis
    attempts_left = session.get("main_login_attempts_left", 3)
    login_attempt_number = 4 - attempts_left

    if request.method == "POST":
        start_time = time.time()

        username = request.form.get("username", "").strip()
        # reads backup login fields
        # if use_backup is selected, the route checks the stored backup code instead
        use_backup = request.form.get("use_backup", "").strip()
        entered_backup_code = request.form.get("backup_code", "").strip()

        # reads typed login prompt and keystroke event json
        # events_raw is processed by KeystrokeHandler if prompt validation passes
        typed = request.form.get("typed", "")
        events_raw = request.form.get("events", "[]")

        # reads current colour state for each graphical animal
        # these values are set by the colour rotation javascript in main_login.html
        dog_colour = request.form.get("dog_colour", "").strip().lower()
        cat_colour = request.form.get("cat_colour", "").strip().lower()
        rabbit_colour = request.form.get("rabbit_colour", "").strip().lower()
        snake_colour = request.form.get("snake_colour", "").strip().lower()
        bird_colour = request.form.get("bird_colour", "").strip().lower()
        frog_colour = request.form.get("frog_colour", "").strip().lower()

        mouse_sample_raw = request.form.get("mouse_sample", "[]")
        login_duration_seconds = request.form.get("login_duration_seconds", "").strip()
        keystroke_time_raw = request.form.get("keystroke_time", "0").strip()
        graphical_time_raw = request.form.get("graphical_time", "0").strip()
        mouse_time_raw = request.form.get("mouse_time", "0").strip()

        # converts frontend timing strings into floats
        # these timings do not decide login success, but are logged for evaluation
        try:
            keystroke_time = float(keystroke_time_raw)
        except:
            keystroke_time = 0.0
        try:
            graphical_time = float(graphical_time_raw)
        except:
            graphical_time = 0.0
        try:
            mouse_time = float(mouse_time_raw)
        except:
            mouse_time = 0.0

        # tells app.py whether the login prompt has already been generated
        # if not loaded, this request only prepares the prompt for the user
        prompt_loaded = request.form.get("prompt_loaded", "").strip()

        db = get_db()
        user_row = None

        # opens the database and fetches the registered user profile
        # user_row is used by all three modality checks and backup login
        if username:
            user_row = db.execute("""SELECT * FROM users WHERE username=?""", (username,)).fetchone()
        if not username:
            error = "ERROR: Please enter a valid username."

        elif not user_row:
            error = "ERROR: This username has not completed registration."

        # checks one-time backup login
        # compares the entered backup code with the stored decrypted backup code
        # marks it as used if correct, then redirects to main_profile()
        elif use_backup == "1":
            stored_backup_code = decrypt_value(user_row["backup_code"])

            if not stored_backup_code:
                error = "ERROR: No backup code found for this username."
            elif user_row["backup_code_used"] == 1:
                error = "ERROR: This backup code has already been used."
            elif entered_backup_code != stored_backup_code:
                error = "ERROR: Incorrect backup code."

            else:
                db.execute("""UPDATE users SET backup_code_used=1 WHERE username=?""", (username,))
                db.commit()
                clear_login_session()
                db.close()
                return redirect(f"/main/profile?username={username}&backup_used=1")

        else:
            # first normal login step
            # builds a mixed prompt from next_pangram() and build_login_prompt()
            # stores the prompt in session so the next post can validate the typed text
            if prompt_loaded != "1":
                pangram_prompt = next_pangram()

                prompt = build_login_prompt(
                    pangram_prompt,
                    decrypt_value(user_row["coverage_phrase"])
                )

                session["main_login_username"] = username
                session["main_login_prompt"] = prompt
                session["main_login_attempts_left"] = 3
                attempts_left = 3
                login_attempt_number = 1

                # returns main_login.html with the generated prompt loaded
                # the user now completes keystroke, graphical, and mouse stages
                db.close()
                return render_template(
                    "main_login.html",
                    error=error,
                    username=username,
                    prompt=prompt,
                    final_result=final_result,
                    keystroke_result=keystroke_result,
                    graphical_result=graphical_result,
                    mouse_result=mouse_result,
                    keystroke_avg_z=keystroke_avg_z,
                    keystroke_max_z=keystroke_max_z,
                    keystroke_similarity=keystroke_similarity,
                    mouse_avg_z=mouse_avg_z,
                    mouse_max_z=mouse_max_z,
                    mouse_similarity=mouse_similarity,
                    mouse_z_breakdown=mouse_z_breakdown,
                    graphical_selected_animal=graphical_selected_animal,
                    graphical_selected_colour=graphical_selected_colour,
                    prompt_match=prompt_match,
                    mouse_sample_debug=mouse_sample_debug,
                    total_login_time=total_login_time,
                    attempts_left=3
                )

            prompt = session.get("main_login_prompt")

            # stops login if the session prompt is missing or expired
            # without the original prompt, keystroke comparison would not be valid
            if not prompt:
                error = "ERROR: No login prompt is loaded. Please enter your username again to start a new login attempt."
                db.close()

                return render_template(
                    "main_login.html",
                    error=error,
                    username=username,
                    prompt=prompt,
                    final_result=final_result,
                    keystroke_result=keystroke_result,
                    graphical_result=graphical_result,
                    mouse_result=mouse_result,
                    keystroke_avg_z=keystroke_avg_z,
                    keystroke_max_z=keystroke_max_z,
                    keystroke_similarity=keystroke_similarity,
                    mouse_avg_z=mouse_avg_z,
                    mouse_max_z=mouse_max_z,
                    mouse_similarity=mouse_similarity,
                    mouse_z_breakdown=mouse_z_breakdown,
                    graphical_selected_animal=graphical_selected_animal,
                    graphical_selected_colour=graphical_selected_colour,
                    prompt_match=prompt_match,
                    mouse_sample_debug=mouse_sample_debug,
                    total_login_time=total_login_time,
                    attempts_left=attempts_left
                )
            # converts submitted keystroke json into a python list
            # missing events means the keystroke modality cannot be checked
            try:
                events = json.loads(events_raw)
            except Exception:
                events = []

            # converts the mouse login sample into a python list
            # valid_sample() checks that it contains one complete 8-transition attempt
            sample = parse_samples(mouse_sample_raw)
            mouse_sample_debug = sample
            prompt_match = normalise_text(typed) == normalise_text(prompt)

            # rejects invalid login input before modality comparison
            # prevents wrong prompt text, missing keystrokes, or bad mouse data being scored
            if not prompt_match:
                error = "ERROR: Prompt must be typed exactly as shown."
            elif not events:
                error = "ERROR: Keystroke event data is missing."
            elif not valid_sample(sample):
                error = "ERROR: Mouse login data is invalid."
            else:

                # processes login keydown/keyup events
                # dataSummary() creates the same timing metrics used during registration
                handler = KeystrokeHandler()
                handler.process_events(events)

                metricsKeystroke = handler.dataSummary()

                # builds the current keystroke login profile
                # this is compared with stored_profile using stats_range()
                login_profile = {
                    "avg_dwell_ms": metricsKeystroke["avg_dwell_ms"],
                    "std_dwell_ms": metricsKeystroke["std_dwell_ms"],
                    "avg_flight_ms": metricsKeystroke["avg_flight_ms"],
                    "std_flight_ms": metricsKeystroke["std_flight_ms"],
                    "avg_latency_ms": metricsKeystroke["avg_latency_ms"],
                    "std_latency_ms": metricsKeystroke["std_latency_ms"],
                    "avg_interval_ms": metricsKeystroke["avg_interval_ms"],
                    "std_interval_ms": metricsKeystroke["std_interval_ms"],
                }

                # rebuilds the enrolled keystroke profile from users
                # decrypt_float() turns stored database values back into numbers
                stored_profile = {
                    "avg_dwell_ms": decrypt_float(user_row["avg_dwell_ms"]),
                    "std_dwell_ms": decrypt_float(user_row["std_dwell_ms"]),
                    "avg_flight_ms": decrypt_float(user_row["avg_flight_ms"]),
                    "std_flight_ms": decrypt_float(user_row["std_flight_ms"]),
                    "avg_latency_ms": decrypt_float(user_row["avg_latency_ms"]),
                    "std_latency_ms": decrypt_float(user_row["std_latency_ms"]),
                    "avg_interval_ms": decrypt_float(user_row["avg_interval_ms"]),
                    "std_interval_ms": decrypt_float(user_row["std_interval_ms"]),
                }

                # compares login_profile with stored_profile
                # stats_range() returns avg z, max z, and similarity for decision and evaluation
                keystroke_avg_z, keystroke_max_z, keystroke_similarity, _ = stats_range(
                    stored_profile,
                    login_profile
                )

                if keystroke_avg_z <= LOGIN_AVG_Z_THRESHOLD and keystroke_max_z <= LOGIN_MAX_Z_THRESHOLD:
                    keystroke_result = "logged in"
                else:
                    keystroke_result = "not logged in"

                # starts graphical login checking
                # stored_graphical_hash is compared against each submitted animal-colour pair
                graphical_selected_animal = ""
                graphical_selected_colour = ""
                graphical_result = "not logged in"
                stored_graphical_hash = decrypt_value(user_row["graphical_password_hash"])

                # six-animal graphical check
                # colours come from main_login.html after the user rotates the colour state
                # graphical_match() hashes each pair and compares it with the stored hash
                animal_checks = [
                    ("dog", dog_colour),
                    ("cat", cat_colour),
                    ("rabbit", rabbit_colour),
                    ("snake", snake_colour),
                    ("bird", bird_colour),
                    ("frog", frog_colour)
                ]

                for animal_name, current_colour in animal_checks:
                    if valid_selection(animal_name, current_colour):
                        if graphical_match(stored_graphical_hash, animal_name, current_colour):
                            graphical_result = "logged in"
                            graphical_selected_animal = animal_name

                            graphical_selected_colour = current_colour
                            break

                # stops mouse comparison if the user has no complete mouse profile
                # this can happen if registration was interrupted or reset
                if not user_row["mouse_avg_profile"] or not user_row["mouse_std_profile"]:
                    error = "ERROR: This user does not have a full mouse profile saved. Please redo registration."
                    db.close()
                    return render_template(
                        "main_login.html",
                        error=error,
                        username=username,
                        prompt=prompt,
                        final_result=final_result,
                        keystroke_result=keystroke_result,
                        graphical_result=graphical_result,
                        mouse_result=mouse_result,
                        keystroke_avg_z=keystroke_avg_z,
                        keystroke_max_z=keystroke_max_z,
                        keystroke_similarity=keystroke_similarity,
                        mouse_avg_z=mouse_avg_z,
                        mouse_max_z=mouse_max_z,
                        mouse_similarity=mouse_similarity,
                        mouse_z_breakdown=mouse_z_breakdown,
                        graphical_selected_animal=graphical_selected_animal,
                        graphical_selected_colour=graphical_selected_colour,
                        prompt_match=prompt_match,
                        mouse_sample_debug=mouse_sample_debug,
                        total_login_time=total_login_time,
                        attempts_left=attempts_left
                    )


                # rebuilds the enrolled mouse profile from users
                # decrypt_json() converts stored json strings back into timing lists
                stored_mouse_profile = {
                    "avg_profile": decrypt_json(user_row["mouse_avg_profile"]),
                    "std_profile": decrypt_json(user_row["mouse_std_profile"])
                }

                # builds the current mouse login profile from one submitted sample
                # std_profile is empty because login uses only one attempt
                login_mouse_profile = {
                    "avg_profile": sample,
                    "std_profile": []
                }

                # compares the login mouse sample against the stored mouse profile
                # mouse_statsRange() is defined in mouse_handler.py
                # returns avg z, max z, similarity, and transition-level z-scores
                mouse_avg_z, mouse_max_z, mouse_similarity, mouse_z_breakdown = mouse_statsRange(
                    stored_mouse_profile,
                    login_mouse_profile
                )

                # mouse passes only if avg z and max z are within threshold
                # thresholds are looser than keystrokes because mouse timing varies more
                if mouse_avg_z <= MOUSE_AVG_Z_THRESHOLD and mouse_max_z <= MOUSE_MAX_Z_THRESHOLD:
                    mouse_result = "logged in"
                else:
                    mouse_result = "not logged in"

                # final weighted multimodal rule
                # keystroke must pass, plus graphical or mouse must pass
                # final_result is saved to combined_attempts and shown in main_profile()
                if keystroke_result == "logged in" and (
                        graphical_result == "logged in" or mouse_result == "logged in"):
                    final_result = "logged in"
                else:
                    final_result = "not logged in"

                # uses frontend total login time when available
                # falls back to server time if the frontend value is missing
                try:
                    total_login_time = float(login_duration_seconds)
                except Exception:
                    total_login_time = round(time.time() - start_time, 3)

                # saves the completed login attempt into combined_attempts
                # stores each modality result, final result, timings, z-scores, and similarity
                db.execute("""
                    INSERT INTO combined_attempts (
                        username,
                        is_impostor,
                        keystroke_result,
                        graphical_result,
                        mouse_result,
                        final_result,
                        login_time_seconds,
                        keystroke_time,
                        graphical_time,
                        mouse_time,
                        login_attempt_number,
                        backup_used,
                        prompt_match,
                        graphical_selected_animal,
                        graphical_selected_colour,
                        keystroke_avg_z,
                        keystroke_max_z,
                        keystroke_similarity,
                        mouse_avg_z,
                        mouse_max_z,
                        mouse_similarity,
                        FAR,
                        FRR,
                        TAR,
                        TRR
                    ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)
                """, (
                    username,
                    keystroke_result,
                    graphical_result,
                    mouse_result,
                    final_result,
                    total_login_time,
                    keystroke_time,
                    graphical_time,
                    mouse_time,
                    login_attempt_number,
                    1 if prompt_match else 0,
                    graphical_selected_animal,
                    graphical_selected_colour,
                    keystroke_avg_z,
                    keystroke_max_z,
                    keystroke_similarity,
                    mouse_avg_z,
                    mouse_max_z,
                    mouse_similarity
                ))
                db.commit()

                # successful login path
                # clears login session and sends the user to main_profile.html
                # passes recent result values in the url for demo visibility
                if final_result == "logged in":
                    clear_login_session()
                    db.close()
                    return redirect(
                        f"/main/profile?username={username}"
                        f"&keystroke_result={keystroke_result}"
                        f"&graphical_result={graphical_result}"
                        f"&mouse_result={mouse_result}"
                        f"&keystroke_avg_z={keystroke_avg_z}"
                        f"&keystroke_max_z={keystroke_max_z}"
                        f"&keystroke_similarity={keystroke_similarity}"
                        f"&mouse_avg_z={mouse_avg_z}"
                        f"&mouse_max_z={mouse_max_z}"
                        f"&mouse_similarity={mouse_similarity}"
                    )

                # failed login path
                # reduces attempts left and updates login_attempt_number
                # this supports retry and first-attempt success analysis
                attempts_left = session.get("main_login_attempts_left", 3) - 1
                session["main_login_attempts_left"] = attempts_left
                login_attempt_number = 4 - attempts_left

                # ends the current login session after three failed attempts
                # clear_login_session() removes the prompt and attempt counter
                if attempts_left <= 0:
                    error = "ERROR: You have used all 3 login attempts for this session."
                    clear_login_session()

        db.close()

    return render_template(
        "main_login.html",
        error=error,
        username=username,
        prompt=prompt,
        final_result=final_result,
        keystroke_result=keystroke_result,
        graphical_result=graphical_result,
        mouse_result=mouse_result,
        keystroke_avg_z=keystroke_avg_z,
        keystroke_max_z=keystroke_max_z,
        keystroke_similarity=keystroke_similarity,
        mouse_avg_z=mouse_avg_z,
        mouse_max_z=mouse_max_z,
        mouse_similarity=mouse_similarity,
        mouse_z_breakdown=mouse_z_breakdown,
        graphical_selected_animal=graphical_selected_animal,
        graphical_selected_colour=graphical_selected_colour,
        prompt_match=prompt_match,
        mouse_sample_debug=mouse_sample_debug,
        total_login_time=total_login_time,
        attempts_left=attempts_left
    )

@app.route("/main/profile", methods=["GET", "POST"])
def main_profile():
    error = None
    success = None

    # gets username from the url or submitted profile form
    # needed to load the correct user row from users
    username = request.args.get("username", "").strip() or request.form.get("username", "").strip()
    backup_used = request.args.get("backup_used", "").strip()

    # reads recent login result values passed from main_login()
    # shown on main_profile.html for demo and debugging
    keystroke_result = request.args.get("keystroke_result", "")
    graphical_result = request.args.get("graphical_result", "")
    mouse_result = request.args.get("mouse_result", "")

    keystroke_avg_z = request.args.get("keystroke_avg_z", "")
    keystroke_max_z = request.args.get("keystroke_max_z", "")
    keystroke_similarity = request.args.get("keystroke_similarity", "")

    mouse_avg_z = request.args.get("mouse_avg_z", "")
    mouse_max_z = request.args.get("mouse_max_z", "")
    mouse_similarity = request.args.get("mouse_similarity", "")

    # backup display defaults
    # updated if the user generates a new backup code on this page
    backupCodeText = None
    backup_code_used = 0

    # sends the user back to login if no username is available
    # profile actions need a valid user row
    if not username:
        return redirect("/main/login")

    db = get_db()
    # loads the registered profile from users
    # needed for backup generation and registration code checking
    user_row = db.execute("""SELECT * FROM users WHERE username=?""", (username,)).fetchone()

    if not user_row:
        db.close()
        return redirect("/main/login")

    # handles profile form actions
    # current actions are generate_backup and redo_all
    if request.method == "POST":
        action = request.form.get("action", "").strip()

        # creates a one-time backup code from the current stored profiles
        # backupCode() combines keystroke, graphical, and mouse data
        if action == "generate_backup":

            # rebuilds the stored keystroke profile for backupCode()
            # decrypt_float() converts encrypted database values back to numbers
            keystroke_profile = {
                "avg_dwell_ms": decrypt_float(user_row["avg_dwell_ms"]),
                "std_dwell_ms": decrypt_float(user_row["std_dwell_ms"]),
                "avg_flight_ms": decrypt_float(user_row["avg_flight_ms"]),
                "std_flight_ms": decrypt_float(user_row["std_flight_ms"]),
                "avg_latency_ms": decrypt_float(user_row["avg_latency_ms"]),
                "std_latency_ms": decrypt_float(user_row["std_latency_ms"]),
                "avg_interval_ms": decrypt_float(user_row["avg_interval_ms"]),
                "std_interval_ms": decrypt_float(user_row["std_interval_ms"]),
            }

            # loads the stored graphical hash for backupCode()
            # this is the hashed animal-colour secret from graphical registration
            graphical_hash = decrypt_value(user_row["graphical_password_hash"])

            # checks that all modality profiles exist before generating a backup code
            # the backup code depends on the full current profile
            if not user_row["mouse_avg_profile"] or not user_row["mouse_std_profile"]:
                error = "ERROR: This user does not have a full mouse profile saved yet."
            elif not graphical_hash:
                error = "ERROR: This user does not have a graphical password saved yet."
            else:
                # rebuilds the stored mouse profile for backupCode()
                # decrypt_json() converts encrypted json back into timing lists
                mouse_profile = {
                    "avg_profile": decrypt_json(user_row["mouse_avg_profile"]),
                    "std_profile": decrypt_json(user_row["mouse_std_profile"])
                }

                # creates the backup code from the current profile values
                # shown to the user and stored for one-time backup login
                backupCodeText = backupCode(
                    keystroke_profile,
                    graphical_hash,
                    mouse_profile
                )

                # saves the backup code and marks it unused
                # encrypt_value() protects it in the database
                db.execute("""UPDATE users SET backup_code=?, backup_code_used=0 WHERE username=?""", (
                    encrypt_value(backupCodeText),
                    username
                ))
                db.commit()

                success = "Backup code generated."

        # starts protected re-enrolment
        # user must provide the original registration code before profile fields are cleared
        elif action == "redo_all":

            # reads the registration code entered on main_profile.html
            # checked against the stored hash before allowing re-enrolment
            entered_registration_code = request.form.get("registration_code", "").strip()
            # loads the stored registration code hash from users
            # the raw original registration code is never stored
            stored_registration_code_hash = user_row["registration_code_hash"]

            if not stored_registration_code_hash:
                error = "ERROR: No registration code is saved for this account."

            # blocks re-enrolment if the user submits an empty code
            # main_profile.html shows the error message
            elif not entered_registration_code:
                error = "ERROR: Please enter your registration code."

            elif hash_registration_code(entered_registration_code) != stored_registration_code_hash:
                error = "ERROR: Incorrect registration code."

            # hashes the entered code and compares it with the stored hash
            # this protects metric reset without storing the raw code
            else:
                db.execute("""UPDATE users SET graphical_password_hash=NULL, mouse_avg_profile=NULL,
                        mouse_std_profile=NULL, backup_code=NULL, backup_code_used=0 WHERE username=?
                """, (username,))
                db.commit()
                db.close()

                clear_register_session()
                # sends the user back to the combined registration flow
                # main_register() rebuilds the missing profile data
                return redirect("/main/register")

    # reloads the user row after profile actions
    # ensures backup code display uses the latest database value
    user_row = db.execute("""SELECT * FROM users WHERE username=?""", (username,)).fetchone()

    # decrypts the backup code for display on main_profile.html
    # if no backup code exists, nothing is shown
    displayed_backup_code = decrypt_value(user_row["backup_code"]) if user_row["backup_code"] else None
    db.close()


    # renders main_profile.html with user status, backup code, and recent login results
    # result values were passed from main_login() after successful login
    return render_template(
        "main_profile.html",
        username=username,
        error=error,
        success=success,
        backupCode=displayed_backup_code,
        backup_code_used=backup_code_used,
        backup_used=backup_used,
        keystroke_result = keystroke_result,
        graphical_result = graphical_result,
        mouse_result = mouse_result,
        keystroke_avg_z = keystroke_avg_z,
        keystroke_max_z = keystroke_max_z,
        keystroke_similarity=keystroke_similarity,
        mouse_avg_z = mouse_avg_z,
        mouse_max_z = mouse_max_z,
        mouse_similarity=mouse_similarity,

    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)