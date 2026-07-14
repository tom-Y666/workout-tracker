"""
ローカルのJSONファイル（users.json, exercises.json, workouts.json）を
Supabaseに一度だけ投入するための移行スクリプト。

使い方:
  python migrate_to_supabase.py

前提: .streamlit/secrets.toml に [supabase] の url/key が設定済みであること。
"""
import json
import os

import data
from supabase_client import get_client

USERS_FILE = "users.json"
EXERCISES_FILE = "exercises.json"
WORKOUTS_FILE = "workouts.json"


def _load(filename: str) -> dict:
    if not os.path.exists(filename):
        return {}
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_users():
    users = _load(USERS_FILE)
    if not users:
        print("users.json が見つからないためスキップ")
        return
    client = get_client()
    for username, info in users.items():
        client.table("users").upsert({
            "username": username,
            "password": info["password"],  # 既にハッシュ化済みの値をそのまま移す
            "failed_attempts": info.get("failed_attempts", 0),
            "locked": info.get("locked", False),
        }, on_conflict="username").execute()
        print(f"user: {username}")


def _normalize_exercise(e: dict) -> dict:
    # 古いスキーマ（"required": bool）は "status" に変換する
    if "status" in e:
        return e
    status = "⭐ 必須" if e.get("required") else "○ 任意"
    return {"name": e["name"], "default_sets": e.get("default_sets", 1),
             "default_weight": e.get("default_weight", 0.0), "status": status}


def migrate_exercises():
    exercises = _load(EXERCISES_FILE)
    if not exercises:
        print("exercises.json が見つからないためスキップ")
        return
    for username, ex_list in exercises.items():
        for e in ex_list:
            data.upsert_exercise(username, _normalize_exercise(e))
        print(f"exercises: {username} ({len(ex_list)}件)")


def migrate_workouts():
    workouts = _load(WORKOUTS_FILE)
    if not workouts:
        print("workouts.json が見つからないためスキップ")
        return
    for username, sessions in workouts.items():
        for s in sessions:
            data.upsert_session(username, s)
        print(f"workouts: {username} ({len(sessions)}件)")


if __name__ == "__main__":
    migrate_users()
    migrate_exercises()
    migrate_workouts()
    print("完了しました")
