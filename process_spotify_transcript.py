#!/usr/bin/env python3
"""
Spotify「聴きながら読む」からの文字起こしHTMLを処理するスクリプト

使用方法:
    python process_spotify_transcript.py <html_file> <spotify_url>

例:
    python process_spotify_transcript.py beattheodds56.html "https://open.spotify.com/episode/5wNv5XFnIoNGTgUaqJ8A23"
"""

import sys
import re
import argparse
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, 'src')
sys.path.insert(0, 'src/integrations')

from spotify import SpotifyClient
from notion_client import NotionClient


def clean_text(text: str) -> str:
    """テキストの改行・空白を整理"""
    # 改行を空白に置換
    text = text.replace('\n', ' ')
    # 複数の空白を1つに
    text = re.sub(r'\s+', ' ', text)
    # 日本語文字間の不要なスペースを除去
    text = re.sub(r'(?<=[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]) (?=[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF])', '', text)
    # 句読点前後の不要なスペースを除去
    text = re.sub(r'\s*([。、！？])\s*', r'\1', text)
    return text.strip()


def extract_transcript_from_html(html_path: Path) -> dict:
    """HTMLファイルから文字起こしデータを抽出"""
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # タイムスタンプとテキストを抽出
    transcript_parts = []
    current_timestamp = None
    
    for element in soup.find_all(['button', 'p']):
        if element.name == 'button':
            span = element.find('span')
            if span:
                timestamp = span.get_text().strip()
                if re.match(r'\d+:\d+', timestamp):
                    current_timestamp = timestamp
        elif element.name == 'p':
            text = element.get_text()
            # テキストを整理
            text = clean_text(text)
            if text and current_timestamp:
                transcript_parts.append((current_timestamp, text))
    
    # タイムスタンプでグループ化
    grouped_transcript = {}
    for ts, text in transcript_parts:
        if ts not in grouped_transcript:
            grouped_transcript[ts] = []
        grouped_transcript[ts].append(text)
    
    # タイムスタンプセクション作成（生のテキストを保持、後でLLMで処理）
    timestamps_raw = []
    for ts in sorted(grouped_transcript.keys(), key=lambda x: tuple(map(int, x.split(':')))):
        combined_text = ' '.join(grouped_transcript[ts])
        timestamps_raw.append((ts, combined_text))
    
    # フルテキスト作成
    full_transcript = []
    for ts in sorted(grouped_transcript.keys(), key=lambda x: tuple(map(int, x.split(':')))):
        combined_text = ' '.join(grouped_transcript[ts])
        full_transcript.append(combined_text)
    
    return {
        'transcript': '\n\n'.join(full_transcript),
        'timestamps_raw': timestamps_raw,  # [(timestamp, text), ...]
        'timestamp_count': len(timestamps_raw)
    }


def generate_summary(transcript: str, max_length: int = 400) -> str:
    """文字起こしから簡易的な要約を生成（最初の数文）"""
    sentences = transcript.split('。')
    summary = ''
    for sentence in sentences[:5]:  # 最初の5文
        if sentence.strip():
            summary += sentence + '。'
    if len(summary) > max_length:
        summary = summary[:max_length] + '...'
    return summary


def generate_chapters_with_ollama(timestamps_raw: list) -> str:
    """Ollamaを使ってタイムスタンプからチャプタータイトルを生成"""
    try:
        import ollama
        
        # 主要なタイムスタンプを選択（約3分ごと）
        key_timestamps = []
        last_minute = -3
        for ts, text in timestamps_raw:
            parts = ts.split(':')
            minutes = int(parts[0])
            if minutes >= last_minute + 3:
                preview = text[:300] if len(text) > 300 else text
                key_timestamps.append((ts, preview))
                last_minute = minutes
        
        # 各タイムスタンプに対してタイトルを生成
        transcript_segments = "\n".join([f"[{ts}] {text}" for ts, text in key_timestamps])
        
        prompt = f"""あなたはポッドキャストの目次を作成するアシスタントです。

以下の文字起こしセグメントを読んで、各タイムスタンプに対して簡潔な日本語のチャプタータイトルを作成してください。

出力形式（厳守）:
0:00 タイトル
3:00 タイトル
...

ルール:
- 各タイトルは15文字以内
- 話している内容を端的に表す
- 説明文は不要、タイトルのみ出力
- 「について」「に関して」は使わない

セグメント:
{transcript_segments}

チャプター目次:"""

        print("🤖 Ollamaでチャプタータイトルを生成中...")
        response = ollama.chat(model='llama3.2', messages=[
            {'role': 'user', 'content': prompt},
        ])
        
        raw_output = response['message']['content'].strip()
        
        # タイムスタンプ形式の行のみ抽出
        chapters = []
        for line in raw_output.split('\n'):
            line = line.strip()
            # MM:SS または M:SS で始まる行のみ
            if re.match(r'^\d{1,2}:\d{2}\s+.+', line):
                chapters.append(line)
        
        if chapters:
            print(f"   ✅ チャプター生成完了（{len(chapters)}個）")
            return '\n'.join(chapters)
        else:
            raise ValueError("有効なチャプターが生成されませんでした")
        
    except Exception as e:
        print(f"   ⚠️ Ollama生成エラー: {e}")
        print("   📝 フォールバック: 手動でタイトル抽出...")
        # フォールバック: 3分ごとに区切って最初の単語をタイトルに
        fallback = []
        last_minute = -3
        for ts, text in timestamps_raw:
            parts = ts.split(':')
            minutes = int(parts[0])
            if minutes >= last_minute + 3:
                # 最初の句点までを取得
                first_sentence = text.split('。')[0]
                title = first_sentence[:20] + "..." if len(first_sentence) > 20 else first_sentence
                fallback.append(f"{ts} {title}")
                last_minute = minutes
        return '\n'.join(fallback)


def main():
    parser = argparse.ArgumentParser(description='Spotify文字起こしHTMLを処理')
    parser.add_argument('html_file', type=str, help='HTMLファイルのパス')
    parser.add_argument('spotify_url', type=str, help='SpotifyエピソードURL')
    parser.add_argument('--no-notion', action='store_true', help='Notionへのアップロードをスキップ')
    parser.add_argument('--summary', type=str, help='カスタム要約（省略時は自動生成）')
    
    args = parser.parse_args()
    
    html_path = Path(args.html_file)
    if not html_path.exists():
        print(f"❌ HTMLファイルが見つかりません: {html_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("🎙️ SPOTIFY TRANSCRIPT PROCESSOR")
    print("=" * 60)
    
    # Step 1: Spotify APIからメタデータ取得
    print("\n📡 Step 1: Spotifyからメタデータを取得...")
    spotify_client = SpotifyClient()
    episode_info = spotify_client.get_episode_info(args.spotify_url)
    
    if not episode_info:
        print("❌ Spotifyからメタデータを取得できませんでした")
        sys.exit(1)
    
    episode_title = episode_info.get('title', 'Unknown')
    podcast_name = episode_info.get('show_name', 'Unknown')
    release_date = episode_info.get('release_date', '')
    duration_ms = episode_info.get('duration_ms', 0)
    duration_minutes = duration_ms / (1000 * 60) if duration_ms else None
    cover_image_url = episode_info.get('cover_image_url', '')
    
    print(f"   ✅ タイトル: {episode_title}")
    print(f"   ✅ ポッドキャスト: {podcast_name}")
    print(f"   ✅ 公開日: {release_date}")
    print(f"   ✅ カバー画像: {cover_image_url[:50]}..." if cover_image_url else "   ⚠️ カバー画像: なし")
    
    # Step 2: HTMLから文字起こし抽出
    print("\n📝 Step 2: HTMLから文字起こしを抽出...")
    extracted = extract_transcript_from_html(html_path)
    
    print(f"   ✅ 文字数: {len(extracted['transcript'])} 文字")
    print(f"   ✅ タイムスタンプ: {extracted['timestamp_count']} セクション")
    
    # Step 3: チャプタータイトル生成
    print("\n📑 Step 3: チャプタータイトル（目次）を生成...")
    chapters = generate_chapters_with_ollama(extracted['timestamps_raw'])
    
    # Step 4: 要約生成
    print("\n📋 Step 4: 要約を準備...")
    if args.summary:
        summary = args.summary
        print("   ✅ カスタム要約を使用")
    else:
        summary = generate_summary(extracted['transcript'])
        print(f"   ✅ 自動要約を生成 ({len(summary)} 文字)")
    
    # Step 5: Markdownファイル保存
    print("\n💾 Step 5: Markdownファイルを保存...")
    safe_title = episode_title.replace('/', '／').replace(':', '：').replace('?', '？')
    output_dir = Path('data/outputs') / safe_title
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 長さフォーマット
    if duration_minutes:
        hours = int(duration_minutes // 60)
        mins = int(duration_minutes % 60)
        secs = int((duration_minutes * 60) % 60)
        if hours > 0:
            duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
        else:
            duration_str = f"{mins:02d}:{secs:02d}"
    else:
        duration_str = "N/A"
    
    markdown_content = f"""## **Basic Information**
- Spotify URL: [Episode Link]({args.spotify_url})
- Podcast: {podcast_name}
- Release Date: {release_date}
- Duration: {duration_str}

## **Summary**

{summary}

## **Chapters**

{chapters}

## **Transcript**

{extracted['transcript']}
"""
    
    output_path = output_dir / 'episode_summary.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"   ✅ 保存先: {output_path}")
    
    # Step 6: Notionアップロード（全文）
    if not args.no_notion:
        print("\n☁️ Step 6: Notionにアップロード（全文）...")
        
        # 全文をそのままアップロード（NotionClientが100ブロックずつ分割して処理）
        notion_client = NotionClient()
        page_id = notion_client.create_page(
            title=episode_title,
            markdown_content=markdown_content,  # 全文をアップロード
            spotify_url=args.spotify_url,
            cover_url=cover_image_url,  # ← Spotify APIから取得したカバー画像を使用
            podcast_name=podcast_name,
            release_date=release_date,
            duration_minutes=duration_minutes
        )
        
        if page_id:
            print("   ✅ Notionアップロード完了（全文）")
    else:
        print("\n⏩ Notionアップロードをスキップ")
    
    print("\n" + "=" * 60)
    print("✅ 処理完了!")
    print("=" * 60)


if __name__ == "__main__":
    main()

