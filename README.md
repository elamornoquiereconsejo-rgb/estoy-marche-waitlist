# Estoy マルシェ順番待ち
QR受付、LINE/メール選択、受付番号、あと何組、管理画面、LINE/メール呼出通知、CSV出力を含む試作です。

## 次に必要な設定
1. HTTPSで公開
2. LINE LoginのコールバックURLを `https://公開ドメイン/line/callback` に設定
3. 作成したLINE LoginのChannel ID/Secretを環境変数へ
4. 既存の公式LINEのMessaging API Channel Access Tokenを環境変数へ
5. LINE Loginチャネルに公式LINEアカウントをリンク
6. メール通知を自動化する場合はSMTP設定

LINE Loginは認可コードフローでユーザーIDを取得し、Messaging APIで友だちユーザーへPush通知します。メールを選んだ人のメールアドレスはDBとCSVに保存します。


## Render公開時
Build Command: `pip install -r requirements.txt`
Start Command: `gunicorn app:app`

GitHubには `.env` や `queue.db` をアップロードしないでください。
LINEのChannel SecretやMessaging APIのアクセストークンはRenderのEnvironment Variablesに設定します。
