#!/usr/bin/env python3
"""Prompt definition for the LLM coding benchmark."""


def get_coding_prompt() -> str:
    return """あなたはフルスタックWebアプリケーション開発者です。
以下の仕様に従って、Reactベースのチャットアプリケーションを開発してください。

## 出力形式

全てのファイルを以下の形式で出力してください：

=== FILE: ファイルパス ===
(ファイル内容)
=== END FILE ===

## 技術スタック

- **Frontend**: React (Viteを使用、ポート3000)
- **Backend**: Express.js (ポート3001)
- **DB**: better-sqlite3 (インメモリまたはファイルベース)
- **認証**: JWTトークン (jsonwebtokenパッケージ)

## 必須ファイル

1. `package.json` - 全依存関係を含む（react, react-dom, express, better-sqlite3, cors, uuid, jsonwebtoken, concurrently, vite, @vitejs/plugin-react）
2. `vite.config.js` - Vite設定（port 3000、proxy設定でAPI→3001）
3. `server.js` - Expressバックエンド（ポート3001）
4. `src/App.jsx` - メインReactコンポーネント
5. `src/main.jsx` - Reactエントリポイント
6. `index.html` - HTMLテンプレート
7. `start.sh` - バックエンドとフロントエンドを同時起動するスクリプト

## Backend API仕様 (Express, ポート3001)

### 認証
- `POST /api/auth/signup` - Body: `{username, password}` → `{token, userId}`
- `POST /api/auth/login` - Body: `{username, password}` → `{token, userId}`

### ユーザー
- `GET /api/users` - 全ユーザー一覧 → `[{id, username}]`（認証ヘッダー: `Authorization: Bearer <token>`）

### フレンド
- `POST /api/friends/follow` - Body: `{targetUserId}` → フォローする（認証必須）
- `POST /api/friends/unfollow` - Body: `{targetUserId}` → フォロー解除（認証必須）
- `GET /api/friends` - フレンド一覧 → `[{id, username}]`（認証必須）

### メッセージ
- `POST /api/messages/send` - Body: `{recipientId, content}` → メッセージ送信（認証必須）
- `GET /api/messages/:recipientId` - DM履歴取得 → `[{id, senderId, recipientId, content, createdAt}]`（認証必須）

## Frontend仕様 (React)

### 画面構成
1. **ログイン/サインアップ画面**: ユーザー名とパスワードのフォーム。ログインとサインアップを切り替えられる
2. **メイン画面（ログイン後）**: 以下のセクションを持つ
   - **ユーザー一覧/フレンド管理**: 全ユーザーを表示し、フォロー/フォロー解除ボタン
   - **DM画面**: フレンドを選択してメッセージを送受信
   - **リアルタイム更新**: 2秒ごとにポーリングしてメッセージを自動更新

### デザイン要件
- **モダンで美しいUI**を実装すること
- CSSはインラインスタイルまたはCSS-in-JSで記述（外部CSSファイル不要）
- カラーテーマを統一し、余白・角丸・影を適切に使うこと
- レスポンシブレイアウトを意識すること
- チャットUIはメッセージバブル形式で、自分と相手で左右に分ける

## start.sh の内容

```bash
#!/bin/bash
# Start backend
node server.js &
# Start frontend (Vite dev server)
npx vite --port 3000 --host 0.0.0.0 &
wait
```

## 重要な注意事項

- CORSを有効にすること（backend側で`cors()`を使用）
- JWTの検証ミドルウェアを実装すること
- SQLiteのテーブル初期化をサーバー起動時に行うこと
- フロントエンドからのAPI呼び出しには`fetch`を使用
- エラーハンドリングを適切に行うこと
- 全てのコードを省略せずに完全に出力すること
"""
