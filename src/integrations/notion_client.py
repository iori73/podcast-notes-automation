# src/integrations/notion_client.py
"""
Notion APIクライアント
エピソード情報をNotionデータベースにアップロード
"""

import requests
from pathlib import Path
from utils import load_config
from typing import Optional, Dict, Any
import re


class NotionClient:
    def __init__(self):
        """Notionクライアントを初期化"""
        self.config = load_config()
        self.api_key = self.config.get("notion", {}).get("api_key", "")
        self.database_id = self.config.get("notion", {}).get("database_id", "")
        
        if not self.api_key or not self.database_id:
            raise ValueError("Notion API key または Database ID が設定されていません")
        
        # データベースIDをフォーマット（ハイフンありの形式に変換）
        self.database_id = self._format_database_id(self.database_id)
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }
    
    def _format_database_id(self, db_id: str) -> str:
        """データベースIDをフォーマット（ハイフンありの形式に変換）"""
        # ハイフンを除去
        db_id_clean = db_id.replace("-", "")
        
        # 32文字の場合はフォーマット
        if len(db_id_clean) == 32:
            return (
                f"{db_id_clean[:8]}-{db_id_clean[8:12]}-{db_id_clean[12:16]}-"
                f"{db_id_clean[16:20]}-{db_id_clean[20:32]}"
            )
        
        return db_id
    
    def _split_text_into_chunks(self, text: str, max_length: int = 2000) -> list:
        """テキストを2000文字以下のチャンクに分割"""
        if len(text) <= max_length:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # 文や段落の境界で分割を試みる
        sentences = text.split('。')
        
        for sentence in sentences:
            # 句点を追加（最後の文以外）
            if sentence != sentences[-1]:
                sentence += '。'
            
            # 現在のチャンクに追加しても2000文字を超えない場合
            if len(current_chunk) + len(sentence) <= max_length:
                current_chunk += sentence
            else:
                # 現在のチャンクを保存
                if current_chunk:
                    chunks.append(current_chunk)
                # 新しいチャンクを開始
                # 文自体が2000文字を超える場合は強制的に分割
                if len(sentence) > max_length:
                    # 文字単位で分割
                    for i in range(0, len(sentence), max_length):
                        chunks.append(sentence[i:i+max_length])
                    current_chunk = ""
                else:
                    current_chunk = sentence
        
        # 最後のチャンクを追加
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _markdown_to_notion_blocks(self, markdown: str) -> list:
        """MarkdownテキストをNotionブロックに変換（改行を適切に処理）"""
        blocks = []
        lines = markdown.split("\n")
        current_section = None  # "timestamps", "transcript", "summary", None
        current_paragraph = []
        
        for i, line in enumerate(lines):
            original_line = line
            line = line.strip()
            
            # 空行の処理
            if not line:
                # 現在の段落を保存
                if current_paragraph:
                    paragraph_text = "\n".join(current_paragraph)
                    # タイムスタンプセクションの場合は各行を個別のブロックに
                    if current_section == "timestamps":
                        for para_line in current_paragraph:
                            if para_line.strip():
                                blocks.append({
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [
                                            {
                                                "type": "text",
                                                "text": {"content": para_line.strip()}
                                            }
                                        ]
                                    }
                                })
                    else:
                        # 通常の段落は2000文字を超える場合は分割
                        chunks = self._split_text_into_chunks(paragraph_text, max_length=2000)
                        for chunk in chunks:
                            blocks.append({
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [
                                        {
                                            "type": "text",
                                            "text": {"content": chunk}
                                        }
                                    ]
                                }
                            })
                    current_paragraph = []
                continue
            
            # 見出しの検出
            if line.startswith("## "):
                # 現在の段落を保存
                if current_paragraph:
                    paragraph_text = "\n".join(current_paragraph)
                    if current_section == "timestamps":
                        for para_line in current_paragraph:
                            if para_line.strip():
                                blocks.append({
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [
                                            {
                                                "type": "text",
                                                "text": {"content": para_line.strip()}
                                            }
                                        ]
                                    }
                                })
                    else:
                        chunks = self._split_text_into_chunks(paragraph_text, max_length=2000)
                        for chunk in chunks:
                            blocks.append({
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [
                                        {
                                            "type": "text",
                                            "text": {"content": chunk}
                                        }
                                    ]
                                }
                            })
                    current_paragraph = []
                
                heading_text = line[3:].strip()
                # 「**」を除去（Notionでは不要）
                heading_text = heading_text.replace("**", "")
                # セクションタイプを判定
                if "Timestamps" in heading_text or "タイムスタンプ" in heading_text:
                    current_section = "timestamps"
                elif "Transcript" in heading_text or "文字起こし" in heading_text:
                    current_section = "transcript"
                elif "Summary" in heading_text or "要約" in heading_text:
                    current_section = "summary"
                else:
                    current_section = None
                
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": heading_text}
                            }
                        ]
                    }
                })
            elif line.startswith("### "):
                if current_paragraph:
                    paragraph_text = "\n".join(current_paragraph)
                    if current_section == "timestamps":
                        for para_line in current_paragraph:
                            if para_line.strip():
                                blocks.append({
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [
                                            {
                                                "type": "text",
                                                "text": {"content": para_line.strip()}
                                            }
                                        ]
                                    }
                                })
                    else:
                        chunks = self._split_text_into_chunks(paragraph_text, max_length=2000)
                        for chunk in chunks:
                            blocks.append({
                                "object": "block",
                                "type": "paragraph",
                                "paragraph": {
                                    "rich_text": [
                                        {
                                            "type": "text",
                                            "text": {"content": chunk}
                                        }
                                    ]
                                }
                            })
                    current_paragraph = []
                
                heading_text = line[4:].strip()
                # 「**」を除去（Notionでは不要）
                heading_text = heading_text.replace("**", "")
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": heading_text}
                            }
                        ]
                    }
                })
            elif line.startswith("- "):
                # リスト項目の処理
                if current_paragraph:
                    paragraph_text = "\n".join(current_paragraph)
                    chunks = self._split_text_into_chunks(paragraph_text, max_length=2000)
                    for chunk in chunks:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": chunk}
                                    }
                                ]
                            }
                        })
                    current_paragraph = []
                
                # リスト項目を個別のブロックに
                list_text = line[2:].strip()
                # リンクの処理
                link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
                rich_text = []
                if re.search(link_pattern, list_text):
                    # リンクを含む場合
                    parts = re.split(link_pattern, list_text)
                    for j, part in enumerate(parts):
                        if j % 3 == 0 and part:
                            rich_text.append({
                                "type": "text",
                                "text": {"content": part}
                            })
                        elif j % 3 == 1:
                            # リンクテキスト
                            link_text = part
                            link_url = parts[j + 1] if j + 1 < len(parts) else ""
                            rich_text.append({
                                "type": "text",
                                "text": {
                                    "content": link_text,
                                    "link": {"url": link_url}
                                }
                            })
                else:
                    rich_text.append({
                        "type": "text",
                        "text": {"content": list_text}
                    })
                
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": rich_text
                    }
                })
            else:
                # タイムスタンプセクションの場合は各行を個別に処理
                if current_section == "timestamps":
                    # タイムスタンプの行を個別のブロックに
                    if line.strip():
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": line}
                                    }
                                ]
                            }
                        })
                else:
                    # 通常の行は段落に追加
                    current_paragraph.append(line)
        
        # 残りの段落を追加
        if current_paragraph:
            paragraph_text = "\n".join(current_paragraph)
            if current_section == "timestamps":
                for para_line in current_paragraph:
                    if para_line.strip():
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": para_line.strip()}
                                    }
                                ]
                            }
                        })
            else:
                # TranscriptやSummaryの場合は、文の境界で分割して改行を保持
                if current_section == "transcript" or current_section == "summary":
                    # 文の境界（。、！、？）で分割
                    sentences = re.split(r'([。！？\n])', paragraph_text)
                    current_sentence = ""
                    
                    for sentence in sentences:
                        if len(current_sentence) + len(sentence) <= 2000:
                            current_sentence += sentence
                        else:
                            if current_sentence:
                                blocks.append({
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [
                                            {
                                                "type": "text",
                                                "text": {"content": current_sentence.strip()}
                                            }
                                        ]
                                    }
                                })
                            current_sentence = sentence
                    
                    if current_sentence.strip():
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": current_sentence.strip()}
                                    }
                                ]
                            }
                        })
                else:
                    chunks = self._split_text_into_chunks(paragraph_text, max_length=2000)
                    for chunk in chunks:
                        blocks.append({
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": chunk}
                                    }
                                ]
                            }
                        })
        
        return blocks
    
    def create_page(
        self,
        title: str,
        markdown_content: str,
        spotify_url: Optional[str] = None,
        cover_url: Optional[str] = None,
        podcast_name: Optional[str] = None,
        release_date: Optional[str] = None,
        duration_minutes: Optional[float] = None,
    ) -> Optional[str]:
        """Notionデータベースに新しいページを作成"""
        try:
            # プロパティを構築
            properties = {
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }
            
            # Spotify URLプロパティを追加（存在する場合）
            if spotify_url:
                properties["URL"] = {
                    "url": spotify_url
                }
            
            # Podcastプロパティを追加（存在する場合）
            if podcast_name:
                properties["Podcast"] = {
                    "select": {
                        "name": podcast_name
                    }
                }
            
            # Release Dateプロパティを追加（存在する場合）
            if release_date:
                # YYYY-MM-DD形式を想定
                properties["Release Date"] = {
                    "date": {
                        "start": release_date
                    }
                }
            
            # Durationプロパティを追加（存在する場合）
            if duration_minutes is not None:
                properties["1. Duration"] = {
                    "number": duration_minutes
                }
            
            # カバー画像を設定（存在する場合）
            cover = None
            if cover_url:
                cover = {
                    "type": "external",
                    "external": {
                        "url": cover_url
                    }
                }
            
            # ページ作成リクエスト
            create_url = "https://api.notion.com/v1/pages"
            payload = {
                "parent": {
                    "database_id": self.database_id
                },
                "properties": properties,
                "children": self._markdown_to_notion_blocks(markdown_content)
            }
            
            if cover:
                payload["cover"] = cover
            
            response = requests.post(create_url, headers=self.headers, json=payload)
            
            if response.status_code == 200:
                page_data = response.json()
                page_id = page_data.get("id", "")
                page_url = page_data.get("url", "")
                print(f"✅ Notionページを作成しました: {page_url}")
                return page_id
            else:
                print(f"❌ Notionページ作成エラー: {response.status_code}")
                print(f"   レスポンス: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Notionページ作成エラー: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_page(
        self,
        page_id: str,
        markdown_content: str,
        spotify_url: Optional[str] = None,
        cover_url: Optional[str] = None,
    ) -> bool:
        """既存のNotionページを更新"""
        try:
            # ブロックを追加
            blocks = self._markdown_to_notion_blocks(markdown_content)
            
            # 既存のブロックを削除してから新しいブロックを追加
            # （簡易実装：既存ブロックを取得して削除）
            blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
            
            # 新しいブロックを追加
            if blocks:
                response = requests.patch(
                    blocks_url,
                    headers=self.headers,
                    json={"children": blocks}
                )
                
                if response.status_code != 200:
                    print(f"⚠️ ブロック追加エラー: {response.status_code}")
                    return False
            
            # プロパティを更新
            if spotify_url or cover_url:
                page_url = f"https://api.notion.com/v1/pages/{page_id}"
                update_payload = {}
                
                if spotify_url:
                    update_payload["properties"] = {
                        "URL": {
                            "url": spotify_url
                        }
                    }
                
                if cover_url:
                    update_payload["cover"] = {
                        "type": "external",
                        "external": {
                            "url": cover_url
                        }
                    }
                
                if update_payload:
                    response = requests.patch(page_url, headers=self.headers, json=update_payload)
                    if response.status_code != 200:
                        print(f"⚠️ プロパティ更新エラー: {response.status_code}")
                        return False
            
            return True
            
        except Exception as e:
            print(f"❌ Notionページ更新エラー: {str(e)}")
            return False

