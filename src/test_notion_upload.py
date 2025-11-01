from integrations.notion_client import NotionClient
from pathlib import Path


def upload_episode_to_notion(md_file_path):
    """エピソードの .md ファイルを読み込んで Notion にアップロード"""
    md_file = Path(md_file_path)
    if not md_file.exists():
        print(f"❌ ファイルが見つかりません: {md_file_path}")
        return

    # ファイル名をエピソードタイトルとして使用
    episode_title = md_file.stem

    # Markdown ファイルの内容を読み込む
    with open(md_file, "r", encoding="utf-8") as f:
        markdown_content = f.read()

    # Notion に追加
    notion = NotionClient()
    notion.create_page(episode_title, markdown_content)


# テスト用
if __name__ == "__main__":
    upload_episode_to_notion("outputs/エピソード名/episode_summary.md")
