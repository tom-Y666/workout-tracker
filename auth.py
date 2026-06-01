import json
import hashlib
import os

USERS_FILE = "users.json"


def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_from_secrets():
    """Streamlit Secretsから初期ユーザーを自動作成（ファイルが空の場合のみ）。"""
    try:
        import streamlit as st
        if "users" not in st.secrets:
            return
        if _load_users():  # すでにユーザーがいれば何もしない
            return
        for username, password in st.secrets["users"].items():
            register_user(username, str(password))
    except Exception:
        pass


def register_user(username: str, password: str) -> bool:
    """管理者用：ユーザー登録。既存ユーザーの場合はFalseを返す。"""
    users = _load_users()
    if username in users:
        return False
    users[username] = {
        "password": _hash_password(password),
        "failed_attempts": 0,
        "locked": False,
    }
    _save_users(users)
    return True


def authenticate(username: str, password: str) -> tuple[bool, str | None]:
    """認証。(成功フラグ, エラーメッセージ) を返す。"""
    users = _load_users()
    if username not in users:
        return False, "ユーザー名またはパスワードが違います"

    user = users[username]

    if user.get("locked"):
        return False, "アカウントがロックされています。管理者にお問い合わせください。"

    if user["password"] == _hash_password(password):
        user["failed_attempts"] = 0
        _save_users(users)
        return True, None
    else:
        user["failed_attempts"] = user.get("failed_attempts", 0) + 1
        if user["failed_attempts"] >= 3:
            user["locked"] = True
            _save_users(users)
            return False, "パスワードを3回間違えました。アカウントがロックされました。管理者にお問い合わせください。"
        remaining = 3 - user["failed_attempts"]
        _save_users(users)
        return False, f"パスワードが違います（あと {remaining} 回間違えるとロック）"


def unlock_user(username: str) -> bool:
    """管理者用：アカウントのロックを解除する。"""
    users = _load_users()
    if username not in users:
        return False
    users[username]["locked"] = False
    users[username]["failed_attempts"] = 0
    _save_users(users)
    return True
