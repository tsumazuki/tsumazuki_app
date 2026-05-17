# -*- coding: utf-8 -*-
"""
リカバリー検証スクリプト
================================================
generate_dummy.py が記録した「真の理解度」(dummy_truth.csv) と、
dummy_data.xlsx の正答率から作った「つまずきマップの推定値」を照合する。

問い:「正答率を集計しただけのマップは、本当の理解度を復元できているか?」

真値を知らないフリをして正答率からタグ別理解度を推定し、
最初に仕込んだ真値とどれだけ一致するかを誤差・相関で評価する。
さらにテスト回数を変えると精度がどう変わるかも見る
（→ 実践に必要なテスト回数の見積もりになる）。

出力:
  recovery_report.txt    検証結果のテキストレポート
  recovery_scatter.png   真値 vs 推定値 の散布図
  recovery_by_ntest.png  テスト回数と推定精度の関係
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import japanize_matplotlib  # noqa: F401

TRUTH_CSV = "dummy_truth.csv"
DATA_XLSX = "dummy_data.xlsx"

truth = pd.read_csv(TRUTH_CSV)
questions = pd.read_excel(DATA_XLSX, sheet_name="questions")
responses = pd.read_excel(DATA_XLSX, sheet_name="responses")


def split_tags(cell):
    if pd.isna(cell) or str(cell).strip() == "":
        return set()
    return {t.strip() for t in str(cell).split(";") if t.strip()}


questions["teacher_set"] = questions["teacher_tags"].apply(split_tags)

# ------------------------------------------------------------
# 推定: 正答率から「タグ別・テスト回別の理解度」を出す
#   各問題の正誤を、その問題が持つ各タグに割り当て、
#   タグ×テスト回ごとに平均（= 正答率）をとる。
#   これが「マップが推定した理解度」。
# ------------------------------------------------------------
merged = responses.merge(
    questions[["test_id", "question_id", "teacher_set"]],
    on=["test_id", "question_id"], how="left")

est_records = []
for _, row in merged.iterrows():
    tags = row["teacher_set"]
    if not isinstance(tags, set):
        continue
    for t in tags:
        est_records.append({"test_id": row["test_id"], "tag": t,
                             "correct": row["correct"]})
est_long = pd.DataFrame(est_records)
estimated = (est_long.groupby(["test_id", "tag"])["correct"]
             .mean().reset_index()
             .rename(columns={"correct": "estimated"}))

# 真値もテスト回×タグで平均（クラス全体の真の理解度）
truth_agg = (truth.groupby(["test_id", "tag"])["true_understanding"]
             .mean().reset_index()
             .rename(columns={"true_understanding": "truth"}))

compare = truth_agg.merge(estimated, on=["test_id", "tag"], how="inner")
compare["error"] = compare["estimated"] - compare["truth"]

# ------------------------------------------------------------
# 評価指標
# ------------------------------------------------------------
mae = compare["error"].abs().mean()                 # 平均絶対誤差
rmse = np.sqrt((compare["error"] ** 2).mean())      # 二乗平均平方根誤差
corr = compare["truth"].corr(compare["estimated"])  # 真値と推定値の相関

# 弱点ランキングが復元できているか（順位の一致）
truth_rank = (truth_agg.groupby("tag")["truth"].mean()
              .rank().sort_index())
est_rank = (estimated.groupby("tag")["estimated"].mean()
            .rank().sort_index())
rank_corr = truth_rank.corr(est_rank, method="spearman")

# ------------------------------------------------------------
# テスト回数を変えると精度がどう変わるか
#   テスト1回だけ / 1〜2回 / 1〜3回 で誤差を比較
# ------------------------------------------------------------
all_tests = sorted(compare["test_id"].unique())
ntest_rows = []
for k in range(1, len(all_tests) + 1):
    subset = compare[compare["test_id"].isin(all_tests[:k])]
    ntest_rows.append({
        "n_tests": k,
        "MAE": subset["error"].abs().mean(),
        "corr": subset["truth"].corr(subset["estimated"]),
    })
ntest_df = pd.DataFrame(ntest_rows)

# ------------------------------------------------------------
# レポート出力
# ------------------------------------------------------------
with open("recovery_report.txt", "w", encoding="utf-8") as f:
    f.write("=== リカバリー検証レポート ===\n\n")
    f.write("問い: 正答率から作ったつまずきマップは、\n")
    f.write("      仕込んだ本当の理解度を復元できているか?\n\n")
    f.write("--- 全体精度（タグ×テスト回 単位） ---\n")
    f.write(f"  比較データ点数 : {len(compare)}\n")
    f.write(f"  平均絶対誤差 MAE : {mae:.4f}\n")
    f.write(f"  RMSE             : {rmse:.4f}\n")
    f.write(f"  真値との相関     : {corr:.4f}\n")
    f.write(f"  弱点順位の一致(Spearman): {rank_corr:.4f}\n")
    f.write("  ※ MAEが小さく相関が1に近いほど、マップは正確。\n")
    f.write("  ※ 順位一致が1なら『どのタグが弱点か』の序列を完全復元。\n\n")
    f.write("--- タグ別の真値 vs 推定値（全テスト回平均） ---\n")
    tag_cmp = (compare.groupby("tag")[["truth", "estimated", "error"]]
               .mean().sort_values("truth"))
    f.write(f"{'tag':<20}{'真値':>8}{'推定':>8}{'誤差':>8}\n")
    for tag, r in tag_cmp.iterrows():
        f.write(f"{tag:<20}{r['truth']:>8.3f}{r['estimated']:>8.3f}"
                f"{r['error']:>+8.3f}\n")
    f.write("\n--- テスト回数と推定精度 ---\n")
    f.write(f"{'テスト回数':>10}{'MAE':>10}{'相関':>10}\n")
    for _, r in ntest_df.iterrows():
        f.write(f"{int(r['n_tests']):>10}{r['MAE']:>10.4f}{r['corr']:>10.4f}\n")
    f.write("  ※ 回数を増やすとMAEが下がる＝必要なテスト回数の目安になる。\n")

print("written: recovery_report.txt")

# ------------------------------------------------------------
# 図1: 真値 vs 推定値 散布図
# ------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6, 6))
ax.scatter(compare["truth"], compare["estimated"],
           c="#2F5496", alpha=0.7, s=50)
ax.plot([0, 1], [0, 1], "r--", lw=1, label="完全一致の線")
ax.set_xlabel("仕込んだ真の理解度")
ax.set_ylabel("マップが推定した理解度（正答率）")
ax.set_title(f"リカバリー検証：真値 vs 推定値\n相関={corr:.3f}  MAE={mae:.3f}")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig("recovery_scatter.png", dpi=150)
print("written: recovery_scatter.png")

# ------------------------------------------------------------
# 図2: テスト回数と精度
# ------------------------------------------------------------
fig, ax1 = plt.subplots(figsize=(7, 4.5))
ax1.plot(ntest_df["n_tests"], ntest_df["MAE"],
         "o-", color="#C0392B", label="MAE（誤差）")
ax1.set_xlabel("使用したテスト回数")
ax1.set_ylabel("平均絶対誤差 MAE", color="#C0392B")
ax1.tick_params(axis="y", labelcolor="#C0392B")
ax1.set_xticks(ntest_df["n_tests"])
ax2 = ax1.twinx()
ax2.plot(ntest_df["n_tests"], ntest_df["corr"],
         "s--", color="#27AE60", label="相関")
ax2.set_ylabel("真値との相関", color="#27AE60")
ax2.tick_params(axis="y", labelcolor="#27AE60")
ax1.set_title("テスト回数を増やすと推定精度はどう変わるか")
fig.tight_layout()
fig.savefig("recovery_by_ntest.png", dpi=150)
print("written: recovery_by_ntest.png")
