import hashlib
import time
import secrets

from supabase_client import get_client


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_from_secrets():
    """Streamlit Secretsから初期ユーザーを自動作成（テーブルが空の場合のみ）。"""
    try:
        import streamlit as st
        if "users" not in st.secrets:
            return
        existing = get_client().table("users").select("username").limit(1).execute()
        if existing.data:  # すでにユーザーがいれば何もしない
            return
        for username, password in st.secrets["users"].items():
            register_user(username, str(password))
    except Exception:
        pass


def register_user(username: str, password: str) -> bool:
    """管理者用：ユーザー登録。既存ユーザーの場合はFalseを返す。"""
    client = get_client()
    existing = client.table("users").select("username").eq("username", username).execute()
    if existing.data:
        return False
    client.table("users").insert({
        "username": username,
        "password": _hash_password(password),
        "failed_attempts": 0,
        "locked": False,
    }).execute()
    return True


def authenticate(username: str, password: str) -> tuple[bool, str | None]:
    """認証。(成功フラグ, エラーメッセージ) を返す。"""
    client = get_client()
    res = client.table("users").select("*").eq("username", username).execute()
    if not res.data:
        return False, "ユーザー名またはパスワードが違います"

    user = res.data[0]

    if user.get("locked"):
        return False, "アカウントがロックされています。管理者にお問い合わせください。"

    if user["password"] == _hash_password(password):
        client.table("users").update({"failed_attempts": 0}).eq("username", username).execute()
        return True, None
    else:
        failed_attempts = user.get("failed_attempts", 0) + 1
        if failed_attempts >= 3:
            client.table("users").update(
                {"failed_attempts": failed_attempts, "locked": True}
            ).eq("username", username).execute()
            return False, "パスワードを3回間違えました。アカウントがロックされました。管理者にお問い合わせください。"
        client.table("users").update({"failed_attempts": failed_attempts}).eq("username", username).execute()
        remaining = 3 - failed_attempts
        return False, f"パスワードが違います（あと {remaining} 回間違えるとロック）"


def list_users() -> dict:
    """管理者用：全ユーザーの状態を返す。"""
    res = get_client().table("users").select("username, failed_attempts, locked").execute()
    return {
        r["username"]: {"failed_attempts": r.get("failed_attempts", 0), "locked": r.get("locked", False)}
        for r in res.data
    }


# ── ブラウザリロードでのセッション継続 ──────────────────────────
# st.session_state はブラウザとの接続（WebSocket）に紐づいており、
# ページをリロードすると新しいセッションになって失われる。
# そこでログイン時にトークンを発行してURL（st.query_params）に載せ、
# サーバー側 sessions テーブルと突き合わせて「30分以内の活動なら復元する」。

def create_session(username: str) -> str:
    """ログイン成功時にセッショントークンを発行し、サーバー側に記録する。
    あわせて長期間活動のない古いレコード（24時間超）を掃除し、肥大化を防ぐ。"""
    client = get_client()
    token = secrets.token_urlsafe(32)
    now = time.time()
    client.table("sessions").delete().lt("last_activity", now - 24 * 60 * 60).execute()
    client.table("sessions").insert({
        "token": token, "username": username, "last_activity": now,
    }).execute()
    return token


def resume_session(token: str, max_idle: int) -> str | None:
    """トークンが有効（max_idle秒以内に活動）ならusernameを返す。
    期限切れ・不正なトークンの場合はNoneを返し、レコードを削除する。"""
    if not token:
        return None
    client = get_client()
    res = client.table("sessions").select("*").eq("token", token).execute()
    if not res.data:
        return None
    s = res.data[0]
    if time.time() - s.get("last_activity", 0) > max_idle:
        client.table("sessions").delete().eq("token", token).execute()
        return None
    return s["username"]


def touch_session(token: str, min_interval: int = 60):
    """セッションの最終活動時刻を更新する。
    毎回の再描画で書き込むとI/Oが増えるため、min_interval秒以上経過時のみ書き込む。"""
    if not token:
        return
    client = get_client()
    res = client.table("sessions").select("last_activity").eq("token", token).execute()
    if not res.data:
        return
    now = time.time()
    if now - res.data[0].get("last_activity", 0) >= min_interval:
        client.table("sessions").update({"last_activity": now}).eq("token", token).execute()


def delete_session(token: str):
    """ログアウト・タイムアウト時にセッションレコードを削除する。"""
    if not token:
        return
    get_client().table("sessions").delete().eq("token", token).execute()


def unlock_user(username: str) -> bool:
    """管理者用：アカウントのロックを解除する。"""
    client = get_client()
    existing = client.table("users").select("username").eq("username", username).execute()
    if not existing.data:
        return False
    client.table("users").update({"locked": False, "failed_attempts": 0}).eq("username", username).execute()
    return True
