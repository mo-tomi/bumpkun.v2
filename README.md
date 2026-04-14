# BUMPくん v3

DISBOARD Bump追跡Discord Bot の v3。

## v2 → v3 変更点

### 新機能
- **連続Bump記録（Streak）**: 毎日Bumpすると連続日数が増加。自己ベスト更新で通知
- **週間ランキング（`/bump_weekly`）**: 月〜日の週間MVP表示
- **個人統計の強化（`/bump_user`）**: 累計・今週・連続日数・最長記録をEmbed表示
- **スロットのリール追加**: 4種 → 6種（🍀🎯🌈追加）
- **マイルストーン拡張**: 300回・500回も追加

### コード品質改善
- **Cog分割**: main.py(504行) → 4つのCogに分離
  - `cogs/bump.py` - Bump検知 + スロットマシン
  - `cogs/ranking.py` - ランキングコマンド
  - `cogs/reminder.py` - リマインダータスク
  - `cogs/admin.py` - 管理者コマンド
- **config.py**: 定数・称号・メッセージを一箇所に集約
- **Bump検知ロジック**: 重複コードを `_detect_bump()` 関数に統一

### 既存機能の強化
- **ランキング**: 5位 → **10位** まで表示
- **Embed化**: Bump通知をテキストからEmbedに変更（アバター表示付き）
- **称号にstreak連動バッジ**: 3日・7日・14日・30日連続でバッジ表示

## DB移行

v2のDBをそのまま使えます。`init_db()` で自動的に新しい列・テーブルが追加されます:
- `users` テーブルに `last_bump_date`, `current_streak`, `max_streak` 列を追加
- `weekly_bumps` テーブルを新規作成

## 環境変数

```
DISCORD_BOT_TOKEN=xxx
DATABASE_URL=postgres://...
PORT=10000
```

## デプロイ

v2と同じ方法でOK（Docker / Koyeb）。
