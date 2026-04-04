"""
auth.py — Handles user registration, login, and JWT-based session management.
All user data is stored in data/users.json (no external database needed).
"""

import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
import bcrypt
import jwt

from utils.user_defaults import ensure_user_defaults, merge_profile_update

# ── Configuration ──────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "smartlearn_secret_2024")  # Change in production
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

DATA_DIR = Path(__file__).parent.parent / "data"
USERS_FILE = DATA_DIR / "users.json"

router = APIRouter()
security = HTTPBearer()


# ── Pydantic Models (request/response shapes) ──────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    age: int | None = Field(default=None, ge=10, le=120)
    year_of_college: int | None = Field(default=None, ge=1, le=8)
    college_name: str | None = None
    learning_goals: str | None = None
    onboarding_complete: bool | None = None


def user_public_dict(u: dict) -> dict:
    ensure_user_defaults(u)
    p = u.get("profile") or {}
    return {
        "id": u["id"],
        "username": u["username"],
        "email": u["email"],
        "full_name": u["full_name"],
        "selected_subjects": u.get("selected_subjects", []),
        "profile": {
            "age": p.get("age"),
            "year_of_college": p.get("year_of_college"),
            "college_name": p.get("college_name"),
            "learning_goals": p.get("learning_goals"),
            "onboarding_complete": p.get("onboarding_complete", False),
        },
        "entry_quiz_completed": u.get("entry_quiz_completed", False),
        "skill_level": u.get("skill_level"),
    }


# ── JSON File Helpers ──────────────────────────────────────────────────────────
def load_users() -> list:
    """Read all users from the JSON file."""
    if not USERS_FILE.exists():
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def save_users(users: list) -> None:
    """Persist the users list back to the JSON file."""
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


# ── JWT Utilities ──────────────────────────────────────────────────────────────
def create_access_token(user_id: str, email: str) -> str:
    """Generate a signed JWT token that expires after TOKEN_EXPIRE_HOURS."""
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token. Please login again.")


# ── Dependency: get current logged-in user from Authorization header ───────────
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI dependency — extract and validate the Bearer token from request headers.
    Returns the user dict if valid, raises 401 otherwise.
    """
    payload = decode_token(credentials.credentials)
    users = load_users()

    # Find user by id stored in token
    user = next((u for u in users if u["id"] == payload["sub"]), None)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    u = deepcopy(user)
    ensure_user_defaults(u)
    return u


# ── Routes ─────────────────────────────────────────────────────────────────────
@router.post("/register")
def register(req: RegisterRequest):
    """
    Register a new user.
    - Checks for duplicate email
    - Hashes the password with bcrypt
    - Saves user to users.json
    """
    users = load_users()

    # Duplicate email check
    if any(u["email"].lower() == req.email.lower() for u in users):
        raise HTTPException(status_code=400, detail="Email already registered.")

    # Duplicate username check
    if any(u["username"].lower() == req.username.lower() for u in users):
        raise HTTPException(status_code=400, detail="Username already taken.")

    # Hash password before storing
    hashed_pw = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()

    new_user = {
        "id": str(uuid.uuid4()),
        "username": req.username.strip(),
        "email": req.email.lower().strip(),
        "password": hashed_pw,
        "full_name": req.full_name.strip(),
        "selected_subjects": [],          # Populated during onboarding
        "created_at": datetime.utcnow().isoformat(),
    }
    ensure_user_defaults(new_user)

    users.append(new_user)
    save_users(users)

    # Return token immediately so user is logged in right after register
    token = create_access_token(new_user["id"], new_user["email"])
    return {
        "message": "Registration successful.",
        "token": token,
        "user": user_public_dict(new_user),
    }


@router.post("/login")
def login(req: LoginRequest):
    """
    Authenticate a user with email + password.
    Returns a JWT token on success.
    """
    users = load_users()
    user = next((u for u in users if u["email"].lower() == req.email.lower()), None)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    # Verify password against stored hash
    if not bcrypt.checkpw(req.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    token = create_access_token(user["id"], user["email"])
    uc = deepcopy(user)
    ensure_user_defaults(uc)
    return {
        "message": "Login successful.",
        "token": token,
        "user": user_public_dict(uc),
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return user_public_dict(current_user)


@router.put("/profile")
def update_profile(body: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    users = load_users()
    updated = None
    for u in users:
        if u["id"] == current_user["id"]:
            ensure_user_defaults(u)
            merge_profile_update(
                u,
                full_name=body.full_name,
                age=body.age,
                year_of_college=body.year_of_college,
                college_name=body.college_name,
                learning_goals=body.learning_goals,
                onboarding_complete=body.onboarding_complete,
            )
            updated = u
            break
    if not updated:
        raise HTTPException(status_code=404, detail="User not found.")
    save_users(users)
    return {"message": "Profile updated.", "user": user_public_dict(updated)}
