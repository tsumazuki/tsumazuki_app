# -*- coding: utf-8 -*-
"""
ダミーデータ生成スクリプト（中程度モデル）
================================================
仮想クラスの生徒に「タグ別の理解度（真値）」を持たせ、
テスト回ごとに学習で少しずつ向上させ、
理解度を成功確率とみなして問題の正誤を確率的に生成する。

出力:
  dummy_data.xlsx        questions / responses シート（analyze.py 互換）
  dummy_truth.csv        各生徒・各テスト回・各タグの「真の理解度」
                         → パラメータリカバリー(verify_recovery.py)で使用

ポイント:
  生徒の真の理解度は実験者が決めて記録しておく。
  分析側(analyze.py)はこの真値を知らずに正答率だけからマップを作る。
  後で両者を照合することで「測定がどれだけ正確か」を評価できる。
"""
import numpy as np
import pandas as pd

# ============================================================
# 設定（ここを変えれば仮想クラスの条件を変えられる）
# ============================================================
SEED = 42                       # 乱数の種。同じ値なら毎回同じデータ
N_STUDENTS = 35                 # 1クラスの生徒数
N_TESTS = 3                     # テストの実施回数
N_QUESTIONS_PER_TEST = 20       # 1回のテストの問題数

# 使用するタグ（案1の tag_master と揃える。8個に絞った例）
TAGS = ["vocabulary", "idiom", "tense", "relative-clause",
        "participle", "sentence-structure", "reference", "inference"]

# 「クラスとして特に弱いタグ」を仕込む（つまずきマップで検出されるべき弱点）
# 値はクラス平均の初期理解度。低いほど弱点。
CLASS_BASELINE = {
    "vocabulary":          0.75,
    "idiom":               0.60,
    "tense":               0.70,
    "relative-clause":     0.35,   # ← 仕込んだ弱点1
    "participle":          0.40,   # ← 仕込んだ弱点2
    "sentence-structure":  0.55,
    "reference":           0.65,
    "inference":           0.45,   # ← 仕込んだ弱点3
}

# 生徒間の能力差の大きさ（標準偏差）。大きいほど生徒ごとのばらつき大
STUDENT_SPREAD = 0.12

# 1回のテストごとの学習による理解度の伸び（平均）。タグ共通
LEARNING_GAIN = 0.06
GAIN_SPREAD = 0.03              # 伸び方の生徒間ばらつき

rng = np.random.default_rng(SEED)


def clip01(x):
    """理解度を 0〜1 の範囲に収める。"""
    return np.clip(x, 0.02, 0.98)


# ============================================================
# 1. 生徒ごとの「真の理解度」を生成
#    初期理解度 = クラス平均 + 生徒固有のずれ
#    テスト回が進むごとに学習ゲインを加算
# ============================================================
# 生徒固有のオフセット（全タグに共通してかかる「地力」の差）
student_ability = rng.normal(0.0, STUDENT_SPREAD, size=N_STUDENTS)
# 生徒ごとの学習スピードの差
student_gain = clip01(rng.normal(LEARNING_GAIN, GAIN_SPREAD, size=N_STUDENTS))
student_gain = np.maximum(student_gain, 0.0)

truth_rows = []
# truth[(student, test, tag)] = 真の理解度
truth = {}
for s in range(N_STUDENTS):
    sid = f"S{s+1:02d}"
    for test in range(1, N_TESTS + 1):
        for tag in TAGS:
            base = CLASS_BASELINE[tag] + student_ability[s]
            # テスト回ごとの伸び（test=1 では伸びゼロ、以降加算）
            grown = base + student_gain[s] * (test - 1)
            # タグ固有の細かいノイズ（同じ生徒でもタグで多少ぶれる）
            val = clip01(grown + rng.normal(0, 0.04))
            truth[(sid, test, tag)] = val
            truth_rows.append({"student_id": sid, "test_id": f"test{test:02d}",
                               "tag": tag, "true_understanding": round(val, 4)})

truth_df = pd.DataFrame(truth_rows)
truth_df.to_csv("dummy_truth.csv", index=False, encoding="utf-8-sig")

# ============================================================
# 2. 問題（questions シート）を生成
#    各問題に 1〜2 個のタグを割り当てる。
#    teacher_tags は「真のタグ」。ai_tags はあえて少しノイズを混ぜて
#    「AIタグ付けは完璧でない」状況を再現する。
#
#    重要: 問題のタグ構成は1セットだけ決め、全テスト回で使い回す。
#    回ごとにタグ分布が変わると、つまずきマップの時系列比較が
#    「生徒の成長」なのか「タグ構成の偶然」なのか区別できなくなるため。
# ============================================================
q_rows = []
# AIが間違えやすいタグの組（混同しやすいペアを仕込む）
AI_CONFUSION = {
    "participle": "relative-clause",   # 分詞構文と関係詞を混同しがち
    "inference": "reference",          # 推論と指示語把握を混同しがち
}

# まず Q番号ごとのタグ構成を1セットだけ決める
q_template = []   # [{teacher: [...], ai: "..."}, ...]
for q in range(1, N_QUESTIONS_PER_TEST + 1):
    n_tag = 1 if rng.random() < 0.7 else 2
    chosen = list(rng.choice(TAGS, size=n_tag, replace=False))

    # AIタグ：8割はそのまま、2割は混同・欠落・過剰のいずれか
    ai_tags_set = set(chosen)
    if rng.random() < 0.20:
        mode = rng.choice(["confuse", "drop", "add"])
        if mode == "confuse":
            for t in list(ai_tags_set):
                if t in AI_CONFUSION:
                    ai_tags_set.discard(t)
                    ai_tags_set.add(AI_CONFUSION[t])
        elif mode == "drop" and len(ai_tags_set) > 1:
            ai_tags_set.discard(rng.choice(list(ai_tags_set)))
        elif mode == "add":
            ai_tags_set.add(rng.choice(TAGS))
    q_template.append({
        "teacher": chosen,
        "ai": ";".join(sorted(ai_tags_set)),
    })

# 全テスト回に同じタグ構成を展開する
for test in range(1, N_TESTS + 1):
    for q in range(1, N_QUESTIONS_PER_TEST + 1):
        tmpl = q_template[q - 1]
        q_rows.append({
            "test_id": f"test{test:02d}",
            "question_id": f"Q{q:02d}",
            "max_score": 1,
            "teacher_tags": ";".join(tmpl["teacher"]),
            "ai_tags": tmpl["ai"],
            "memo": "dummy",
            "_tags": tmpl["teacher"],   # 内部用（正誤生成で使う）
        })
questions_df = pd.DataFrame(q_rows)

# ============================================================
# 3. 回答（responses シート）を生成
#    問題の正解確率 = その問題のタグについての生徒の理解度の平均。
#    その確率でコイン投げ（ベルヌーイ試行）して 1/0 を決める。
# ============================================================
resp_rows = []
for _, qrow in questions_df.iterrows():
    test_no = int(qrow["test_id"].replace("test", ""))
    tags = qrow["_tags"]
    for s in range(N_STUDENTS):
        sid = f"S{s+1:02d}"
        # この問題のタグについての理解度の平均 = 正解確率
        p = np.mean([truth[(sid, test_no, t)] for t in tags])
        correct = int(rng.random() < p)
        resp_rows.append({
            "test_id": qrow["test_id"],
            "question_id": qrow["question_id"],
            "student_id": sid,
            "correct": correct,
        })
responses_df = pd.DataFrame(resp_rows)

# ============================================================
# 4. Excel に保存（analyze.py がそのまま読める形式）
# ============================================================
out_q = questions_df.drop(columns=["_tags"])
with pd.ExcelWriter("dummy_data.xlsx", engine="openpyxl") as w:
    out_q.to_excel(w, sheet_name="questions", index=False)
    responses_df.to_excel(w, sheet_name="responses", index=False)
    # タグ定義シートも付けておく
    pd.DataFrame({"tag": TAGS}).to_excel(w, sheet_name="tag_master", index=False)

# ============================================================
# 5. 生成結果のサマリを表示
# ============================================================
print("=== ダミーデータ生成完了 ===")
print(f"生徒数 {N_STUDENTS} / テスト {N_TESTS}回 / "
      f"1回{N_QUESTIONS_PER_TEST}問")
print(f"  questions 行数 : {len(out_q)}")
print(f"  responses 行数 : {len(responses_df)}")
print("\n仕込んだクラスの弱点（初期理解度が低いタグ）:")
for t, v in sorted(CLASS_BASELINE.items(), key=lambda x: x[1]):
    mark = "  ← 弱点" if v < 0.5 else ""
    print(f"  {t:<20} {v:.2f}{mark}")
print("\n出力ファイル: dummy_data.xlsx / dummy_truth.csv")
