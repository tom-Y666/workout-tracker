import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

import auth
import data

st.set_page_config(page_title="筋トレ記録", page_icon="💪", layout="wide")

for key, default in [("logged_in", False), ("username", "")]:
    if key not in st.session_state:
        st.session_state[key] = default

auth.init_from_secrets()  # Secretsから初期ユーザーを自動作成

# 種目区分の定義
STATUS_REQUIRED = "⭐ 必須"
STATUS_CONDITIONAL = "🔶 条件付き必須"
STATUS_OPTIONAL = "○ 任意"
STATUS_OPTIONS = [STATUS_REQUIRED, STATUS_CONDITIONAL, STATUS_OPTIONAL]


# ══════════════════════════════════════════════════════════════════
# ログイン画面
# ══════════════════════════════════════════════════════════════════

def show_login():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("💪 筋トレ記録")
        st.divider()
        with st.form("login_form"):
            username = st.text_input("ユーザー名")
            password = st.text_input("パスワード", type="password")
            if st.form_submit_button("ログイン", use_container_width=True, type="primary"):
                ok, msg = auth.authenticate(username, password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error(msg)


# ══════════════════════════════════════════════════════════════════
# 画面1：記録する
# ══════════════════════════════════════════════════════════════════

def _clear_rec_widget_keys():
    for k in list(st.session_state.keys()):
        if k.startswith("rec_w_") or k.startswith("rec_r_"):
            del st.session_state[k]


def _init_rec_state(username: str, date_str: str):
    _clear_rec_widget_keys()
    existing = data.get_session_by_date(username, date_str)
    if existing:
        st.session_state.rec_ex_names = [e["name"] for e in existing["exercises"]]
        st.session_state.rec_ex_sets = [len(e["sets"]) for e in existing["exercises"]]
        for i, ex in enumerate(existing["exercises"]):
            for j, s in enumerate(ex["sets"]):
                st.session_state[f"rec_w_{i}_{j}"] = float(s["weight"])
                st.session_state[f"rec_r_{i}_{j}"] = int(s["reps"])
    else:
        ex_defs = data.get_exercises(username)
        defaults = [e for e in ex_defs if e.get("status", STATUS_REQUIRED) != STATUS_OPTIONAL]
        st.session_state.rec_ex_names = [e["name"] for e in defaults]
        st.session_state.rec_ex_sets = [e.get("default_sets", 1) for e in defaults]
        for i, e in enumerate(defaults):
            for j in range(e.get("default_sets", 1)):
                st.session_state[f"rec_w_{i}_{j}"] = float(e.get("default_weight", 0))
                st.session_state[f"rec_r_{i}_{j}"] = 0
    st.session_state.rec_current_date = date_str


def _ex_has_changes(i: int, ex_def: dict) -> bool:
    """種目iのいずれかのセットがデフォルト値から変更されているか。"""
    num_sets = st.session_state.rec_ex_sets[i]
    default_w = float(ex_def.get("default_weight", 0))
    for j in range(num_sets):
        w = st.session_state.get(f"rec_w_{i}_{j}", default_w)
        r = st.session_state.get(f"rec_r_{i}_{j}", 0)
        if w != default_w or r != 0:
            return True
    return False


def _set_has_changes(i: int, j: int, ex_def: dict) -> bool:
    """セット(i,j)がデフォルト値から変更されているか。"""
    default_w = float(ex_def.get("default_weight", 0))
    w = st.session_state.get(f"rec_w_{i}_{j}", default_w)
    r = st.session_state.get(f"rec_r_{i}_{j}", 0)
    return w != default_w or r != 0


def _do_delete_ex(i: int):
    st.session_state.rec_ex_names.pop(i)
    st.session_state.rec_ex_sets.pop(i)
    st.session_state.pop("pending_del_ex", None)


def _do_delete_set(i: int, j: int):
    num_sets = st.session_state.rec_ex_sets[i]
    for k in range(j, num_sets - 1):
        st.session_state[f"rec_w_{i}_{k}"] = st.session_state.get(f"rec_w_{i}_{k+1}", 0.0)
        st.session_state[f"rec_r_{i}_{k}"] = st.session_state.get(f"rec_r_{i}_{k+1}", 0)
    st.session_state.rec_ex_sets[i] -= 1
    st.session_state.pop("pending_del_set", None)


def _build_session_from_state(date_str: str, status: str) -> dict:
    exercises = []
    for i, name in enumerate(st.session_state.rec_ex_names):
        sets = []
        for j in range(st.session_state.rec_ex_sets[i]):
            sets.append({
                "weight": st.session_state.get(f"rec_w_{i}_{j}", 0.0),
                "reps": st.session_state.get(f"rec_r_{i}_{j}", 0),
            })
        exercises.append({"name": name, "sets": sets})
    return {"date": date_str, "status": status, "exercises": exercises}


def page_record(username: str, date_str: str):
    ex_defs = data.get_exercises(username)
    if not ex_defs:
        st.warning("種目が登録されていません。先に「種目管理」で種目を追加してください。")
        return

    if st.session_state.get("rec_current_date") != date_str:
        _init_rec_state(username, date_str)

    # 種目ステータスマップ
    status_map = {e["name"]: e.get("status", STATUS_REQUIRED) for e in ex_defs}

    # 各種目の入力
    for i, ex_name in enumerate(st.session_state.rec_ex_names):
        ex_status = status_map.get(ex_name, STATUS_OPTIONAL)
        ex_def = next((e for e in ex_defs if e["name"] == ex_name), {})

        col_h, col_d = st.columns([6, 1])
        with col_h:
            icon = "⭐ " if ex_status == STATUS_REQUIRED else ("🔶 " if ex_status == STATUS_CONDITIONAL else "")
            st.markdown(f"#### {icon}{ex_name}")
        with col_d:
            if st.session_state.get("pending_del_ex") == i:
                # 確認UI
                pass  # 後述
            else:
                if st.button("🗑️", key=f"rec_del_ex_{i}", help="種目を削除"):
                    if _ex_has_changes(i, ex_def):
                        st.session_state.pending_del_ex = i
                        st.rerun()
                    else:
                        _do_delete_ex(i)
                        st.rerun()

        # 種目削除の確認ダイアログ（種目ヘッダー直下に表示）
        if st.session_state.get("pending_del_ex") == i:
            with st.container(border=True):
                st.warning(f"**「{ex_name}」** の入力内容が失われます。削除しますか？")
                cc1, cc2 = st.columns(2)
                if cc1.button("はい、削除する", key=f"confirm_del_ex_{i}", type="primary", use_container_width=True):
                    _do_delete_ex(i)
                    st.rerun()
                if cc2.button("キャンセル", key=f"cancel_del_ex_{i}", use_container_width=True):
                    st.session_state.pop("pending_del_ex", None)
                    st.rerun()

        num_sets = st.session_state.rec_ex_sets[i]

        for j in range(num_sets):
            if f"rec_w_{i}_{j}" not in st.session_state:
                st.session_state[f"rec_w_{i}_{j}"] = float(ex_def.get("default_weight", 0))
            if f"rec_r_{i}_{j}" not in st.session_state:
                st.session_state[f"rec_r_{i}_{j}"] = 0

            rc = st.columns([0.7, 2.2, 0.4, 2.2, 0.6])
            rc[0].markdown(f"<div style='padding-top:8px;font-size:0.85rem;'>#{j+1}</div>",
                           unsafe_allow_html=True)
            rc[1].number_input("重量(kg)", min_value=0.0, max_value=500.0, step=2.5,
                               key=f"rec_w_{i}_{j}", label_visibility="collapsed")
            rc[2].markdown("<div style='padding-top:8px;text-align:center;'>×</div>",
                           unsafe_allow_html=True)
            rc[3].number_input("回数", min_value=0, max_value=100, step=1,
                               key=f"rec_r_{i}_{j}", label_visibility="collapsed")
            if num_sets > 1:
                pending_set = st.session_state.get("pending_del_set")
                if pending_set == (i, j):
                    rc[4].write("")  # ボタン位置を保持
                else:
                    if rc[4].button("－", key=f"rec_del_set_{i}_{j}"):
                        if _set_has_changes(i, j, ex_def):
                            st.session_state.pending_del_set = (i, j)
                            st.rerun()
                        else:
                            _do_delete_set(i, j)
                            st.rerun()

            # セット削除の確認ダイアログ
            if st.session_state.get("pending_del_set") == (i, j):
                with st.container(border=True):
                    w_val = st.session_state.get(f"rec_w_{i}_{j}", 0)
                    r_val = st.session_state.get(f"rec_r_{i}_{j}", 0)
                    st.warning(f"セット {j+1}（{w_val}kg × {r_val}回）の入力内容が失われます。削除しますか？")
                    sc1, sc2 = st.columns(2)
                    if sc1.button("はい、削除する", key=f"confirm_del_set_{i}_{j}", type="primary", use_container_width=True):
                        _do_delete_set(i, j)
                        st.rerun()
                    if sc2.button("キャンセル", key=f"cancel_del_set_{i}_{j}", use_container_width=True):
                        st.session_state.pop("pending_del_set", None)
                        st.rerun()

        if num_sets < 10:
            if st.button("＋ セットを追加", key=f"rec_add_set_{i}"):
                new_j = num_sets
                st.session_state[f"rec_w_{i}_{new_j}"] = float(ex_def.get("default_weight", 0))
                st.session_state[f"rec_r_{i}_{new_j}"] = 0
                st.session_state.rec_ex_sets[i] += 1
                st.rerun()

        st.divider()

    # 種目追加（一番下）
    registered_names = set(st.session_state.rec_ex_names)
    addable = ["-- 種目を選択 --"] + [e["name"] for e in ex_defs if e["name"] not in registered_names]
    ac1, ac2 = st.columns([3, 1])
    with ac1:
        add_choice = st.selectbox("種目を追加", addable, key="rec_add_select", label_visibility="collapsed")
    with ac2:
        if st.button("＋ 種目を追加", use_container_width=True):
            if add_choice != "-- 種目を選択 --":
                ex_def = next(e for e in ex_defs if e["name"] == add_choice)
                new_i = len(st.session_state.rec_ex_names)
                num_sets = ex_def.get("default_sets", 1)
                st.session_state.rec_ex_names.append(add_choice)
                st.session_state.rec_ex_sets.append(num_sets)
                for j in range(num_sets):
                    st.session_state[f"rec_w_{new_i}_{j}"] = float(ex_def.get("default_weight", 0))
                    st.session_state[f"rec_r_{new_i}_{j}"] = 0
                st.rerun()

    st.divider()

    # バリデーション（必須のみチェック）
    required_names = {e["name"] for e in ex_defs if e.get("status") == STATUS_REQUIRED}
    all_required_filled = all(
        st.session_state.get(f"rec_r_{i}_{j}", 0) > 0
        for i, name in enumerate(st.session_state.rec_ex_names)
        if name in required_names
        for j in range(st.session_state.rec_ex_sets[i])
    )

    bc1, bc2 = st.columns(2)
    with bc1:
        if st.button("途中保存", use_container_width=True):
            data.upsert_session(username, _build_session_from_state(date_str, "draft"))
            st.success("途中保存しました")
    with bc2:
        if not all_required_filled:
            st.button("登録", use_container_width=True, disabled=True, type="primary")
            st.caption("⚠️ ⭐必須種目の回数をすべて入力してください")
        else:
            if st.button("登録 ✅", use_container_width=True, type="primary"):
                data.upsert_session(username, _build_session_from_state(date_str, "saved"))
                st.success("登録しました！")
                st.rerun()

    # 登録済みサマリー
    session = data.get_session_by_date(username, date_str)
    if session and session["status"] == "saved":
        st.divider()
        st.subheader(f"📋 {date_str} のトレーニング記録")
        for ex in session["exercises"]:
            st.markdown(f"**{ex['name']}**")
            for k, s in enumerate(ex["sets"], 1):
                st.write(f"　セット {k}：{s['weight']} kg × {s['reps']} 回")
        total_vol = sum(s["weight"] * s["reps"] for ex in session["exercises"] for s in ex["sets"])
        st.metric("本日の総ボリューム", f"{total_vol:.0f} kg")


# ══════════════════════════════════════════════════════════════════
# 画面2：種目管理
# ══════════════════════════════════════════════════════════════════

def page_exercises(username: str):
    st.subheader("種目を追加")

    with st.form("ex_form"):
        col1, col2, col3 = st.columns([3, 1.5, 1.5])
        name = col1.text_input("種目名")
        default_sets = col2.number_input("デフォルトセット数", min_value=1, max_value=10, value=3, step=1)
        default_weight = col3.number_input("デフォルト重量 (kg)", min_value=0.0, max_value=500.0, value=60.0, step=2.5)

        st.markdown("**区分**")
        status = st.radio(
            "区分",
            STATUS_OPTIONS,
            index=0,
            horizontal=True,
            label_visibility="collapsed",
            help="必須：登録ボタンに入力必須 ／ 条件付き必須：デフォルト表示だが未入力でも登録可 ／ 任意：自分で追加した時のみ表示",
        )

        if st.form_submit_button("追加 ✅", use_container_width=True):
            if not name.strip():
                st.error("種目名を入力してください")
            else:
                data.upsert_exercise(username, {
                    "name": name.strip(),
                    "default_sets": int(default_sets),
                    "default_weight": float(default_weight),
                    "status": status,
                })
                st.success(f"「{name}」を登録しました")
                st.rerun()

    st.divider()
    st.subheader("登録済み種目")

    exercises = data.get_exercises(username)
    if not exercises:
        st.info("まだ種目が登録されていません")
        return

    header = st.columns([3, 1.5, 1.5, 2, 1])
    for col, label in zip(header, ["種目名", "セット数", "重量 (kg)", "区分", ""]):
        col.markdown(f"**{label}**")

    for ex in exercises:
        row = st.columns([3, 1.5, 1.5, 2, 1])
        row[0].write(ex["name"])
        row[1].write(ex["default_sets"])
        row[2].write(ex["default_weight"])
        row[3].write(ex.get("status", STATUS_REQUIRED))
        if row[4].button("削除", key=f"del_ex_{ex['name']}"):
            data.delete_exercise(username, ex["name"])
            st.rerun()


# ══════════════════════════════════════════════════════════════════
# 画面3：過去の記録
# ══════════════════════════════════════════════════════════════════

def page_history(username: str):
    sessions = data.get_sessions(username)
    saved = [s for s in sessions if s["status"] == "saved"]

    if not saved:
        st.info("まだ登録済みの記録がありません")
        return

    rows = []
    for s in saved:
        for ex in s["exercises"]:
            for k, set_ in enumerate(ex["sets"], 1):
                rows.append({
                    "date": s["date"],
                    "exercise": ex["name"],
                    "set": k,
                    "weight": set_["weight"],
                    "reps": set_["reps"],
                    "volume": set_["weight"] * set_["reps"],
                })
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])

    exercise_names = df["exercise"].unique().tolist()
    selected = st.selectbox("種目を選択", exercise_names)

    df_ex = df[df["exercise"] == selected].copy()
    df_day = df_ex.groupby("date").agg(
        max_weight=("weight", "max"),
        total_volume=("volume", "sum"),
    ).reset_index()

    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.line(df_day, x="date", y="max_weight",
                       title=f"{selected} ー 最大重量推移",
                       labels={"date": "日付", "max_weight": "最大重量 (kg)"},
                       markers=True)
        st.plotly_chart(fig1, use_container_width=True)
    with col2:
        fig2 = px.bar(df_day, x="date", y="total_volume",
                      title=f"{selected} ー 総ボリューム推移",
                      labels={"date": "日付", "total_volume": "総ボリューム (kg)"})
        st.plotly_chart(fig2, use_container_width=True)

    if len(df_day) >= 2:
        m1, m2, m3 = st.columns(3)
        m1.metric("最高重量", f"{df_day['max_weight'].max()} kg")
        m2.metric("初回重量", f"{df_day.iloc[0]['max_weight']} kg")
        last_w = df_day.iloc[-1]["max_weight"]
        m3.metric("最新重量", f"{last_w} kg", delta=f"{last_w - df_day.iloc[0]['max_weight']:+.1f} kg（初回比）")

    st.divider()
    for s in saved:
        if not any(ex["name"] == selected for ex in s["exercises"]):
            continue
        with st.expander(f"📅 {s['date']}"):
            for ex in s["exercises"]:
                if ex["name"] != selected:
                    continue
                for k, set_ in enumerate(ex["sets"], 1):
                    st.write(f"　セット {k}：{set_['weight']} kg × {set_['reps']} 回")


# ══════════════════════════════════════════════════════════════════
# メイン
# ══════════════════════════════════════════════════════════════════

def show_main():
    username = st.session_state.username

    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "record"
    if "nav_date" not in st.session_state:
        st.session_state.nav_date = date.today()

    active = st.session_state.active_tab

    # ── CSS：全横並びブロックの折り返し禁止（paddingは変えない）──
    st.markdown("""
    <style>
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
    [data-testid="stColumn"] { min-width: 0 !important; overflow: hidden; }

    /* radioをタブ風に */
    [data-testid="stRadio"] > div[role="radiogroup"] {
        display: flex !important; gap: 6px !important;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] > label {
        flex: 1 !important; text-align: center !important;
        padding: 8px 4px !important; border-radius: 6px !important;
        border: 1px solid rgba(255,255,255,0.15) !important; cursor: pointer !important;
        white-space: nowrap !important; overflow: hidden !important;
        text-overflow: ellipsis !important;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) {
        background: #ff4b4b !important; border-color: #ff4b4b !important; font-weight: 600 !important;
    }
    [data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── 1行目：タブ（radioで横並び保証）────────────────────────
    TABS = {"📝 記録する": "record", "🏋️ 種目管理": "exercises", "📈 過去の記録": "history"}
    labels = list(TABS.keys())
    current_label = next(k for k, v in TABS.items() if v == active)
    selected = st.radio("", labels, index=labels.index(current_label),
                        horizontal=True, label_visibility="collapsed", key="nav_radio")
    if TABS[selected] != active:
        st.session_state.active_tab = TABS[selected]
        st.rerun()

    # ── 2行目：日付・ユーザー名・ログアウト ──────────────────────
    c_date, c_user, c_logout = st.columns([2, 4, 1])
    with c_date:
        st.session_state.nav_date = st.date_input(
            "", value=st.session_state.nav_date,
            label_visibility="collapsed", key="nav_date_input",
        )
    c_user.markdown(
        f'<div style="text-align:right;padding-top:6px;font-size:0.85rem;color:#888;">'
        f'👤 {username}</div>', unsafe_allow_html=True,
    )
    with c_logout:
        if st.button("🚪", help="ログアウト", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()

    st.divider()

    date_str = str(st.session_state.nav_date)

    if active == "record":
        page_record(username, date_str)
    elif active == "exercises":
        page_exercises(username)
    else:
        page_history(username)


if st.session_state.logged_in:
    show_main()
else:
    show_login()
