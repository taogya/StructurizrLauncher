# StructurizrLauncher

Structurizr を複数ワークスペース・ローカル動作・AIからのDSL作成に対応させたランチャーです。
UI は `http://127.0.0.1:8080/`、MCP は `http://127.0.0.1:8081/mcp` で起動します。
クラウドのアカウント、Docker、外部DBは不要です。

## 構成

| ファイル・フォルダ | 用途 |
|---|---|
| `structurizr/` | Structurizr 本体のソース（Git submodule。fork `taogya/structurizr` の `launcher` ブランチ） |
| `workspaces/1/workspace.dsl` | ワークスペース1のDSL |
| `workspaces/2/workspace.dsl` | ワークスペース2のDSL |
| `start.cmd` / `start.sh` | UIとMCPをまとめてバックグラウンド起動 |
| `stop.cmd` / `stop.sh` | このランチャーが起動したUIとMCPを停止 |
| `build.cmd` / `build.sh` | ソースからビルドして `dist` に格納 |
| `status.cmd` / `status.sh` | 起動状態・URLを表示 |
| `launcher.py` / `launcher.json` | ランチャー本体・ポート設定 |
| `dist/` | 実行可能WAR 2本とSHA-256マニフェスト |
| `logs/` | 起動時に生成されるログ |
| `.run/` | ランチャー管理用の一時情報（手作業で編集しない） |
| `tests/` | ローカル結合検証スクリプト |

## 取得（Clone）

`structurizr/` は Git submodule です。本体ソースを含めて取得するため、submodule ごと clone します。

```bash
git clone --recurse-submodules https://github.com/taogya/StructurizrLauncher.git
cd StructurizrLauncher
```

`--recurse-submodules` を付け忘れて clone した場合は、後から取得します。

```bash
git submodule update --init --recursive
```

submodule は fork `taogya/structurizr` の `launcher` ブランチを追跡します。
本体ソースを最新の追跡ブランチへ更新する場合:

```bash
git submodule update --remote structurizr
```

submodule の内容（`structurizr/` のコミット）を更新したら、親リポジトリ側でその参照をコミットしてください。

```bash
git add structurizr
git commit -m "Update structurizr submodule"
```

## 必要環境

- JDK 21以上（`JAVA_HOME` を設定するか `java` をPATHに通す）。検証はJava 21。
- Python 3.10以上。追加Pythonパッケージは不要。
- ブラウザ。
- ソースを初回ビルドする場合はインターネット接続。Mavenはwrapperが取得します。

ビルド済みの `dist` がある場合、起動時のダウンロードはありません。
Java/Python自体は同梱していないため、閉域PCでは事前に導入してください。

## 起動・停止

Windowsのコマンドプロンプト:

```bat
cd C:\path\to\StructurizrLauncher
build.cmd
start.cmd
status.cmd
stop.cmd
```

PowerShellからは ` .\start.cmd ` のように呼び出してください。
ビルド済みWARがあれば `build.cmd` は省略できます。

macOS / Linux:

```bash
cd /path/to/StructurizrLauncher
./build.sh
./start.sh
./status.sh
./stop.sh
```

どのカレントディレクトリからでもスクリプト自身の場所を基準に動作します。
`start` は両サービスのHTTP応答を確認してから成功を返します。
ポート競合や起動失敗時は `logs/launcher.log`、`logs/ui.log`、`logs/mcp.log` を確認してください。
二重起動は抑止し、片方のサービスが終了するともう片方も停止します。
停止処理は管理プロセスへランダムトークンを付けて要求し、無関係なJavaプロセスをPIDで終了させません。

ポートを変える場合は停止してから `launcher.json` の `uiPort` / `mcpPort` を変更します。
待受アドレスはローカルPCの `127.0.0.1` に固定しています。

## 複数ワークスペース

1つのUIサーバー内で複数のワークスペースを扱います。ワークスペースごとにJavaを起動する方式ではありません。
トップページで一覧を表示し、別タブで同時に開けます。

- `workspaces/<正の整数>/workspace.dsl` を配置します。
- URLは `/workspace/1`、`/workspace/2` などです。
- DSL編集後は画面を再読み込みしてください。ファイル変更の検知に約1秒かかります。
- `workspace.json` は本体が生成し、図の位置などを保存します。通常は削除しません。
- 新規ワークスペースはDSLファイルの手動配置、またはMCPで作成します。
- 本ランチャーのMCPでは数字のみのディレクトリ名を使います。

同梱サンプルは外部テーマ・画像・フォントを参照しません。

## MCPによるAI作成

Streamable HTTPに対応したMCPクライアントへ、次のURLを登録します。

```text
http://127.0.0.1:8081/mcp
```

一般的な設定例（キー名は使用クライアントの仕様に合わせてください）:

```json
{
  "mcpServers": {
    "structurizr-local": {
      "url": "http://127.0.0.1:8081/mcp"
    }
  }
}
```

| ツール | 処理 |
|---|---|
| `validate` / `parse` / `inspect` | 既存のDSL検証・JSON変換・モデル検査 |
| `listLocalWorkspaces` | ローカルのワークスペースID一覧 |
| `readLocalWorkspace` | DSLとSHA-256リビジョン取得 |
| `createLocalWorkspace` | 構文検証して新規IDへDSL保存。既存フォルダには上書きしない |
| `updateLocalWorkspace` | リビジョン確認、構文検証、バックアップ、DSL更新 |

AIへの指示例:

> listLocalWorkspacesで空きIDを確認して、タブレットと有線カメラで撮影・保存するシステムのC4図を作って。
> DSLは外部リソースを参照せず、stylesをインライン定義。validate後にcreateLocalWorkspaceで保存して。

更新時は `readLocalWorkspace` が返した `sha256` を `expectedSha256` に渡します。
古いリビジョンは拒否します。更新前DSLは `workspaces/<ID>/.backups/` に保存します。
MCPで保存するDSLは自己完結型です。ファイルinclude、スクリプト、プラグイン、外部通信は許可しません。
手作業の編集とMCP更新を全く同時に実行するケースを排他するものではありません。

MCPサーバー自身がLLMを実行するわけではありません。完全オフラインでAI作成するには、
ローカルLLMと、それを使えるMCPクライアントを別途用意してください。
クラウドLLMにつなぐ場合は、そのクライアントがDSLをクラウドへ送信します。

## 完全ローカル動作の範囲

ビルド後の通常の図の表示・編集・保存、MCPの検証・ローカル保存は外部サービスなしで動作する構成です。

- JS/CSSは本体内蔵のものを配信します。
- ランチャーは本体のネットワークURL許可リストを空に相当する正規表現に固定します。
- ローカルDSL読み込みでHTTP/HTTPS、スクリプト、プラグイン、コンポーネント探索を無効にします。
- ブラウザのCSPで外部の通信・画像・フォント・iframeをブロックします。
- 外部テーマ、外部URLの画像、リモートincludeは使えません。ローカルファイルやインラインstylesを使ってください。
- ヘルプなどの外部ページへのリンクは残ります。オフラインでは開けません。
- サーバー側のPlaywright画像エクスポートはこのビルドから除外しています。通常のブラウザ表示・操作は対象です。

これはOSレベルのネットワーク遮断ではありません。厳密な閉域要件ではPCのネットワークも切断してください。

## 再ビルド・変更点

upstream: https://github.com/structurizr/structurizr.git

ベースコミット: `f828a297dc693e08115b7e5b51dba4a83d8148c2`（2026-09-19）。
変更はclone内に未コミット差分として残してあり、`git -C structurizr diff` で確認できます。
追加ファイルは `git -C structurizr status --short` で確認できます。
自動pull/resetは実行しません。

依存を取得済みなら `build.cmd --offline` / `./build.sh --offline` でMavenのオフラインビルドが可能です。
初回は依存とMaven wrapperの取得が必要です。`build` はテストをスキップしてパッケージを作成します。
追加MCPユニットテストの実行例:

```bash
cd structurizr
./mvnw -B -ntp -pl structurizr-mcp -am test -Dtest=LocalWorkspaceToolsTest -Dsurefire.failIfNoSpecifiedTests=false -Dmaven.javadoc.skip=true
```

主なソース変更:

- `LocalWorkspaceTools.java`：ローカルDSL作成・更新。
- `AbstractTools.java`：MCPパーサーのHTTP/HTTPS無効化。
- `HomePageController.java`：MCPトップページの外部リダイレクトを廃止。
- `LocalFileSystemWorkspaceAdapter.java`：ランチャーのオフライン設定を適用。
- `AbstractController.java`：既存のnonce付きCSPにオフライン制限を追加。
- `structurizr-mcp/pom.xml`：Maven Central URL修正。

upstreamはApache-2.0。`structurizr/LICENSE` を参照してください。
検証結果と制約は `VERIFICATION.md` に記録します。
