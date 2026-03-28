import os
import jwt
import bcrypt
from datetime import datetime, timedelta
from database import create_user, get_user_by_username, get_user_by_id
from fastapi import HTTPException, Header
from typing import Optional

JWT_SECRET = os.environ.get("JWT_SECRET", "dev_secret_change_in_production")
JWT_EXPIRY_DAYS = 7

# ===== PASSWORD =====

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# ===== JWT =====

def create_token(user_id: int, username: str) -> str:
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRY_DAYS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token. Please log in again.")

# ===== AUTH ACTIONS =====

def register_user(username: str, password: str) -> dict:
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if get_user_by_username(username):
        raise HTTPException(status_code=400, detail="Username already taken.")

    user_id = create_user(username, hash_password(password))
    token = create_token(user_id, username)
    return {"token": token, "username": username, "user_id": user_id}

def login_user(username: str, password: str) -> dict:
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = create_token(user["id"], user["username"])
    return {"token": token, "username": user["username"], "user_id": user["id"]}

# ===== DEPENDENCY: get current user from Authorization header =====

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    user = get_user_by_id(payload["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user
