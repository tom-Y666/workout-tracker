import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
from datetime import date
import time

import auth
import data

IDLE_TIMEOUT = 30 * 60  # 30分（秒）

st.set_page_config(page_title="筋トレ記録", page_icon="💪", layout="wide")

for key, default in [("logged_in", False), ("username", "")]:
    if key not in st.session_state:
        st.session_state[key] = default

auth.init_from_secrets()  # Secretsから初期ユーザーを自動作成

# ── ブラウザリロード時のセッション復元 ──────────────────────────
# st.session_state はリロードで失われるため、URLに載せたトークン(?session=...)を
# sessions.json と突き合わせ、IDLE_TIMEOUT以内の活動があれば再ログインなしで復元する。
if not st.session_state.logged_in:
    _qp_token = st.query_params.get("session")
    if _qp_token:
        _restored_user = auth.resume_session(_qp_token, IDLE_TIMEOUT)
        if _restored_user:
            st.session_state.logged_in = True
            st.session_state.username = _restored_user
            st.session_state.session_token = _qp_token
            st.session_state.last_activity = time.time()
        else:
            st.query_params.clear()

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
                    token = auth.create_session(username)
                    st.session_state.session_token = token
                    st.query_params["session"] = token  # リロード時の継続用にURLへ保持
                    data.init_default_exercises(username)  # 種目が0件ならテンプレートから初期投入
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


def _set_shadow(i: int, j: int, w, r):
    """shadowストレージに値を保存（Streamlitに削除されない通常のdict）。"""
    st.session_state.setdefault("rec_shadow", {})[f"{i}_{j}"] = {"w": w, "r": r}


def _init_rec_state(username: str, date_str: str):
    _clear_rec_widget_keys()
    st.session_state.rec_shadow = {}
    ex_defs = data.get_exercises(username)
    ex_default_map = {e["name"]: float(e.get("default_weight", 0)) for e in ex_defs}

    existing = data.get_session_by_date(username, date_str)
    if existing:
        st.session_state.rec_ex_names = [e["name"] for e in existing["exercises"]]
        st.session_state.rec_ex_sets = [len(e["sets"]) for e in existing["exercises"]]
        for i, ex in enumerate(existing["exercises"]):
            for j, s in enumerate(ex["sets"]):
                saved_w = float(s["weight"])
                # draft かつ重量未入力(0)の場合は種目マスタのデフォルト重量を使う
                if existing["status"] == "draft" and saved_w == 0:
                    w = ex_default_map.get(ex["name"], 0.0)
                else:
                    w = saved_w
                r = int(s["reps"]) if s["reps"] else None
                st.session_state[f"rec_w_{i}_{j}"] = w
                st.session_state[f"rec_r_{i}_{j}"] = r
                _set_shadow(i, j, w, r)
    else:
        defaults = [e for e in ex_defs if e.get("status", STATUS_REQUIRED) != STATUS_OPTIONAL]
        st.session_state.rec_ex_names = [e["name"] for e in defaults]
        st.session_state.rec_ex_sets = [e.get("default_sets", 1) for e in defaults]
        for i, e in enumerate(defaults):
            for j in range(e.get("default_sets", 1)):
                w = float(e.get("default_weight", 0))
                st.session_state[f"rec_w_{i}_{j}"] = w
                st.session_state[f"rec_r_{i}_{j}"] = None
                _set_shadow(i, j, w, None)
    st.session_state.rec_current_date = date_str


def _ex_has_changes(i: int, ex_def: dict) -> bool:
    """種目iのいずれかのセットがデフォルト値から変更されているか。"""
    num_sets = st.session_state.rec_ex_sets[i]
    default_w = float(ex_def.get("default_weight", 0))
    for j in range(num_sets):
        w = st.session_state.get(f"rec_w_{i}_{j}", default_w)
        r = st.session_state.get(f"rec_r_{i}_{j}") or 0
        if w != default_w or r != 0:
            return True
    return False


def _set_has_changes(i: int, j: int, ex_def: dict) -> bool:
    """セット(i,j)がデフォルト値から変更されているか。"""
    default_w = float(ex_def.get("default_weight", 0))
    w = st.session_state.get(f"rec_w_{i}_{j}", default_w)
    r = st.session_state.get(f"rec_r_{i}_{j}") or 0
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
                "weight": st.session_state.get(f"rec_w_{i}_{j}") or 0.0,
                "reps": st.session_state.get(f"rec_r_{i}_{j}") or 0,
            })
        exercises.append({"name": name, "sets": sets})
    return {"date": date_str, "status": status, "exercises": exercises}


def page_record(username: str, date_str: str):
    # ── インターバルアラーム ──────────────────────────────────────
    st.markdown("##### ⏱ インターバルアラーム")
    components.html("""
        <style>
        body{background:transparent;font-family:sans-serif;margin:0;}
        #disp{font-size:2.2rem;font-weight:bold;text-align:center;color:#fff;padding:6px 0 2px;display:none;}
        #alarm-msg{text-align:center;color:#ff4b4b;font-weight:bold;font-size:0.95rem;min-height:1.4em;margin-bottom:2px;}
        .inputs{display:flex;align-items:center;justify-content:center;gap:6px;margin:4px 0 6px;}
        .inputs input{width:52px;padding:8px 2px;font-size:1rem;text-align:center;
            border-radius:6px;border:1px solid #555;background:#1a1a2e;color:#fff;}
        .inputs label{color:#bbb;font-size:0.9rem;}
        .btns{display:flex;gap:8px;justify-content:center;}
        button{padding:7px 22px;border-radius:8px;border:none;cursor:pointer;font-size:0.95rem;font-weight:600;}
        #bstart{background:#ff4b4b;color:#fff;}
        #breset{background:#555;color:#fff;}
        </style>

        <div id="disp">02:00</div>
        <div id="alarm-msg"></div>
        <div class="inputs" id="time-inputs">
            <input type="number" id="inp-min" min="0" max="60" value="2">
            <label>分</label>
            <input type="number" id="inp-sec" min="0" max="59" value="0">
            <label>秒</label>
        </div>
        <div class="btns">
            <button id="bstart" onclick="startTimer()">▶ スタート</button>
            <button id="breset" onclick="resetTimer()">↺ リセット</button>
        </div>

        <script>
        const KEY = 'wt_alarm';
        // カウントダウンアラーム。タイムスタンプ方式でバックグラウンド時もズレなし。
        let deadline = null;   // 0:00になるms epoch
        let targetSecs = 120;  // 設定した秒数（リセット時に戻る値）
        let running = false;
        let alarming = false;
        let ticker = null;
        let alarmTicker = null;
        let audioCtx = null;
        let scheduledNodes = [];  // バックグラウンド対策: 事前スケジュール済みノード

        function getAudioCtx() {
            if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            return audioCtx;
        }
        function playBeep() {
            try {
                const ctx = getAudioCtx();
                if (ctx.state === 'suspended') ctx.resume();
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.connect(gain); gain.connect(ctx.destination);
                osc.type = 'sine'; osc.frequency.value = 880;
                gain.gain.setValueAtTime(0.5, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.7);
                osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.7);
            } catch(e) {}
        }
        function fmt(ms) {
            const s = Math.max(0, Math.ceil(ms / 1000));
            return String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0');
        }
        function save() {
            localStorage.setItem(KEY, JSON.stringify({running, alarming, deadline, targetSecs}));
        }
        function getInputSecs() {
            const m = Math.max(0, Math.min(60, parseInt(document.getElementById('inp-min').value) || 0));
            const s = Math.max(0, Math.min(59, parseInt(document.getElementById('inp-sec').value) || 0));
            return m * 60 + s;
        }
        function setInputs(secs) {
            document.getElementById('inp-min').value = Math.floor(secs / 60);
            document.getElementById('inp-sec').value = secs % 60;
        }
        function showRunningUI() {
            document.getElementById('disp').style.display = 'block';
            document.getElementById('time-inputs').style.display = 'none';
            document.getElementById('bstart').style.display = 'none';
        }
        function showStoppedUI() {
            document.getElementById('disp').style.display = 'none';
            document.getElementById('time-inputs').style.display = 'flex';
            document.getElementById('bstart').style.display = '';
            document.getElementById('alarm-msg').textContent = '';
            document.getElementById('disp').style.color = '#fff';
        }
        function tick() {
            if (!running) return;
            const rem = deadline - Date.now();
            if (rem <= 0) {
                document.getElementById('disp').textContent = '00:00';
                clearInterval(ticker); ticker = null;
                running = false; alarming = true;
                save(); fireAlarm();
                return;
            }
            document.getElementById('disp').textContent = fmt(rem);
        }
        function fireAlarm() {
            document.getElementById('disp').style.color = '#ff4b4b';
            document.getElementById('alarm-msg').textContent = '⏰ 時間です！';
            playBeep();
            alarmTicker = setInterval(playBeep, 3000);
        }
        function cancelScheduledNodes() {
            scheduledNodes.forEach(n => { try { n.stop(); } catch(e) {} });
            scheduledNodes = [];
        }
        function startTimer() {
            const secs = getInputSecs();
            if (secs <= 0) return;
            // iOS対策: ユーザー操作中（同期処理内）に無音バッファを再生してAudioContextをアンロック
            try {
                const ctx = getAudioCtx();
                const buf = ctx.createBuffer(1, 1, 22050);
                const src = ctx.createBufferSource();
                src.buffer = buf;
                src.connect(ctx.destination);
                src.start(0);
                ctx.resume();
            } catch(e) {}
            targetSecs = secs;
            deadline = Date.now() + secs * 1000;
            running = true; alarming = false;
            clearInterval(alarmTicker); alarmTicker = null;
            // バックグラウンド対策: アラーム音をオーディオスレッドに事前スケジュール
            // (JSスレッドが止まっても発火する可能性がある)
            cancelScheduledNodes();
            try {
                const ctx = getAudioCtx();
                const alarmAt = ctx.currentTime + secs;
                for (let i = 0; i < 5; i++) {
                    const t = alarmAt + i * 3;
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.connect(gain); gain.connect(ctx.destination);
                    osc.type = 'sine'; osc.frequency.value = 880;
                    gain.gain.setValueAtTime(0.5, t);
                    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.7);
                    osc.start(t); osc.stop(t + 0.7);
                    scheduledNodes.push(osc);
                }
            } catch(e) {}
            showRunningUI();
            save(); tick();
            ticker = setInterval(tick, 500);
        }
        function resetTimer() {
            running = false; alarming = false;
            clearInterval(ticker); ticker = null;
            clearInterval(alarmTicker); alarmTicker = null;
            cancelScheduledNodes();
            deadline = null;
            document.getElementById('disp').textContent = fmt(targetSecs * 1000);
            showStoppedUI();
            save();
        }
        // ページ読み込み・タブ復帰時の状態復元
        (function load() {
            try {
                const d = JSON.parse(localStorage.getItem(KEY) || '{}');
                if (d.targetSecs) { targetSecs = d.targetSecs; setInputs(targetSecs); }
                if (d.alarming) {
                    showRunningUI();
                    document.getElementById('disp').textContent = '00:00';
                    alarming = true; fireAlarm();
                } else if (d.running && d.deadline) {
                    deadline = d.deadline;
                    const rem = deadline - Date.now();
                    if (rem > 0) {
                        running = true; showRunningUI();
                        tick(); ticker = setInterval(tick, 500);
                    } else {
                        // バックグラウンド中に時間切れ
                        showRunningUI();
                        document.getElementById('disp').textContent = '00:00';
                        alarming = true; fireAlarm();
                    }
                } else {
                    document.getElementById('disp').textContent = fmt(targetSecs * 1000);
                }
            } catch(e) {
                document.getElementById('disp').textContent = fmt(targetSecs * 1000);
            }
        })();
        // タブ復帰時に即時反映（バックグラウンド中の時間切れも検出）
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) return;
            if (running) tick();
            else if (alarming) playBeep();
        });
        </script>
        """, height=165)

    ex_defs = data.get_exercises(username)
    if not ex_defs:
        st.warning("種目が登録されていません。先に「種目管理」で種目を追加してください。")
        return

    # 日付が変わった時だけ再初期化（タブ切り替えによるキー消失はshadowで対処）
    if st.session_state.get("rec_current_date") != date_str:
        _init_rec_state(username, date_str)
        st.rerun()  # widgetが正しいデフォルト値を表示するために必要

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

        shadow = st.session_state.get("rec_shadow", {})
        default_w = float(ex_def.get("default_weight", 0))

        for j in range(num_sets):
            s_key = f"{i}_{j}"
            # widgetキーが消えていたらshadowから復元（Streamlitがタブ切り替え時に削除するため）
            if f"rec_w_{i}_{j}" not in st.session_state:
                st.session_state[f"rec_w_{i}_{j}"] = shadow.get(s_key, {}).get("w", default_w)
            if f"rec_r_{i}_{j}" not in st.session_state:
                st.session_state[f"rec_r_{i}_{j}"] = shadow.get(s_key, {}).get("r", None)

            rc = st.columns([0.7, 2.2, 0.4, 2.2, 0.6])
            rc[0].markdown(f"<div style='padding-top:8px;font-size:0.85rem;'>#{j+1}</div>",
                           unsafe_allow_html=True)
            rc[1].number_input("重量(kg)", min_value=0.0, max_value=500.0, step=2.5,
                               key=f"rec_w_{i}_{j}", label_visibility="collapsed")
            rc[2].markdown("<div style='padding-top:8px;text-align:center;'>×</div>",
                           unsafe_allow_html=True)
            rc[3].number_input("回数", min_value=0, max_value=100, step=1,
                               key=f"rec_r_{i}_{j}", label_visibility="collapsed", value=None)

            # widgetが描画されたらshadowを更新（次のタブ切り替えに備える）
            _set_shadow(i, j,
                        st.session_state.get(f"rec_w_{i}_{j}"),
                        st.session_state.get(f"rec_r_{i}_{j}"))
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
                    w_val = st.session_state.get(f"rec_w_{i}_{j}") or 0
                    r_val = st.session_state.get(f"rec_r_{i}_{j}") or 0
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
                st.session_state[f"rec_r_{i}_{new_j}"] = None
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
                    st.session_state[f"rec_r_{new_i}_{j}"] = None
                st.rerun()

    st.divider()

    # バリデーション（必須のみチェック）
    required_names = {e["name"] for e in ex_defs if e.get("status") == STATUS_REQUIRED}
    all_required_filled = all(
        (st.session_state.get(f"rec_r_{i}_{j}") or 0) > 0
        for i, name in enumerate(st.session_state.rec_ex_names)
        if name in required_names
        for j in range(st.session_state.rec_ex_sets[i])
    )

    st.markdown('<div class="rec-footer-anchor"></div>', unsafe_allow_html=True)
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

    # ── セッションタイムアウト（30分無操作で自動ログアウト）────
    if "last_activity" not in st.session_state:
        st.session_state.last_activity = time.time()
    elif time.time() - st.session_state.last_activity > IDLE_TIMEOUT:
        auth.delete_session(st.session_state.get("session_token"))
        st.query_params.clear()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.warning("30分間操作がなかったため、自動ログアウトしました。")
        st.rerun()
    st.session_state.last_activity = time.time()
    # サーバー側にも最終活動時刻を記録（リロード時の30分判定に使用。書き込みは間引く）
    auth.touch_session(st.session_state.get("session_token"))

    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "record"
    if "nav_date" not in st.session_state:
        st.session_state.nav_date = date.today()

    active = st.session_state.active_tab
    prev_tab = st.session_state.get("prev_tab", active)

    # ── 記録タブを離れるとき入力中データを自動下書き保存 ────────
    if prev_tab == "record" and active != "record":
        if st.session_state.get("rec_ex_names") and st.session_state.get("rec_current_date"):
            draft = _build_session_from_state(st.session_state.rec_current_date, "draft")
            data.upsert_session(username, draft)
    st.session_state.prev_tab = active

    # ── CSS：全横並びブロックの折り返し禁止（paddingは変えない）──
    st.markdown("""
    <style>
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
    [data-testid="stColumn"] { min-width: 0 !important; overflow: hidden; }

    /* 途中保存・登録ボタンを画面下部に固定 */
    /* stVerticalBlockの直接子の中で .rec-footer-anchor を含む要素の直後の兄弟要素を対象にする
       （ラッパーdivの有無を問わず動作する） */
    [data-testid="stVerticalBlock"] > *:has(.rec-footer-anchor) + * {
        position: fixed !important;
        bottom: 0 !important;
        left: 0 !important;
        right: 0 !important;
        z-index: 999 !important;
        background: rgba(14, 17, 23, 0.97) !important;
        padding: 10px 2rem !important;
        border-top: 1px solid rgba(255, 255, 255, 0.1) !important;
        backdrop-filter: blur(8px) !important;
    }
    /* フッターに隠れないよう下部にパディング */
    [data-testid="stMainBlockContainer"] {
        padding-bottom: 90px !important;
    }

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
            auth.delete_session(st.session_state.get("session_token"))
            st.query_params.clear()
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
