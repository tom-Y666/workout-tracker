import json
import os

from supabase_client import get_client

DEFAULT_EXERCISES_FILE = "default_exercises.json"


# ── 種目定義 ──────────────────────────────────────────────────────

def get_exercises(username: str) -> list[dict]:
    """ユーザーの種目定義一覧を返す。"""
    res = get_client().table("exercises").select("*").eq("username", username).execute()
    return [
        {"name": r["name"], "default_sets": r["default_sets"],
         "default_weight": r["default_weight"], "status": r["status"]}
        for r in res.data
    ]


def upsert_exercise(username: str, exercise: dict):
    """種目を追加または更新する。"""
    row = {**exercise, "username": username}
    get_client().table("exercises").upsert(row, on_conflict="username,name").execute()


def delete_exercise(username: str, name: str):
    get_client().table("exercises").delete().eq("username", username).eq("name", name).execute()


def init_default_exercises(username: str):
    """ユーザーの種目が0件の場合、デフォルトテンプレート（default_exercises.json）から
    種目を自動投入する（初回ログイン時用。個人情報を含まないテンプレートをGit管理する）。"""
    if get_exercises(username):
        return
    if not os.path.exists(DEFAULT_EXERCISES_FILE):
        return
    with open(DEFAULT_EXERCISES_FILE, "r", encoding="utf-8") as f:
        defaults = json.load(f)
    if not defaults:
        return
    rows = [{**e, "username": username} for e in defaults]
    get_client().table("exercises").upsert(rows, on_conflict="username,name").execute()


# ── トレーニングセッション ─────────────────────────────────────────

def get_sessions(username: str) -> list[dict]:
    """全セッションを日付降順で返す。"""
    res = (
        get_client().table("workouts").select("*")
        .eq("username", username).order("date", desc=True).execute()
    )
    return [
        {"date": r["date"], "status": r["status"], "exercises": r["exercises"]}
        for r in res.data
    ]


def get_session_by_date(username: str, date_str: str) -> dict | None:
    res = (
        get_client().table("workouts").select("*")
        .eq("username", username).eq("date", date_str).execute()
    )
    if not res.data:
        return None
    r = res.data[0]
    return {"date": r["date"], "status": r["status"], "exercises": r["exercises"]}


def upsert_session(username: str, session: dict):
    """セッションを保存（同じ日付があれば上書き）。"""
    row = {"username": username, **session}
    get_client().table("workouts").upsert(row, on_conflict="username,date").execute()
