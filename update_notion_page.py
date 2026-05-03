#!/usr/bin/env python3
"""
Notionページを更新するスクリプト
"""

import sys
from pathlib import Path

# Add src directories to path
sys.path.insert(0, 'src')
sys.path.insert(0, 'src/integrations')

from integrations.notion_client import NotionClient

def main():
    # 更新されたMarkdownファイルを読み込む
    md_file = Path('data/outputs/#95 【月イチ企画】グーグル流エンジニアの終焉？新人類「Cracked Engineer」がAIを操り、1人で世界をハックする | 伊藤穰一/episode_summary.md')
    
    if not md_file.exists():
        print(f"❌ Markdownファイルが見つかりません: {md_file}")
        return
    
    with open(md_file, 'r', encoding='utf-8') as f:
        markdown_content = f.read()
    
    # Notionクライアントを初期化
    notion = NotionClient()
    
    # ページID（実行ログから取得）
    page_id = '2ee264826e0c81249b1fd091f2ed97fa'
    
    # Spotify URL
    spotify_url = 'https://open.spotify.com/episode/1LscTUNYxfYdH75iNKKlEY?si=7b27e3e62bf844a1'
    
    print('📝 Notionページを更新中...')
    print(f'   ページID: {page_id}')
    
    # 既存のブロックを削除してから新しいブロックを追加
    # まず既存のブロックを取得
    blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    import requests
    response = requests.get(blocks_url, headers=notion.headers)
    
    if response.status_code == 200:
        existing_blocks = response.json().get('results', [])
        print(f'   既存のブロック数: {len(existing_blocks)}')
        
        # 既存のブロックを削除
        for block in existing_blocks:
            block_id = block.get('id')
            delete_url = f"https://api.notion.com/v1/blocks/{block_id}"
            delete_response = requests.delete(delete_url, headers=notion.headers)
            if delete_response.status_code != 200:
                print(f"   ⚠️ ブロック削除エラー: {block_id}")
        
        print('   ✅ 既存のブロックを削除しました')
    
    # 新しいブロックを追加
    result = notion.update_page(page_id, markdown_content, spotify_url, None)
    
    if result:
        print('✅ Notionページの更新が完了しました！')
        print(f'   URL: https://www.notion.so/{page_id.replace("-", "")}')
    else:
        print('❌ Notionページの更新に失敗しました')

if __name__ == "__main__":
    main()

