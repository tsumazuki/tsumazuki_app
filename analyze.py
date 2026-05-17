# -*- coding: utf-8 -*-
"""
つまずきマップ 分析スクリプト
入力 : tsumazuki_template.xlsx （questions / responses シート）
出力 : agreement_report.txt   AIタグと教師タグの一致度レポート
        tag_accuracy.png      タグ別正答率（つまずきマップ）
        agreement_heatmap.png タグごとの一致状況

使い方:
  python3 analyze.py  tsumazuki_template.xlsx
"""
import sys
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import japanize_matplotlib  # noqa: F401  日本語表示を有効化

# ---------------------------------------------------------------- 入力読込
infile = sys.argv[1] if len(sys.argv) > 1 else "tsumazuki_template.xlsx"
questions = pd.read_excel(infile, sheet_name="questions")
responses = pd.read_excel(infile, sheet_name="responses")


def split_tags(cell):
    """セミコロン区切りのタグ文字列を集合に変換。空欄は空集合。"""
    if pd.isna(cell) or str(cell).strip() == "":
        return set()
    return {t.strip() for t in str(cell).split(";") if t.strip()}


questions["teacher_set"] = questions["teacher_tags"].apply(split_tags)
questions["ai_set"] = questions["ai_tags"].apply(split_tags)

# ================================================================
# 分析1：AIタグ vs 教師タグ の一致度
#   集合どうしの比較なので Jaccard係数（共通/和集合）を問題ごとに算出。
#   1.0 = 完全一致, 0.0 = 全く重ならない。
# ================================================================
def jaccard(a, b):
    if not a and not b:
        return None          # 両方空 → 評価対象外
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


rows = []
for _, q in questions.iterrows():
    j = jaccard(q["teacher_set"], q["ai_set"])
    rows.append({
        "test_id": q["test_id"], "question_id": q["question_id"],
        "teacher": ";".join(sorted(q["teacher_set"])) or "(なし)",
        "ai": ";".join(sorted(q["ai_set"])) or "(なし)",
        "jaccard": j,
    })
agree = pd.DataFrame(rows)
scored = agree.dropna(subset=["jaccard"])

# タグ単位の混同：教師がつけた / AIがつけた を突き合わせ
all_tags = sorted({t for s in questions["teacher_set"] for t in s} |
                  {t for s in questions["ai_set"] for t in s})
tp = {t: 0 for t in all_tags}   # 両者一致
fn = {t: 0 for t in all_tags}   # 教師のみ（AIが見落とし）
fp = {t: 0 for t in all_tags}   # AIのみ（AIが過剰付与）
for _, q in questions.iterrows():
    for t in all_tags:
        in_t, in_a = t in q["teacher_set"], t in q["ai_set"]
        if in_t and in_a:
            tp[t] += 1
        elif in_t and not in_a:
            fn[t] += 1
        elif in_a and not in_t:
            fp[t] += 1

with open("agreement_report.txt", "w", encoding="utf-8") as f:
    f.write("=== AIタグ と 教師タグ の一致度レポート ===\n\n")
    if len(scored) == 0:
        f.write("AIタグが未入力です。questionsシートのai_tags列を埋めてください。\n")
    else:
        f.write(f"評価対象の問題数: {len(scored)}\n")
        f.write(f"平均Jaccard係数 : {scored['jaccard'].mean():.3f}"
                "  (1.0で完全一致)\n")
        f.write(f"完全一致した問題: {(scored['jaccard'] == 1.0).sum()} / "
                f"{len(scored)} 問\n\n")
        f.write("--- 問題ごとの詳細 ---\n")
        for _, r in agree.iterrows():
            js = "未評価" if pd.isna(r["jaccard"]) else f"{r['jaccard']:.2f}"
            f.write(f"[{r['test_id']}/{r['question_id']}] "
                    f"一致度={js}\n"
                    f"    教師: {r['teacher']}\n"
                    f"    AI  : {r['ai']}\n")
        f.write("\n--- タグ別のAI傾向 ---\n")
        f.write(f"{'tag':<20}{'一致':>6}{'AI見落とし':>12}{'AI過剰':>10}\n")
        for t in all_tags:
            f.write(f"{t:<20}{tp[t]:>6}{fn[t]:>12}{fp[t]:>10}\n")

print("written: agreement_report.txt")

# 一致状況のヒートマップ（AIタグがある場合のみ）
if len(scored) > 0:
    import numpy as np
    mat = np.array([[tp[t], fn[t], fp[t]] for t in all_tags], dtype=float)
    fig, ax = plt.subplots(figsize=(7, max(3, 0.5 * len(all_tags))))
    im = ax.imshow(mat, cmap="YlOrRd", aspect="auto")
    ax.set_xticks(range(3))
    ax.set_xticklabels(["一致", "AI見落とし", "AI過剰付与"])
    ax.set_yticks(range(len(all_tags)))
    ax.set_yticklabels(all_tags)
    for i in range(len(all_tags)):
        for j in range(3):
            ax.text(j, i, int(mat[i, j]), ha="center", va="center")
    ax.set_title("タグごとの AI と教師の一致状況")
    fig.colorbar(im, label="問題数")
    fig.tight_layout()
    fig.savefig("agreement_heatmap.png", dpi=150)
    print("written: agreement_heatmap.png")

# ================================================================
# 分析2：タグ別正答率（つまずきマップ）
#   教師タグを正とする。1問に複数タグがあれば、その問題の正誤を
#   各タグに重複カウントする。タグ別の平均正答率が低い=クラスの弱点。
# ================================================================
merged = responses.merge(
    questions[["test_id", "question_id", "teacher_set"]],
    on=["test_id", "question_id"], how="left")

records = []
for _, row in merged.iterrows():
    tags = row["teacher_set"]
    if not isinstance(tags, set):   # mergeで対応問題が無い場合はNaN
        continue
    for t in tags:
        records.append({"tag": t, "correct": row["correct"]})
long = pd.DataFrame(records)

if len(long) > 0:
    tag_acc = (long.groupby("tag")["correct"]
               .agg(["mean", "count"])
               .rename(columns={"mean": "正答率", "count": "延べ解答数"})
               .sort_values("正答率"))
    tag_acc.to_csv("tag_accuracy.csv", encoding="utf-8-sig")

    fig, ax = plt.subplots(figsize=(8, max(3, 0.5 * len(tag_acc))))
    colors = ["#C0392B" if v < 0.5 else "#E67E22" if v < 0.7 else "#27AE60"
              for v in tag_acc["正答率"]]
    ax.barh(tag_acc.index, tag_acc["正答率"], color=colors)
    ax.set_xlim(0, 1)
    ax.set_xlabel("クラス平均正答率")
    ax.set_title("つまずきマップ：タグ別正答率（低いほど弱点）")
    for i, (v, n) in enumerate(zip(tag_acc["正答率"], tag_acc["延べ解答数"])):
        ax.text(v + 0.02, i, f"{v:.0%} (n={n})", va="center")
    ax.axvline(0.5, color="gray", ls="--", lw=0.8)
    ax.axvline(0.7, color="gray", ls=":", lw=0.8)
    fig.tight_layout()
    fig.savefig("tag_accuracy.png", dpi=150)
    print("written: tag_accuracy.png / tag_accuracy.csv")
else:
    print("responses が空です。")
