# Render + Neon テスト環境セットアップ

## Neon

1. NeonでPostgreSQLのプロジェクトを作成します。
2. 接続文字列をコピーします。
3. Renderの環境変数 `DATABASE_URL` に設定します。

## Render

RenderでGitHubリポジトリを接続し、Web Serviceとして作成します。

このリポジトリには `render.yaml` があるため、Blueprintとして作成できます。

手動で設定する場合は以下です。

```txt
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn --bind 0.0.0.0:$PORT app:app
```

## 環境変数

```txt
DATABASE_URL=Neonの接続文字列
SECRET_KEY=Renderで自動生成または任意のランダム文字列
ADMIN_USERNAME=管理画面ユーザー名
ADMIN_PASSWORD=管理画面パスワード
MAIL_FROM=送信元メール
MAIL_TO=問い合わせ受信メール
```

## 注意

テスト環境では、添付ファイルはRenderの `uploads/` に保存されます。
Renderの通常ファイル領域は永続保存向きではないため、再デプロイや再起動で消える可能性があります。

見積りデータと問い合わせ情報は、`DATABASE_URL` を設定していればNeonに保存されます。
