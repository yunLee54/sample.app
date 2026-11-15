"""영어 단어 학습 앱 (Streamlit)

실행:  streamlit run app.py
준비:  Voca_3000.csv 를 app.py 와 같은 폴더에 두세요.
"""
import html
import json
import random
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DATA_FILE = Path(__file__).parent / "Voca_3000.csv"

# 화면에 보이는 이름 -> CSV의 Level 값 (이 표만 바꾸면 수준 이름/구성이 바뀝니다)
LEVELS = {"초등": "Elementary", "중·고등": "MidHigh", "확장": "Extended"}
LEVEL_NAMES = list(LEVELS)

HOME, READING = "🏠 시작", "📖 읽기"
PAGES = [HOME, *LEVEL_NAMES, READING]

M_LIST, M_CARD = "📋 단어 목록", "🃏 플래시카드"
M_EN2KO, M_KO2EN, M_SPELL = "🔤 영→한 퀴즈", "🔁 한→영 퀴즈", "✍️ 철자 쓰기"
M_REVIEW = "🔖 복습(표시한 단어)"
MODES = [M_LIST, M_CARD, M_EN2KO, M_KO2EN, M_SPELL, M_REVIEW]
MODE_KIND = {M_EN2KO: "en2ko", M_KO2EN: "ko2en", M_SPELL: "spell"}
KIND_LABEL = {"en2ko": "영어 → 한국어", "ko2en": "한국어 → 영어", "spell": "철자 쓰기"}

DONT_KNOW = "잘 모르겠어요"
DIAG_PER_LEVEL = 5  # 수준별 진단 문항 수
PASS_SCORE = 4      # 이 점수 이상이면 다음 수준 추천


# ───────────────────────── 데이터 ─────────────────────────
@st.cache_data
def load_data():
    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig", keep_default_na=False)
    df = df.rename(columns={"Korean meaning (뜻)": "Meaning"})
    for col in ["Word", "Meaning", "Variation"]:
        df[col] = df[col].astype(str).str.strip()
    df["Variation"] = df["Variation"].replace({"NA": ""})
    return df[["No.", "Word", "Level", "Meaning", "Variation"]]


@st.cache_data
def get_levels():
    df = load_data()
    return {
        name: df[df["Level"] == code].set_index("No.", drop=False).rename_axis(None)
        for name, code in LEVELS.items()
    }


@st.cache_data
def get_word_index():
    """단어/변형 표기(소문자) -> {word, meaning}  (지문 핵심 단어 뜻 표시에 사용)"""
    df = load_data()
    index = {}
    for word, meaning, variation in zip(df["Word"], df["Meaning"], df["Variation"]):
        forms = [word.lower()] + [v.strip().lower() for v in variation.split(",") if v.strip()]
        for form in forms:
            index.setdefault(form, {"word": word, "meaning": meaning})
    return index


def make_options(lvdf, no, col, n=4):
    """정답 1개 + 같은 수준에서 뽑은 오답 (n-1)개를 섞어서 반환"""
    correct = lvdf.at[no, col]
    # 한→영 문제에서는 같은 뜻을 가진 다른 단어가 오답 보기에 섞이지 않게 제외
    cand = lvdf[lvdf["Meaning"] != lvdf.at[no, "Meaning"]] if col == "Word" else lvdf
    pool = [x for x in cand[col].unique() if x != correct]
    options = random.sample(pool, min(n - 1, len(pool))) + [correct]
    random.shuffle(options)
    return options


# ───────────────────────── 상태/콜백 ─────────────────────────
def init_state():
    ss = st.session_state
    ss.setdefault("page", HOME)
    ss.setdefault("review", {name: set() for name in LEVEL_NAMES})
    ss.setdefault("diag_state", "intro")  # intro / running / done
    ss.setdefault("diag_questions", [])
    ss.setdefault("diag_result", None)
    # 다른 페이지에 다녀와도 위젯 값(w_ 로 시작하는 키)이 사라지지 않게 유지
    for key in list(ss.keys()):
        if key.startswith("w_"):
            ss[key] = ss[key]


def go(page):
    st.session_state.page = page


def start_diag():
    ss = st.session_state
    ss.diag_questions = make_diag_questions(get_levels())
    ss.diag_state = "running"


def restart_diag():
    start_diag()
    go(HOME)


def back_to_intro():
    st.session_state.diag_state = "intro"


# ───────────────────────── 수준 진단 ─────────────────────────
def make_diag_questions(levels):
    questions = []
    for name in LEVEL_NAMES:
        lvdf = levels[name]
        for no in random.sample(list(lvdf.index), DIAG_PER_LEVEL):
            questions.append({
                "level": name,
                "word": lvdf.at[no, "Word"],
                "answer": lvdf.at[no, "Meaning"],
                "options": make_options(lvdf, no, "Meaning") + [DONT_KNOW],
            })
    return questions


def recommend(scores):
    """낮은 수준부터 PASS_SCORE 이상이면 한 단계씩 올려서 추천"""
    rec = LEVEL_NAMES[0]
    for i, name in enumerate(LEVEL_NAMES[:-1]):
        if scores[name] >= PASS_SCORE:
            rec = LEVEL_NAMES[i + 1]
        else:
            break
    return rec


def level_buttons(levels, prefix):
    cols = st.columns(len(LEVEL_NAMES))
    for col, name in zip(cols, LEVEL_NAMES):
        col.button(f"{name} ({len(levels[name]):,}개)", key=f"{prefix}_{name}",
                   on_click=go, args=(name,))


def diag_form():
    ss = st.session_state
    st.subheader("🧭 내 수준 확인하기")
    st.write("아는 만큼만 골라 보세요. 모르면 '잘 모르겠어요'를 골라도 괜찮아요. (총 15문항)")
    questions = ss.diag_questions
    with st.form("diag_form"):
        for i, q in enumerate(questions):
            st.radio(f"**{i + 1}. {q['word']}**", q["options"], index=None, key=f"diag_q_{i}")
        submitted = st.form_submit_button("결과 보기", type="primary")
    if submitted:
        scores = {name: 0 for name in LEVEL_NAMES}
        for i, q in enumerate(questions):
            if ss.get(f"diag_q_{i}") == q["answer"]:
                scores[q["level"]] += 1
        ss.diag_result = {"scores": scores, "recommended": recommend(scores)}
        ss.diag_state = "done"
        st.rerun()
    st.button("← 돌아가기", on_click=back_to_intro)


def diag_result(levels):
    res = st.session_state.diag_result
    st.subheader("🧭 진단 결과")
    cols = st.columns(len(LEVEL_NAMES))
    for col, name in zip(cols, LEVEL_NAMES):
        col.metric(name, f"{res['scores'][name]} / {DIAG_PER_LEVEL}")
    st.success(f"**{res['recommended']}** 단어부터 시작하면 좋아요! "
               "추천일 뿐이라서, 다른 수준도 언제든 자유롭게 골라서 공부할 수 있어요.")
    st.button(f"👉 {res['recommended']} 학습 시작", type="primary", on_click=go,
              args=(res["recommended"],))
    st.caption("다른 수준으로 바로 가기")
    level_buttons(levels, "res")
    st.button("🔄 진단 다시 하기", on_click=start_diag)


def page_home(levels):
    ss = st.session_state
    st.title("📚 영어 단어 학습")
    if ss.diag_state == "running":
        diag_form()
        return
    if ss.diag_state == "done" and ss.diag_result:
        diag_result(levels)
        return
    st.write("먼저 3분 정도 간단한 진단으로 내 수준을 확인하거나, 바로 원하는 수준에서 시작할 수 있어요.")
    c1, c2 = st.columns(2)
    c1.button("🧭 내 수준 확인하기 (약 3분)", type="primary", on_click=start_diag)
    c2.button("바로 학습 시작", on_click=go, args=(LEVEL_NAMES[0],))
    st.caption("수준별 단어 수")
    cols = st.columns(len(LEVEL_NAMES))
    for col, name in zip(cols, LEVEL_NAMES):
        col.metric(name, f"{len(levels[name]):,}개")


# ───────────────────────── 수준별 페이지 ─────────────────────────
def page_level(name, lvdf):
    ss = st.session_state
    st.subheader(f"{name} 단어 · {len(lvdf):,}개")
    res = ss.diag_result
    if res and res["recommended"] == name:
        st.caption("🧭 진단 결과로 추천된 수준이에요.")
    mode_key = f"w_mode_{name}"
    ss.setdefault(mode_key, M_CARD)
    mode = st.radio("연습 모드 (언제든 바꿔도 돼요)", MODES, key=mode_key, horizontal=True)
    st.divider()
    if mode == M_LIST:
        mode_list(name, lvdf)
    elif mode == M_CARD:
        mode_flashcards(name, lvdf)
    elif mode == M_REVIEW:
        mode_review(name, lvdf)
    else:
        run_quiz(name, lvdf, MODE_KIND[mode], [int(i) for i in lvdf.index], "all")


def mode_list(name, lvdf):
    ss = st.session_state
    key = f"w_search_{name}"
    ss.setdefault(key, "")
    q = st.text_input("🔍 검색 (영어 또는 한국어)", key=key).strip()
    view = lvdf
    if q:
        mask = (
            lvdf["Word"].str.contains(q, case=False, regex=False)
            | lvdf["Meaning"].str.contains(q, regex=False)
            | lvdf["Variation"].str.contains(q, case=False, regex=False)
        )
        view = lvdf[mask]
    st.caption(f"{len(view):,}개")
    show = view[["No.", "Word", "Meaning", "Variation"]].rename(
        columns={"No.": "번호", "Word": "단어", "Meaning": "뜻", "Variation": "변형 표기"})
    st.dataframe(show, hide_index=True, height=420)


# ───────────────────────── 플래시카드 ─────────────────────────
def render_card(text, sub=""):
    st.markdown(
        "<div style='border:1px solid rgba(128,128,128,.4);border-radius:16px;"
        "padding:48px 16px;text-align:center;background:rgba(128,128,128,.08);'>"
        f"<div style='font-size:2.4rem;font-weight:700;'>{html.escape(text)}</div>"
        f"<div style='margin-top:12px;opacity:.7;'>{html.escape(sub)}</div></div>",
        unsafe_allow_html=True,
    )


SPEAK_HTML = """
<meta name="color-scheme" content="light dark">
<style>
  body { margin: 0; font-family: sans-serif; }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  button {
    cursor: pointer; font-size: 15px; padding: 7px 14px; border-radius: 8px;
    border: 1px solid rgba(128,128,128,.5); background: rgba(128,128,128,.15); color: CanvasText;
  }
  button:active { background: rgba(128,128,128,.35); }
  #m { font-size: 13px; opacity: .75; }
</style>
<div class="row">
  <button id="normal">🔊 발음 듣기</button>
  <button id="slow">🐢 천천히</button>
  <span id="m"></span>
</div>
<script>
  const word = __WORD__;
  const msg = document.getElementById('m');
  function pickVoice() {
    const voices = window.speechSynthesis.getVoices();
    return voices.find(v => v.lang === 'en-US') ||
           voices.find(v => v.lang && v.lang.startsWith('en')) || null;
  }
  function say(rate) {
    if (!('speechSynthesis' in window)) {
      msg.textContent = '이 브라우저는 음성 재생을 지원하지 않아요.';
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(word);
    u.lang = 'en-US';
    u.rate = rate;
    const v = pickVoice();
    if (v) u.voice = v;
    window.speechSynthesis.speak(u);
  }
  document.getElementById('normal').onclick = () => say(0.9);
  document.getElementById('slow').onclick = () => say(0.55);
</script>
"""


def speak_button(text):
    """브라우저 내장 음성 합성(Web Speech API)으로 영어 발음을 들려줌 (추가 설치 없음)"""
    components.html(SPEAK_HTML.replace("__WORD__", json.dumps(text)), height=52)


def fc_unflip(flip_key):
    st.session_state[flip_key] = False


def fc_toggle(flip_key):
    st.session_state[flip_key] = not st.session_state[flip_key]


def fc_move(pos_key, flip_key, delta, n):
    ss = st.session_state
    ss[pos_key] = min(max(ss[pos_key] + delta, 1), n)
    ss[flip_key] = False


def fc_mark(name, no, known, pos_key, flip_key, n, deck_mode):
    ss = st.session_state
    if known:
        ss.review[name].discard(no)
    else:
        ss.review[name].add(no)
    ss[flip_key] = False
    removed_from_deck = known and deck_mode == "헷갈려요만"
    if not removed_from_deck:
        ss[pos_key] = min(ss[pos_key] + 1, n)


def fc_reshuffle(seed_key, pos_key, flip_key):
    ss = st.session_state
    ss[seed_key] += 1
    ss[pos_key] = 1
    ss[flip_key] = False


def mode_flashcards(name, lvdf):
    ss = st.session_state
    review = ss.review[name]
    deck_key, order_key = f"w_fcdeck_{name}", f"w_fcorder_{name}"
    pos_key, seed_key, flip_key = f"w_fcpos_{name}", f"fc_seed_{name}", f"fc_flip_{name}"
    ss.setdefault(deck_key, "전체")
    ss.setdefault(order_key, "번호순")
    ss.setdefault(pos_key, 1)
    ss.setdefault(seed_key, 1)
    ss.setdefault(flip_key, False)

    c1, c2, c3 = st.columns([2, 2, 1])
    deck_mode = c1.radio("카드 범위", ["전체", "헷갈려요만"], key=deck_key, horizontal=True)
    order = c2.radio("순서", ["번호순", "무작위"], key=order_key, horizontal=True)
    c3.button("🔀 섞기", key=f"fc_shuffle_{name}", on_click=fc_reshuffle,
              args=(seed_key, pos_key, flip_key))

    ids = [int(i) for i in lvdf.index]
    if deck_mode == "헷갈려요만":
        ids = [i for i in ids if i in review]
    if order == "무작위":
        random.Random(ss[seed_key]).shuffle(ids)
    n = len(ids)
    if n == 0:
        st.info("'헷갈려요'로 표시한 단어가 아직 없어요. '전체' 카드에서 표시해 보세요.")
        return

    ss[pos_key] = min(max(int(ss[pos_key]), 1), n)
    if n > 1:
        st.slider("카드 번호", 1, n, key=pos_key, on_change=fc_unflip, args=(flip_key,))
    pos = ss[pos_key]
    no = ids[pos - 1]
    row = lvdf.loc[no]

    mark = "  🔖 표시됨" if no in review else ""
    st.caption(f"{pos} / {n}{mark}")
    if ss[flip_key]:
        sub = row["Word"] + (f"  ·  변형: {row['Variation']}" if row["Variation"] else "")
        render_card(row["Meaning"], sub)
    else:
        render_card(row["Word"], "카드를 뒤집어 뜻을 확인하세요")
    speak_button(row["Word"])

    b1, b2, b3 = st.columns(3)
    b1.button("◀ 이전", key=f"fc_prev_{name}", disabled=pos <= 1, on_click=fc_move,
              args=(pos_key, flip_key, -1, n))
    b2.button("🔄 뒤집기", key=f"fc_flip_btn_{name}", on_click=fc_toggle, args=(flip_key,))
    b3.button("다음 ▶", key=f"fc_next_{name}", disabled=pos >= n, on_click=fc_move,
              args=(pos_key, flip_key, 1, n))
    k1, k2 = st.columns(2)
    k1.button("✅ 알아요", key=f"fc_known_{name}", on_click=fc_mark,
              args=(name, no, True, pos_key, flip_key, n, deck_mode))
    k2.button("❓ 헷갈려요", key=f"fc_unsure_{name}", on_click=fc_mark,
              args=(name, no, False, pos_key, flip_key, n, deck_mode))


# ───────────────────────── 퀴즈 / 철자 ─────────────────────────
def make_quiz(lvdf, pool_ids, kind, size):
    n = min(size, len(pool_ids))
    ids = random.sample(list(pool_ids), n)
    quiz = {"rid": random.randrange(10**9), "size": size, "n": n, "ids": ids,
            "pos": 0, "answers": {}, "options": {}}
    if kind in ("en2ko", "ko2en"):
        col = "Meaning" if kind == "en2ko" else "Word"
        for no in ids:
            quiz["options"][no] = make_options(lvdf, no, col)
    return quiz


def correct_text(kind, row):
    return row["Meaning"] if kind == "en2ko" else row["Word"]


def is_correct(kind, row, answer):
    if kind == "spell":
        return answer.strip().lower() == row["Word"].lower()
    return answer == correct_text(kind, row)


def q_move(quiz, delta):
    quiz["pos"] = min(max(quiz["pos"] + delta, 0), quiz["n"] - 1)


def spelling_hint(word):
    hint = word[0] + "".join("_" if ch.isalpha() else ch for ch in word[1:])
    return " ".join(hint)


def run_quiz(name, lvdf, kind, pool_ids, tag):
    ss = st.session_state
    skey = f"quiz_{tag}_{name}_{kind}"
    size_key = f"w_qsize_{tag}_{name}_{kind}"
    ss.setdefault(size_key, 10)
    size = st.select_slider("문제 수", options=[5, 10, 20, 30], key=size_key)

    quiz = ss.get(skey)
    if quiz is None or quiz["size"] != size:
        if not pool_ids:
            st.info("아직 표시된 단어가 없어요. 퀴즈에서 틀리거나 카드에서 '헷갈려요'를 누르면 여기에 모여요.")
            return
        quiz = make_quiz(lvdf, pool_ids, kind, size)
        ss[skey] = quiz

    n, pos, answers = quiz["n"], quiz["pos"], quiz["answers"]
    no = quiz["ids"][pos]
    row = lvdf.loc[no]
    done = sum(1 for p, a in answers.items() if is_correct(kind, lvdf.loc[quiz["ids"][p]], a))
    st.progress((pos + 1) / n, text=f"문제 {pos + 1} / {n}  ·  푼 문제 {len(answers)}  ·  정답 {done}")

    widget_key = f"qz_{quiz['rid']}_{kind}_{pos}"
    if kind == "en2ko":
        st.markdown(f"## {row['Word']}")
        options = quiz["options"][no]
        prev = answers.get(pos)
        choice = st.radio("뜻을 고르세요", options, key=widget_key,
                          index=options.index(prev) if prev in options else None)
        if choice is not None:
            answers[pos] = choice
    elif kind == "ko2en":
        st.markdown(f"## {row['Meaning']}")
        options = quiz["options"][no]
        prev = answers.get(pos)
        choice = st.radio("알맞은 영어 단어를 고르세요", options, key=widget_key,
                          index=options.index(prev) if prev in options else None)
        if choice is not None:
            answers[pos] = choice
    else:
        st.markdown(f"## {row['Meaning']}")
        st.caption(f"힌트: {spelling_hint(row['Word'])}   ({len(row['Word'])}글자)")
        with st.form(f"form_{widget_key}"):
            typed = st.text_input("영어 철자를 입력하세요", value=answers.get(pos, ""), key=widget_key)
            submitted = st.form_submit_button("확인")
        if submitted:
            answers[pos] = typed.strip()

    if pos in answers:
        if is_correct(kind, row, answers[pos]):
            st.success("정답! 🎉")
            if tag == "review":
                ss.review[name].discard(no)
        else:
            answer_text = row["Word"] if kind == "spell" else correct_text(kind, row)
            st.error(f"아쉬워요. 정답: **{answer_text}**")
            ss.review[name].add(no)

    c1, c2, c3 = st.columns(3)
    c1.button("◀ 이전 문제", key=f"qprev_{skey}", disabled=pos == 0, on_click=q_move, args=(quiz, -1))
    c2.button("🔄 새 문제 세트", key=f"qnew_{skey}", on_click=lambda: ss.pop(skey, None))
    c3.button("다음 문제 ▶", key=f"qnext_{skey}", disabled=pos >= n - 1, on_click=q_move, args=(quiz, 1))

    if len(answers) == n:
        correct_now = sum(1 for p, a in answers.items() if is_correct(kind, lvdf.loc[quiz["ids"][p]], a))
        st.info(f"🏁 모든 문제를 풀었어요! 결과: {correct_now} / {n}. "
                "틀린 단어는 '복습' 모드에 모아 두었어요.")


def mode_review(name, lvdf):
    ss = st.session_state
    ids = sorted(ss.review[name])
    st.caption(f"표시한 단어 {len(ids)}개 — 퀴즈에서 틀린 단어와 카드에서 '헷갈려요'로 표시한 단어가 모여요. "
               "복습에서 맞히면 목록에서 빠집니다.")
    if ids:
        with st.expander("표시한 단어 보기"):
            st.write(", ".join(lvdf.at[i, "Word"] for i in ids))
        st.button("🗑️ 표시 모두 지우기", key=f"clear_review_{name}",
                  on_click=lambda: ss.review[name].clear())
    kind_key = f"w_revkind_{name}"
    ss.setdefault(kind_key, KIND_LABEL["en2ko"])
    label = st.radio("복습 방식", list(KIND_LABEL.values()), key=kind_key, horizontal=True)
    kind = {v: k for k, v in KIND_LABEL.items()}[label]
    run_quiz(name, lvdf, kind, ids, "review")


# ───────────────────────── 읽기(지문) ─────────────────────────
# 지문 표기법: [[단어]] = 그 수준의 단어(노란 표시), [[변형된 형태|기본 단어]] = 기본 단어가 다른 경우
STORY_TITLE = "✈️ 여행 이야기: 낯선 도시에서의 하루"
STORY_SUMMARY_KO = (
    "지난여름 친구와 큰 도시로 여행을 떠났다. 기차를 타고 가서 숙소에 짐을 풀고, 식당에서 맛있고 "
    "저렴한 저녁을 먹었다. 다음 날 오래된 다리를 보러 가려고 길에서 만난 여성에게 길을 물었고, "
    "그분이 친절하게 알려 주었다. 다리에서 사진을 많이 찍은 뒤 시장에서 어머니께 드릴 선물을 "
    "샀다. 짧은 여행이었지만 오래 기억할 것이다."
)
BEAT_LABELS = ["① 출발", "② 숙소", "③ 저녁 식사", "④ 길 묻기", "⑤ 다리에서", "⑥ 시장과 선물", "⑦ 마무리"]

PASSAGES = {
    "초등": {
        "note": "초등 어휘(*)로 쓴 지문이에요.",
        "beats": [
            "Last summer, I took a [[trip]] to a big city with my friend. We went there by [[train]].",
            "First, we found our [[room]] and put our bags on the bed.",
            "We wanted to eat dinner, so we went to a [[restaurant]]. The food was [[delicious]], "
            "and it was [[cheap]].",
            "The next morning, we wanted to visit an old [[bridge]] by the river. We did not know the way, "
            "so we asked a woman on the [[street]]. She smiled and said, “Walk along this road, and turn "
            "left at the [[corner]].”",
            "We found the bridge and took many pictures.",
            "After that, we went to a [[market]]. I bought a present for my mother and paid [[cash]].",
            "It was a short trip, but I will always [[remember]] it.",
        ],
        "blanks": ["restaurant", "delicious", "bridge", "corner", "market", "cash"],
    },
    "중·고등": {
        "note": "초등 어휘에 중·고등 어휘(**)를 더해 쓴 지문이에요.",
        "beats": [
            "Last summer, I went on a [[journey]] to a [[foreign]] city with my friend. We took a train there.",
            "When we [[reached|reach]] the [[hotel]], we put our bags in the room we had [[reserved|reserve]].",
            "In the evening, we wanted a good [[meal]], so we went to a restaurant. We looked at the [[menu]] "
            "and [[ordered|order]] a [[local]] [[dish]]. It tasted delicious, and the [[price]] was low.",
            "The next morning, we wanted to see an old bridge by the river, but we did not know the way. "
            "A [[polite]] woman on the street helped us. She smiled and said, “Go [[straight]], and turn "
            "left at the corner.”",
            "At the bridge, there was a big [[crowd]], but we still took many [[photos|photo]].",
            "After that, we went to a market. I bought a [[gift]] for my mother and paid in cash.",
            "It was a short trip, but I will always remember it.",
        ],
        "blanks": ["hotel", "menu", "local", "polite", "straight", "gift"],
        "gloss": {"order": "주문하다", "dish": "요리", "straight": "곧장"},
    },
    "확장": {
        "note": "확장 어휘까지 사용해 쓴 지문이에요.",
        "beats": [
            "Last summer, I traveled [[abroad]] with my friend to a [[vast]] city. Our train "
            "[[departed|depart]] from the [[platform]] at dawn.",
            "By evening, we reached a small [[inn]] that [[accommodated|accommodate]] us for the night. "
            "The room was small and far from [[luxury]].",
            "We were [[eager]] to eat, so we found a restaurant and ordered an [[exotic]] dish with a rich "
            "[[flavor]]. It was delicious, and the price was a real [[bargain]].",
            "The next morning, we wanted to see an [[ancient]] bridge by the river, but we could not find it. "
            "We [[inquired|inquire]] of a woman on the street, and we were [[grateful]] for her help. She "
            "smiled and said, “Continue straight, then turn left at the corner.”",
            "At the bridge, we took many photographs of the [[landscape]].",
            "Then, we [[wandered|wander]] through a market, where I bought a gift for my mother. I paid in "
            "local [[currency]] and kept the [[receipt]].",
            "It was a brief trip, but I will always remember it.",
        ],
        "blanks": ["inn", "exotic", "bargain", "ancient", "inquire", "currency"],
        "gloss": {"bargain": "싸게 산 물건", "luxury": "호화로움", "accommodate": "묵게 해 주다"},
    },
}

MARK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
MARK_STYLE = "background:rgba(255,193,7,.35);border-radius:4px;padding:0 3px;font-weight:600;"
BLANK_STYLE = "border-bottom:2px solid currentColor;padding:0 10px;font-weight:700;"
COMPARE = "🔍 문장별 비교"
ACT_READ, ACT_CLOZE = "📖 읽기", "✏️ 빈칸 채우기"
NO_PICK = "선택"


def parse_marks(text):
    """('text', 글) 또는 ('word', 본문 표기, 기본 단어) 조각의 목록으로 나눔"""
    parts, last = [], 0
    for m in MARK_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", text[last:m.start()]))
        parts.append(("word", m.group(1), m.group(2) or m.group(1)))
        last = m.end()
    if last < len(text):
        parts.append(("text", text[last:]))
    return parts


def render_parts(parts, show_marks=True, blank_numbers=None):
    """blank_numbers = {기본 단어: 번호} 이면 그 단어의 첫 등장 위치를 빈칸으로 표시"""
    out, used = [], set()
    for part in parts:
        if part[0] == "text":
            out.append(html.escape(part[1]))
            continue
        _, surface, base = part
        if blank_numbers and base in blank_numbers and base not in used:
            used.add(base)
            out.append(f"<span style='{BLANK_STYLE}'>({blank_numbers[base]}) ______</span>")
        elif show_marks:
            out.append(f"<span style='{MARK_STYLE}'>{html.escape(surface)}</span>")
        else:
            out.append(html.escape(surface))
    return "".join(out)


def show_html(body):
    st.markdown(f"<div style='line-height:2;font-size:1.05rem;'>{body}</div>", unsafe_allow_html=True)


def passage_parts(name):
    return parse_marks(" ".join(PASSAGES[name]["beats"]))


def keyword_table(parts, word_index, gloss=None):
    """gloss = {기본 단어: 지문 속 뜻}. 목록의 뜻이 지문 문맥과 다를 때만 덮어씀"""
    gloss = gloss or {}
    rows, seen = [], set()
    for part in parts:
        if part[0] == "word" and part[2] not in seen:
            seen.add(part[2])
            entry = word_index.get(part[2].lower(), {})
            rows.append({"단어": part[2], "지문에 나온 모양": part[1],
                         "뜻 (이 지문에서)": gloss.get(part[2], entry.get("meaning", ""))})
    return pd.DataFrame(rows)


def cloze_order(name):
    """빈칸으로 만들 단어를 지문에 나오는 순서대로 [(기본 단어, 본문 표기)]"""
    order = []
    for part in passage_parts(name):
        if part[0] == "word" and part[2] in PASSAGES[name]["blanks"] \
                and part[2] not in [b for b, _ in order]:
            order.append((part[2], part[1]))
    return order


def reset_cloze(name, count):
    ss = st.session_state
    ss[f"read_checked_{name}"] = False
    for i in range(count):
        ss[f"w_cloze_{name}_{i}"] = NO_PICK


def check_cloze(name):
    st.session_state[f"read_checked_{name}"] = True


def reading_cloze(name, show_marks):
    ss = st.session_state
    order = cloze_order(name)
    numbers = {base: i + 1 for i, (base, _) in enumerate(order)}
    show_html(render_parts(passage_parts(name), show_marks, numbers))

    bank = [surface for _, surface in order]
    random.Random(name).shuffle(bank)
    st.markdown("**단어 상자:** " + " · ".join(f"`{w}`" for w in bank))
    checked_key = f"read_checked_{name}"
    ss.setdefault(checked_key, False)
    for i in range(len(order)):
        key = f"w_cloze_{name}_{i}"
        ss.setdefault(key, NO_PICK)
        st.selectbox(f"({i + 1})", [NO_PICK, *bank], key=key)

    b1, b2 = st.columns(2)
    b1.button("✅ 정답 확인", key=f"read_check_{name}", type="primary", on_click=check_cloze, args=(name,))
    b2.button("🔄 다시 풀기", key=f"read_reset_{name}", on_click=reset_cloze, args=(name, len(order)))
    if ss[checked_key]:
        right = 0
        for i, (_, surface) in enumerate(order):
            if ss[f"w_cloze_{name}_{i}"] == surface:
                right += 1
                st.write(f"({i + 1}) ✅ {surface}")
            else:
                st.write(f"({i + 1}) ❌ 정답: **{surface}**")
        st.info(f"결과: {right} / {len(order)}")


def reading_single(name, show_marks, word_index):
    ss = st.session_state
    st.caption(PASSAGES[name]["note"])
    act_key = "w_read_act"
    ss.setdefault(act_key, ACT_READ)
    act = st.radio("활동", [ACT_READ, ACT_CLOZE], key=act_key, horizontal=True)
    if act == ACT_READ:
        show_html(render_parts(passage_parts(name), show_marks))
        with st.expander("🔑 이 지문의 핵심 단어"):
            st.dataframe(
                keyword_table(passage_parts(name), word_index, PASSAGES[name].get("gloss")),
                hide_index=True)
    else:
        reading_cloze(name, show_marks)


def reading_compare(show_marks):
    st.caption("같은 장면을 세 가지 어휘 수준으로 비교해 보세요.")
    for i, label in enumerate(BEAT_LABELS):
        st.markdown(f"**{label}**")
        for name in LEVEL_NAMES:
            body = render_parts(parse_marks(PASSAGES[name]["beats"][i]), show_marks)
            st.markdown(
                f"<div style='margin:2px 0 8px;line-height:1.9;'>"
                f"<span style='opacity:.6;font-size:.8rem;'>{html.escape(name)}</span><br>{body}</div>",
                unsafe_allow_html=True)
        st.divider()


def page_reading(word_index):
    ss = st.session_state
    st.subheader(STORY_TITLE)
    st.caption("같은 이야기를 초등 / 중·고등 / 확장 어휘 수준으로 읽어 보세요. 노란색은 그 수준의 단어예요.")
    with st.expander("📝 줄거리 (한국어)"):
        st.write(STORY_SUMMARY_KO)
    view_key, marks_key = "w_read_view", "w_read_marks"
    ss.setdefault(view_key, LEVEL_NAMES[0])
    ss.setdefault(marks_key, True)
    view = st.radio("지문 선택", [*LEVEL_NAMES, COMPARE], key=view_key, horizontal=True)
    show_marks = st.checkbox("수준 단어 노란색으로 표시", key=marks_key)
    st.divider()
    if view == COMPARE:
        reading_compare(show_marks)
    else:
        reading_single(view, show_marks, word_index)


# ───────────────────────── 사이드바 / 메인 ─────────────────────────
def sidebar():
    ss = st.session_state
    with st.sidebar:
        st.header("내 학습 현황")
        for name in LEVEL_NAMES:
            st.write(f"**{name}** · 표시한 단어 {len(ss.review[name])}개")
        if ss.diag_result:
            st.write(f"🧭 추천 수준: **{ss.diag_result['recommended']}**")
        st.button("🧭 수준 진단 다시 하기", on_click=restart_diag)
        st.caption("새로고침하거나 창을 닫으면 표시한 단어와 진단 결과는 초기화돼요.")


def main():
    st.set_page_config(page_title="영어 단어 학습", page_icon="📚", layout="centered")
    if not DATA_FILE.exists():
        st.error(f"{DATA_FILE.name} 파일을 app.py와 같은 폴더에 넣어 주세요.")
        st.stop()
    init_state()
    levels = get_levels()
    sidebar()
    st.radio("이동", PAGES, key="page", horizontal=True, label_visibility="collapsed")
    page = st.session_state.page
    if page == HOME:
        page_home(levels)
    elif page in LEVELS:
        page_level(page, levels[page])
    else:
        page_reading(get_word_index())


if __name__ == "__main__":
    main()
