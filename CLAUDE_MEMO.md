# Workout Tracker - 開発メモ

## 概要
Streamlit + JSON で作る筋トレ記録Webアプリ

## 技術スタック
- Python / Streamlit
- JSON（データ保存）
- hashlib（パスワードハッシュ化）
- pandas（データ処理）
- plotly（グラフ描画）

## ファイル構成
```
workout-tracker/
├── app.py          # メインアプリ（UIロジック）
├── auth.py         # ユーザー認証
├── data.py         # トレーニング記録の読み書き
├── requirements.txt
├── users.json      # 自動生成（ユーザー情報）
├── workouts.json   # 自動生成（記録データ）
└── CLAUDE_MEMO.md  # このファイル
```

## 機能
- ログイン / 新規登録（パスワードはSHA-256ハッシュで保存）
- トレーニング記録（種目・重量・セット数・回数・日付）
- 履歴表示（種目フィルター・総ボリューム計算・削除機能）
- グラフ（重量推移・総ボリューム推移・最高重量メトリクス）

## 起動方法
```bash
cd C:\Users\tmrev\dev\workout-tracker
pip install -r requirements.txt
streamlit run app.py
```

## 今後の拡張アイデア
- [ ] メモ欄の追加（体調・感想など）
- [ ] CSV/Excelエクスポート
- [ ] 週次サマリー
- [ ] 身体データ（体重・体脂肪率）の記録
