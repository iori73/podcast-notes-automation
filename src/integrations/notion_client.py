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

    _MD_LINK_INLINE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def _rich_text_from_markdown_inline(self, text: str) -> list:
        """段落内の [ラベル](URL) を Notion rich_text に展開する（ネストなし）。"""
        rich: list = []
        pos = 0
        for m in self._MD_LINK_INLINE.finditer(text):
            if m.start() > pos:
                rich.append(
                    {"type": "text", "text": {"content": text[pos : m.start()]}}
                )
            rich.append(
                {
                    "type": "text",
                    "text": {
                        "content": m.group(1),
                        "link": {"url": m.group(2)},
                    },
                }
            )
            pos = m.end()
        if pos < len(text):
            rich.append({"type": "text", "text": {"content": text[pos:]}})
        return rich

    def _paragraph_rich_text_chunks(
        self, text: str, max_length: int = 2000
    ) -> list:
        """1段落分の rich_text。プレーンのみのときは長さで分割。リンクありは分割せず1ブロック。"""
        text = text.strip()
        if not text:
            return []
        if "](" not in text or "[" not in text:
            chunks = self._split_text_into_chunks(text, max_length=max_length)
            return [[{"type": "text", "text": {"content": c}}] for c in chunks]
        rt = self._rich_text_from_markdown_inline(text)
        total = sum(
            len(x.get("text", {}).get("content", ""))
            for x in rt
            if x.get("type") == "text"
        )
        if total <= max_length:
            return [rt]
        # 極端に長い場合のみプレーンに戻して分割（リンクは失われる）
        chunks = self._split_text_into_chunks(text, max_length=max_length)
        return [[{"type": "text", "text": {"content": c}}] for c in chunks]

    def _emit_transcript_paragraph_text(self, paragraph_text: str, blocks: list) -> None:
        """Transcript/Summary: 改行ごとに段落化し、[text](url) を解釈する。"""
        for para_line in paragraph_text.split("\n"):
            para_line = para_line.strip()
            if not para_line:
                continue
            for rt in self._paragraph_rich_text_chunks(para_line, max_length=2000):
                blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text": rt},
                    }
                )

    def _markdown_to_notion_blocks(self, markdown: str) -> list:
        """MarkdownテキストをNotionブロックに変換（改行を適切に処理）

        Transcriptセクションはtoggleブロック（折りたたみ）として生成する。
        toggleブロックのchildren上限(100)を超える分は self._transcript_overflow_blocks に格納。
        """
        blocks = []
        self._transcript_overflow_blocks = []
        transcript_blocks = []  # toggleのchildren用
        lines = markdown.split("\n")
        current_section = None  # "timestamps", "transcript", "summary", "takeaways", None
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
                        # Transcript/Summaryは改行ごとに1ブロック、それ以外は2000文字で分割
                        if current_section == "transcript" or current_section == "summary":
                            self._emit_transcript_paragraph_text(paragraph_text, blocks)
                        else:
                            chunks = self._split_text_into_chunks(paragraph_text, max_length=2000)
                            for chunk in chunks:
                                blocks.append({
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {
                                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
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
                    elif current_section == "transcript" or current_section == "summary":
                        self._emit_transcript_paragraph_text(paragraph_text, blocks)
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
                elif "Key Takeaways" in heading_text:
                    current_section = "takeaways"
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
                    elif current_section == "transcript" or current_section == "summary":
                        self._emit_transcript_paragraph_text(paragraph_text, blocks)
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
                # TranscriptやSummaryは、改行で区切られた1行＝1段落としてブロック化（読みやすさのため）
                if current_section == "transcript" or current_section == "summary":
                    def _append_paragraph(content: str):
                        if not content or not content.strip():
                            return
                        for rt in self._paragraph_rich_text_chunks(
                            content.strip(), max_length=2000
                        ):
                            blocks.append(
                                {
                                    "object": "block",
                                    "type": "paragraph",
                                    "paragraph": {"rich_text": rt},
                                }
                            )
                    # マークダウンの改行（\n）ごとに1ブロック＝1段落として出力
                    for line in paragraph_text.split("\n"):
                        line = line.strip()
                        if line:
                            _append_paragraph(line)
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
        
        return self._wrap_transcript_in_toggle(blocks)

    def _wrap_transcript_in_toggle(self, blocks: list) -> list:
        """Transcriptのheading_2とその後のブロックをtoggleブロックに変換する。
        100件を超えるchildren は self._transcript_overflow_blocks に格納。"""
        transcript_idx = None
        for idx, block in enumerate(blocks):
            if (block.get("type") == "heading_2"
                and block["heading_2"]["rich_text"]
                and "Transcript" in block["heading_2"]["rich_text"][0]["text"]["content"]):
                transcript_idx = idx
                break

        if transcript_idx is None:
            return blocks

        before = blocks[:transcript_idx]
        transcript_children = blocks[transcript_idx + 1:]  # heading以降の全ブロック

        TOGGLE_CHILD_LIMIT = 100
        initial_children = transcript_children[:TOGGLE_CHILD_LIMIT]
        self._transcript_overflow_blocks = transcript_children[TOGGLE_CHILD_LIMIT:]

        toggle_block = {
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "Transcript"}
                    }
                ],
                "children": initial_children if initial_children else []
            }
        }

        return before + [toggle_block]

    def _find_toggle_block_id(self, page_id: str) -> Optional[str]:
        """ページ内のTranscript toggleブロックのIDを取得する。"""
        import time
        url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100"
        while url:
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                return None
            data = response.json()
            for block in data.get("results", []):
                if block.get("type") == "toggle":
                    rich_text = block.get("toggle", {}).get("rich_text", [])
                    if rich_text and "Transcript" in rich_text[0].get("text", {}).get("content", ""):
                        return block["id"]
            if data.get("has_more"):
                url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=100&start_cursor={data['next_cursor']}"
                time.sleep(0.1)
            else:
                break
        return None

    def _append_blocks_to_page(self, page_id: str, blocks: list) -> bool:
        """ページにブロックを追加（100ブロックずつ分割）"""
        BATCH_SIZE = 100
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        
        for i in range(0, len(blocks), BATCH_SIZE):
            batch = blocks[i:i + BATCH_SIZE]
            response = requests.patch(
                blocks_url,
                headers=self.headers,
                json={"children": batch}
            )
            
            if response.status_code != 200:
                print(f"⚠️ ブロック追加エラー (batch {i//BATCH_SIZE + 1}): {response.status_code}")
                print(f"   レスポンス: {response.text[:500]}")
                return False
            
            print(f"   ✅ ブロック追加完了: {i + 1}〜{min(i + BATCH_SIZE, len(blocks))} / {len(blocks)}")
        
        return True
    
    def create_page(
        self,
        title: str,
        markdown_content: str,
        spotify_url: Optional[str] = None,
        cover_url: Optional[str] = None,
        podcast_name: Optional[str] = None,
        release_date: Optional[str] = None,
        duration_minutes: Optional[float] = None,
        category: Optional[str] = None,
    ) -> Optional[str]:
        """Notionデータベースに新しいページを作成（100ブロック以上も対応）"""
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
                # Notion select options don't allow commas
                clean_name = podcast_name.replace(",", " |")
                properties["Podcast"] = {
                    "select": {
                        "name": clean_name
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

            # Categoryプロパティを追加（存在する場合）
            if category:
                properties["Category"] = {
                    "select": {
                        "name": category
                    }
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
            
            # 全ブロックを生成（Transcriptはtoggleブロック化される）
            all_blocks = self._markdown_to_notion_blocks(markdown_content)
            transcript_overflow = self._transcript_overflow_blocks
            print(f"📝 生成されたブロック数: {len(all_blocks)}")
            if transcript_overflow:
                print(f"   (toggle overflow: {len(transcript_overflow)} ブロック)")

            # 最初の100ブロックでページを作成
            BATCH_SIZE = 100
            initial_blocks = all_blocks[:BATCH_SIZE]
            remaining_blocks = all_blocks[BATCH_SIZE:]

            # ページ作成リクエスト
            create_url = "https://api.notion.com/v1/pages"
            payload = {
                "parent": {
                    "database_id": self.database_id
                },
                "properties": properties,
                "children": initial_blocks
            }

            if cover:
                payload["cover"] = cover

            response = requests.post(create_url, headers=self.headers, json=payload)

            if response.status_code == 200:
                page_data = response.json()
                page_id = page_data.get("id", "")
                page_url = page_data.get("url", "")
                print(f"✅ Notionページを作成しました: {page_url}")

                # 残りのブロックを追加
                if remaining_blocks:
                    print(f"📤 残り {len(remaining_blocks)} ブロックを追加中...")
                    if not self._append_blocks_to_page(page_id, remaining_blocks):
                        print("⚠️ 一部のブロック追加に失敗しましたが、ページは作成されています")

                # toggleブロックのoverflow childrenを追加
                if transcript_overflow:
                    toggle_id = self._find_toggle_block_id(page_id)
                    if toggle_id:
                        print(f"📤 Transcript toggle に残り {len(transcript_overflow)} ブロックを追加中...")
                        if not self._append_blocks_to_page(toggle_id, transcript_overflow):
                            print("⚠️ Transcript toggle への追加に一部失敗しました")
                    else:
                        print("⚠️ Toggleブロックが見つかりませんでした")

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

