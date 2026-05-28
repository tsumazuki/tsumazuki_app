# -*- coding: utf-8 -*-
"""
つまずきマップ 分析スクリプト
入力 : tsumazuki_template.xlsx （questions / responses シート）
出力 : agreement_report.txt        AIタグと教師タグの一致度レポート
        tag_accuracy.png           タグ別正答率（クラスのつまずきマップ）
        agreement_heatmap.png      タグごとの一致状況
        （複数テスト回がある場合）
        tag_accuracy_timeseries.png 時系列のつまずきマップ
        tag_change_report.txt       初回→最終回の変化レポート
        （個人別集計）
        student_deviation.csv       生徒別の総合得点・クラス内偏差値・順位
        student_deviation.png       生徒別の偏差値分布
        student_tag_accuracy.csv    生徒×タグの正答率（個人つまずきマップ）

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

    # ============================================================
    # 分析2b：つまずきマップの時系列変化（テストが複数回ある場合）
    #   テスト回ごとにタグ別正答率を出し、折れ線で推移を可視化する。
    #   前提：各テスト回が同じタグ体系で作られていること。
    # ============================================================
    records_t = []
    for _, row in merged.iterrows():
        tags = row["teacher_set"]
        if not isinstance(tags, set):
            continue
        for t in tags:
            records_t.append({"test_id": row["test_id"], "tag": t,
                              "correct": row["correct"]})
    long_t = pd.DataFrame(records_t)
    test_ids = sorted(long_t["test_id"].unique())

    if len(test_ids) > 1:
        # テスト回×タグ の正答率表
        pivot = (long_t.groupby(["test_id", "tag"])["correct"]
                 .mean().unstack("tag"))
        pivot.to_csv("tag_accuracy_timeseries.csv", encoding="utf-8-sig")

        fig, ax = plt.subplots(figsize=(9, 5))
        for tag in pivot.columns:
            ax.plot(range(len(test_ids)), pivot[tag], "o-", label=tag)
        ax.set_xticks(range(len(test_ids)))
        ax.set_xticklabels(test_ids)
        ax.set_ylim(0, 1)
        ax.set_xlabel("テスト回")
        ax.set_ylabel("クラス平均正答率")
        ax.set_title("つまずきマップの時系列変化（タグ別正答率の推移）")
        ax.axhline(0.5, color="gray", ls="--", lw=0.8)
        ax.axhline(0.7, color="gray", ls=":", lw=0.8)
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=9)
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig("tag_accuracy_timeseries.png", dpi=150)
        print("written: tag_accuracy_timeseries.png / "
              "tag_accuracy_timeseries.csv")

        # 第1回 → 最終回 の変化量レポート
        first, last = test_ids[0], test_ids[-1]
        with open("tag_change_report.txt", "w", encoding="utf-8") as f:
            f.write(f"=== つまずきマップ変化レポート（{first} → {last}）===\n\n")
            f.write(f"{'tag':<20}{'初回':>8}{'最終':>8}{'変化':>9}\n")
            for tag in sorted(pivot.columns,
                              key=lambda t: pivot.loc[last, t]):
                v0, v1 = pivot.loc[first, tag], pivot.loc[last, tag]
                d = v1 - v0
                f.write(f"{tag:<20}{v0:>8.0%}{v1:>8.0%}{d:>+8.1%}\n")
            f.write("\n※ プラス＝改善、マイナス＝低下。\n")
        print("written: tag_change_report.txt")

    # ================================================================
    # 分析4：個人別集計と総合得点の偏差値
    #   各生徒のタグ別正答率（個人つまずきマップ）と、全問正答率に基づく
    #   クラス内偏差値を算出する。偏差値は外部模試と同じく総合得点ベース。
    #   偏差値 = 50 + 10 * (個人正答率 - クラス平均) / 標準偏差
    # ================================================================
    import numpy as np

    # 個人 × タグ の正答率（全テスト回まとめ）
    stu_tag = {}     # {student_id: {tag: [sum, n]}}
    stu_total = {}   # {student_id: [correct, total]}
    for _, row in merged.iterrows():
        sid = row["student_id"]
        c = row["correct"]
        if pd.isna(c):
            continue
        c = int(c)
        stu_total.setdefault(sid, [0, 0])
        stu_total[sid][0] += c
        stu_total[sid][1] += 1
        tags = row["teacher_set"]
        if not isinstance(tags, set):
            continue
        for t in tags:
            stu_tag.setdefault(sid, {}).setdefault(t, [0, 0])
            stu_tag[sid][t][0] += c
            stu_tag[sid][t][1] += 1

    student_ids = sorted(stu_total.keys())
    if student_ids:
        # 総合得点の正答率と偏差値
        rates = {s: stu_total[s][0] / stu_total[s][1]
                 for s in student_ids if stu_total[s][1] > 0}
        mean = float(np.mean(list(rates.values())))
        sd = float(np.std(list(rates.values())))   # 母標準偏差

        def deviation(rate):
            return 50 + 10 * (rate - mean) / sd if sd > 1e-9 else 50.0

        # 順位（正答率の高い順）
        ranked = sorted(rates.items(), key=lambda kv: kv[1], reverse=True)
        rank_of = {}
        for s, r in rates.items():
            rank_of[s] = 1 + sum(1 for _, rr in ranked if rr > r)

        # student_deviation.csv：生徒別の総合得点・偏差値・順位
        dev_rows = []
        for s in student_ids:
            cor, tot = stu_total[s]
            rate = rates.get(s)
            dev_rows.append({
                "student_id": s,
                "correct": cor,
                "total": tot,
                "rate": round(rate, 4) if rate is not None else None,
                "deviation": round(deviation(rate), 1) if rate is not None else None,
                "rank": rank_of.get(s),
            })
        dev_df = pd.DataFrame(dev_rows).sort_values("deviation", ascending=False)
        dev_df.to_csv("student_deviation.csv", index=False, encoding="utf-8-sig")
        print("written: student_deviation.csv")

        # student_tag_accuracy.csv：生徒 × タグ の正答率（個人つまずきマップ）
        tags_all = sorted({t for s in stu_tag for t in stu_tag[s]})
        rows2 = []
        for s in student_ids:
            rec = {"student_id": s}
            for t in tags_all:
                if s in stu_tag and t in stu_tag[s] and stu_tag[s][t][1] > 0:
                    rec[t] = round(stu_tag[s][t][0] / stu_tag[s][t][1], 4)
                else:
                    rec[t] = None
            rows2.append(rec)
        pd.DataFrame(rows2).to_csv(
            "student_tag_accuracy.csv", index=False, encoding="utf-8-sig")
        print("written: student_tag_accuracy.csv")

        # 偏差値分布の図
        fig, ax = plt.subplots(figsize=(8, max(3, 0.3 * len(student_ids))))
        ys = [d["student_id"] for d in dev_rows]
        xs = [d["deviation"] for d in dev_rows]
        order = np.argsort(xs)
        ys = [ys[i] for i in order]
        xs = [xs[i] for i in order]
        colors = ["#c0533f" if x < 45 else "#d99b3f" if x < 55 else "#4a7a52"
                  for x in xs]
        ax.barh(range(len(ys)), xs, color=colors)
        ax.axvline(50, color="#333", linestyle="--", linewidth=1, label="偏差値50")
        ax.set_yticks(range(len(ys)))
        ax.set_yticklabels(ys, fontsize=8)
        ax.set_xlabel("クラス内偏差値（総合得点ベース）")
        ax.set_title(f"生徒別 偏差値（クラス平均正答率 {mean:.0%}）")
        ax.legend()
        fig.tight_layout()
        fig.savefig("student_deviation.png", dpi=150)
        print("written: student_deviation.png")
else:
    print("responses が空です。")
