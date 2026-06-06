import json
import hashlib
import os
import time
import secrets

USERS_FILE = "users.json"
SESSIONS_FILE = "sessions.json"


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


# ── ブラウザリロードでのセッション継続 ──────────────────────────
# st.session_state はブラウザとの接続（WebSocket）に紐づいており、
# ページをリロードすると新しいセッションになって失われる。
# そこでログイン時にトークンを発行してURL（st.query_params）に載せ、
# サーバー側 sessions.json と突き合わせて「30分以内の活動なら復元する」。

def _load_sessions() -> dict:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_sessions(sessions: dict):
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def create_session(username: str) -> str:
    """ログイン成功時にセッショントークンを発行し、サーバー側に記録する。
    あわせて長期間活動のない古いレコード（24時間超）を掃除し、肥大化を防ぐ。"""
    token = secrets.token_urlsafe(32)
    sessions = _load_sessions()
    now = time.time()
    sessions = {k: v for k, v in sessions.items()
                if now - v.get("last_activity", 0) <= 24 * 60 * 60}
    sessions[token] = {"username": username, "last_activity": now}
    _save_sessions(sessions)
    return token


def resume_session(token: str, max_idle: int) -> str | None:
    """トークンが有効（max_idle秒以内に活動）ならusernameを返す。
    期限切れ・不正なトークンの場合はNoneを返し、レコードを削除する。"""
    if not token:
        return None
    sessions = _load_sessions()
    s = sessions.get(token)
    if not s:
        return None
    if time.time() - s.get("last_activity", 0) > max_idle:
        sessions.pop(token, None)
        _save_sessions(sessions)
        return None
    return s["username"]


def touch_session(token: str, min_interval: int = 60):
    """セッションの最終活動時刻を更新する。
    毎回の再描画で書き込むとI/Oが増えるため、min_interval秒以上経過時のみ書き込む。"""
    if not token:
        return
    sessions = _load_sessions()
    s = sessions.get(token)
    if not s:
        return
    now = time.time()
    if now - s.get("last_activity", 0) >= min_interval:
        s["last_activity"] = now
        _save_sessions(sessions)


def delete_session(token: str):
    """ログアウト・タイムアウト時にセッションレコードを削除する。"""
    if not token:
        return
    sessions = _load_sessions()
    if sessions.pop(token, None) is not None:
        _save_sessions(sessions)


def unlock_user(username: str) -> bool:
    """管理者用：アカウントのロックを解除する。"""
    users = _load_users()
    if username not in users:
        return False
    users[username]["locked"] = False
    users[username]["failed_attempts"] = 0
    _save_users(users)
    return True
