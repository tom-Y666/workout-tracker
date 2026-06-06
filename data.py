import json
import os

EXERCISES_FILE = "exercises.json"
WORKOUTS_FILE = "workouts.json"
DEFAULT_EXERCISES_FILE = "default_exercises.json"


def _load(filename: str) -> dict:
    if not os.path.exists(filename):
        return {}
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(filename: str, data: dict):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── 種目定義 ──────────────────────────────────────────────────────

def get_exercises(username: str) -> list[dict]:
    """ユーザーの種目定義一覧を返す。"""
    return _load(EXERCISES_FILE).get(username, [])


def upsert_exercise(username: str, exercise: dict):
    """種目を追加または更新する。"""
    data = _load(EXERCISES_FILE)
    if username not in data:
        data[username] = []
    for i, e in enumerate(data[username]):
        if e["name"] == exercise["name"]:
            data[username][i] = exercise
            _save(EXERCISES_FILE, data)
            return
    data[username].append(exercise)
    _save(EXERCISES_FILE, data)


def delete_exercise(username: str, name: str):
    data = _load(EXERCISES_FILE)
    data[username] = [e for e in data.get(username, []) if e["name"] != name]
    _save(EXERCISES_FILE, data)


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
    data = _load(EXERCISES_FILE)
    data[username] = defaults
    _save(EXERCISES_FILE, data)


# ── トレーニングセッション ─────────────────────────────────────────

def get_sessions(username: str) -> list[dict]:
    """全セッションを日付降順で返す。"""
    sessions = _load(WORKOUTS_FILE).get(username, [])
    return sorted(sessions, key=lambda s: s["date"], reverse=True)


def get_session_by_date(username: str, date_str: str) -> dict | None:
    for s in get_sessions(username):
        if s["date"] == date_str:
            return s
    return None


def upsert_session(username: str, session: dict):
    """セッションを保存（同じ日付があれば上書き）。"""
    data = _load(WORKOUTS_FILE)
    if username not in data:
        data[username] = []
    for i, s in enumerate(data[username]):
        if s["date"] == session["date"]:
            data[username][i] = session
            _save(WORKOUTS_FILE, data)
            return
    data[username].append(session)
    _save(WORKOUTS_FILE, data)
