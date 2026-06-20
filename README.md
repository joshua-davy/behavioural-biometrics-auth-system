# Evaluation of Human Biometric Interaction Techniques for Secure User Authentication

## Project Overview

This repository contains the software artefacts for my Final Year Software Engineering dissertation project.

The project is a Flask-based multimodal authentication system that combines three authentication modalities:

1. Keystroke dynamics
2. Graphical password authentication
3. Mouse dynamics

The aim of the system is to evaluate whether combining multiple human interaction-based authentication techniques can improve secure user authentication compared with relying on a single conventional password-style mechanism.

The final system uses a combined registration and login flow. Users register their keystroke profile, graphical password, and mouse profile through one main registration page. During login, each modality is tested and the final login decision is made using a weighted multimodal rule.

---

## Current System Flow

The final system uses three main pages:

| Page | Purpose |
|---|---|
| `/main/register` | Combined registration for keystroke, graphical, and mouse profiles |
| `/main/login` | Combined login using all three modalities |
| `/main/profile` | Profile page, backup code generation, and protected re-enrolment |

Login attempt data is stored in SQLite and can be exported as CSV for evaluation.

---

## Repository Structure

The main software artefacts are located in the `/source/` directory.

```text
/source/
│
├── app.py
├── database.py
├── keystroke_handler.py
├── graphical_handler.py
├── mouse_handler.py
├── keystrokes.db
│
├── templates/
│   ├── main_register.html
│   ├── main_login.html
│   └── main_profile.html
│
└── static/
    └── images/
        ├── bird1.jpg
        ├── cat1.jpg
        ├── dog1.jpg
        ├── frog1.jpg
        ├── rab1.jpg
        └── snake1.jpg
```

### Main Files

| File | Description |
|---|---|
| `app.py` | Main Flask application. Handles routes, registration, login, profile actions, multimodal decision logic, backup codes, optional encryption, and CSV export |
| `database.py` | SQLite setup and database connection helper |
| `keystroke_handler.py` | Processes keystroke keydown/keyup events and calculates timing features |
| `graphical_handler.py` | Handles graphical password validation, hashing, and matching |
| `mouse_handler.py` | Processes mouse timing samples, builds mouse profiles, and compares login attempts |
| `main_register.html` | Combined registration interface |
| `main_login.html` | Combined login interface |
| `main_profile.html` | Profile, backup code, and re-enrolment interface |
| `keystrokes.db` | SQLite database file used by the prototype |

---

## Requirements

The project requires:

- Python 3.10 or newer
- Flask
- cryptography

Recommended IDE:
- PyCharm
- Visual Studio Code


PyCharm is recommended, as the system was developed and tested using it. Visual Studio Code also works well and provides an integrated terminal, Python environment support, and Git tools.

---

## How to Run the Project

### 1. Clone or download the repository

```bash
git clone https://campus.cs.le.ac.uk/gitlab/ug_project/25-26/jd534
cd jd534
cd source
```

### 2. Create a virtual environment

#### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install required packages

```bash
pip install flask cryptography
```


### 4. Run the Flask application

Make sure you are inside the `/source/` folder, then run:

```bash
python app.py
```

The Flask development server should start locally.

Open the application in a browser at:

```text
http://127.0.0.1:5000/main/register
```

or go directly to login:

```text
http://127.0.0.1:5000/main/login
```

---

## Main URLs

| URL | Description |
|---|---|
| `http://127.0.0.1:5000/main/register` | Register a new user |
| `http://127.0.0.1:5000/main/login` | Log in using the multimodal system |
| `http://127.0.0.1:5000/main/profile` | View profile after successful login |
| `http://127.0.0.1:5000/export-combined-attempts` | Export logged attempt data as CSV |

---

## Using the System

### Registration

1. Go to `/main/register`
2. Enter a username
3. Complete the keystroke registration stage (2 typing prompts, completed 3 times)
4. Select the graphical password animal and colour (Use arrow keys for colour rotation, numbers for selection)
5. Complete the mouse registration stage by clicking numbers 1 to 9
6. Save the registration code shown at the end of registration

The registration code is required if the user later wants to redo or strengthen their stored metrics.

### Login

1. Go to `/main/login`
2. Enter the registered username, press enter to load
3. Type the generated keystroke prompt
4. Complete the graphical colour-selection task
5. Complete the mouse grid task
6. The system evaluates each modality and returns a final login result

The final system uses a weighted multimodal rule:

```text
Keystroke must pass
AND
Graphical OR Mouse must pass
```

### Profile and Re-Enrolment

After a successful login, the user is taken to `/main/profile`.

From the profile page, the user can:

- generate a backup code
- redo all authentication metrics
- return to login

Re-enrolment is protected by the original registration code. This prevents an impostor who gains access from replacing the genuine user’s biometric profiles.

---

## Database

The project uses SQLite.

The main database file is:

```text
/source/keystrokes.db
```

The two main active tables are:

| Table | Purpose |
|---|---|
| `users` | Stores registered user profiles and authentication data |
| `combined_attempts` | Stores login attempt results for evaluation |

The `combined_attempts` table stores the data required for evaluation metrics.

---

## CSV Export

To export login attempt data, run the system and open:

```text
http://127.0.0.1:5000/export-combined-attempts
```

This downloads a CSV file containing the logged authentication attempts for evaluation metrics.

---

## Optional Encryption Feature

The project includes optional field-level encryption using Fernet from the `cryptography` package.

This is controlled in `app.py` using:

```python
ENCRYPT_DB_FIELDS = True
```

When enabled, selected stored values are encrypted before being saved to the database.

Important notes:

- Encryption should be kept consistent for the database.
- If old rows were created while encryption was off, turning encryption on later may cause read/decryption errors unless the data is migrated.
- For demonstration, it is safest to use a fresh database if encryption is enabled.

---

## Common Issues

### Flask is not recognised

Make sure Flask is installed inside the active virtual environment:

```bash
pip install flask
```

### `cryptography` import error

Install the package:

```bash
pip install cryptography
```

### Database errors after changing encryption setting

Use a fresh database or keep the encryption setting the same as when the database rows were created.

### Images not loading

Make sure the image files are inside:

```text
/source/static/images/
```

Also make sure the Flask app is being run from the `/source/` folder.

---

## Project Artefacts

Main artefacts for the dissertation include:

| Folder/File | Purpose |
|---|---|
| `/source/` | Final software implementation |
| `/source/templates/` | HTML interfaces |
| `/source/static/images/` | Graphical password images |
| `/diagrams/` | UML, ERD, and sequence diagrams  |
| `/evaluation/` | Exported CSV files, Excel analysis, graphs, and participant results |


## Diagrams

All system and design diagrams used during development are included in the `/diagrams/` directory of this repository.

### Included diagrams
- **System Architecture Diagram**  
  High‑level overview of the frontend, backend, handlers, and database.

- **ER Diagram**  
  Database structure showing the `users` and `combined_attempts` tables.

- **UML Class Diagrams**  
  Class structure for the Flask app, handlers, database layer, and data models.

- **Use Case Diagram**  
  Functional overview of user and researcher interactions with the system.

- **Flowchart**  
  End‑to‑end login and re‑registration process.

- **Sequence Diagrams**  
  - Registration flow  
  - Login flow  
  - Backup code generation and login  
  - Re‑enrolment (redo metrics) flow  

These diagrams support the design and implementation documentation and provide a clear visual reference for system behaviour.

##
##
##