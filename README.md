# つまずきマップ研究 ― 成果物一式

英語読解のAI活用授業を、研究会発表向けに実践・検証するためのツール群です。
ターミナルで動くPythonスクリプトと、ブラウザで動くWebアプリの2系統があります。

## ファイル一覧

| ファイル | 種別 | 役割 |
|---|---|---|
| `tsumazuki_webapp_v2.html` | Webアプリ | これ1つで全工程。ダミー/本番モード対応 |
| `generate_dummy.py` | Python | ダミーデータ生成（中程度モデル） |
| `analyze.py` | Python | つまずきマップ＋AIタグ一致度の分析 |
| `verify_recovery.py` | Python | リカバリー検証（真値と推定値の照合） |
| `tsumazuki_template.xlsx` | Excel | 本番データの入力テンプレート |

## Webアプリの使い方

`tsumazuki_webapp_v2.html` をブラウザで開くだけで動きます。
インストール不要、サーバ不要、通信もしません。

- **ダミーモード**: 仮想クラスを生成し、STEP 1〜5（生成・マップ・AIタグ検証・
  リカバリー検証・問題生成計画）でシステムを検証します。
- **本番モード**: 実際の生徒の解答を手入力またはCSVで取り込み、
  STEP 1〜3 と STEP 5 を実行します。真値が無いためリカバリー検証は省略されます。
  STEP 1b でAIタグ付け用プロンプトを生成できます。

## Pythonスクリプトの使い方

実行には Python 3 と以下のライブラリが必要です。
```
pip install pandas openpyxl matplotlib japanize-matplotlib
```

### ダミーデータで一連の検証を行う場合
```
python3 generate_dummy.py      # dummy_data.xlsx と dummy_truth.csv を生成
python3 analyze.py dummy_data.xlsx     # つまずきマップ等を出力
python3 verify_recovery.py     # リカバリー検証の図とレポートを出力
```

### 実際の生徒データを分析する場合
1. `tsumazuki_template.xlsx` を開き、questions シートと responses シートに入力
2. `python3 analyze.py tsumazuki_template.xlsx` を実行

## 注意

- Webアプリとターミナル版は乱数生成器が異なるため、同じ設定でも数値は
  完全には一致しません（モデルの挙動・弱点の序列は一致します）。
  発表資料に載せる確定値はターミナル版で固定することを推奨します。
- 生徒の成績データはセンシティブな個人情報です。取り扱いは
  「データ取り扱いの注意」（別途の説明）を参照してください。
