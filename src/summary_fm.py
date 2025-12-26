# # src/summary_fm.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from pathlib import Path
from datetime import datetime
import time
from selenium.webdriver.support.ui import Select
import google.generativeai as genai
from utils import load_config
from account_manager import AccountManager


class SummaryFMProcessor:
    def __init__(self):
        self.setup_driver()
        # Gemini APIの設定
        config = load_config()
        genai.configure(api_key=config["gemini"]["api_key"])

        # 利用可能なモデルを試す（無料枠で使える安定版）
        self.model = None
        model_names = [
            "gemini-1.5-flash",  # 安定版Flashモデル
            "gemini-1.5-pro",  # 安定版Proモデル
            "gemini-pro",  # 古い安定版（フォールバック）
        ]

        for model_name in model_names:
            try:
                self.model = genai.GenerativeModel(model_name)
                print(f"✅ Gemini APIモデル初期化成功: {model_name}")
                break
            except Exception as e:
                # 最初のモデルで失敗した場合のみ警告を表示
                if model_name == model_names[0]:
                    print(f"⚠️ モデル {model_name} を試行中...")
                continue

        if self.model is None:
            print("⚠️ Gemini APIが利用できません。翻訳機能は無効化されます。")

        # アカウント管理の初期化
        self.account_manager = AccountManager()
        self.current_account = None

    def setup_driver(self):
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--dns-prefetch-disable")
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
        self.wait = WebDriverWait(self.driver, 120)

    def login_and_navigate(self):
        """ログインして文字起こしページに移動"""
        max_attempts = len(self.account_manager.accounts)

        for attempt in range(max_attempts):
            try:
                # 使用可能なアカウントを取得
                available_account = self.account_manager.get_available_account()

                if not available_account:
                    print("❌ 全てのアカウントが月5回制限に達しています")
                    print("📊 アカウント使用状況:")
                    self.account_manager.print_status()
                    raise Exception("全てのアカウントが制限に達しました")

                self.current_account = available_account
                print(
                    f"🔑 アカウント使用: {available_account['name']} ({available_account['email']})"
                )
                print(
                    f"   使用回数: {available_account['usage']}/5 (残り: {available_account['remaining']})"
                )

                # ログインページにアクセス
                self.driver.get("https://podcastranking.jp/login")

                # メールアドレス入力
                email_input = self.wait.until(
                    EC.presence_of_element_located((By.ID, "email"))
                )
                email_input.clear()
                email_input.send_keys(available_account["email"])

                # パスワード入力
                password_input = self.wait.until(
                    EC.presence_of_element_located((By.ID, "password"))
                )
                password_input.clear()
                password_input.send_keys(available_account["password"])

                # ログインボタンをクリック
                login_button = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button[type='submit']")
                    )
                )
                login_button.click()

                # ダッシュボードページの読み込みを待機
                try:
                    self.wait.until(EC.url_to_be("https://podcastranking.jp/dashboard"))
                except:
                    # ログインエラーの可能性があるため、エラーメッセージをチェック
                    try:
                        error_element = self.driver.find_element(
                            By.CLASS_NAME, "error-message"
                        )
                        if (
                            "制限" in error_element.text
                            or "limit" in error_element.text.lower()
                        ):
                            print(
                                f"⚠️ アカウント {available_account['name']} が制限に達している可能性があります"
                            )
                            # 使用回数を強制的に5に設定
                            self.account_manager.usage_data[available_account["id"]][
                                self.account_manager._get_current_month_key()
                            ] = 5
                            self.account_manager._save_usage_data()
                            continue
                    except:
                        pass

                    # その他のログインエラー
                    print(
                        f"⚠️ アカウント {available_account['name']} でのログインに失敗しました"
                    )
                    time.sleep(2)
                    continue

                # 文字起こしページに直接移動
                self.driver.get("https://podcastranking.jp/transcribe")

                # 文字起こしページの要素が表示されるまで待機
                self.wait.until(
                    EC.presence_of_element_located((By.ID, "inputs-audio-file"))
                )

                print(
                    f"✅ ログインと移動が完了しました (アカウント: {available_account['name']})"
                )
                return

            except Exception as e:
                print(
                    f"⚠️ アカウント {available_account['name'] if available_account else 'unknown'} でのログインエラー: {str(e)}"
                )
                if attempt < max_attempts - 1:
                    print(f"🔄 次のアカウントで再試行します...")
                    time.sleep(2)
                else:
                    print("❌ 全てのアカウントでログインに失敗しました")
                    raise

    def translate_to_english(self, text, sentence_count=10):
        """日本語テキストを英語に翻訳"""
        # Gemini APIが利用できない場合はスキップ
        if self.model is None:
            print("⚠️ Gemini APIが利用できないため、翻訳をスキップします")
            return "[Translation unavailable - Gemini API not initialized]"

        try:
            # テキストをセンテンスで分割
            sentences = text.split("。")
            translated_sentences = []
            failed_chunks = 0
            max_failures = 3  # 最大3回失敗したら翻訳を中止

            for i in range(0, len(sentences), sentence_count):
                chunk = "。".join(sentences[i : i + sentence_count])
                if not chunk.strip():
                    continue

                # 失敗が多い場合は翻訳を中止
                if failed_chunks >= max_failures:
                    print(
                        f"⚠️ 翻訳エラーが{max_failures}回発生したため、翻訳を中止します"
                    )
                    return "[Translation failed - Too many errors]"

                prompt = f"""
                以下の日本語テキストを英語に翻訳してください。
                元のテキストの意味と文脈を保持しながら、自然な英語に翻訳してください。

                テキスト:
                {chunk}
                """

                try:
                    response = self.model.generate_content(prompt)
                    if response and response.text:
                        translated_sentences.append(response.text)
                        # APIレート制限を避けるため少し待機
                        time.sleep(1)
                    else:
                        print(f"⚠️ 空のレスポンスが返されました")
                        failed_chunks += 1
                except Exception as e:
                    error_msg = str(e)
                    print(f"⚠️ 段落の翻訳エラー: {error_msg}")
                    failed_chunks += 1
                    # エラーが続く場合は詳細を表示
                    if failed_chunks == 1:
                        print(f"   詳細: {error_msg}")

            # 翻訳されたセンテンスがある場合のみ結合
            if translated_sentences:
                return "。".join(translated_sentences)
            else:
                print("❌ 翻訳に失敗しました")
                return "[Translation failed]"

        except Exception as e:
            print(f"❌ 翻訳処理エラー: {str(e)}")
            return "[Translation error]"

    def process_audio(
        self,
        mp3_path=None,
        spotify_url=None,
        release_date=None,
        duration=None,
        language="Japanese",
    ):
        try:
            print(f"📢 処理開始: {mp3_path} (言語: {language})")

            # アカウント使用状況を表示
            print("\n📊 処理前のアカウント使用状況:")
            self.account_manager.print_status()

            self.login_and_navigate()
            print("✅ ログイン成功")

            # ファイルアップロード
            file_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "inputs-audio-file"))
            )
            absolute_path = str(Path(mp3_path).resolve())
            file_input.send_keys(absolute_path)
            print(f"✅ ファイルアップロード完了: {absolute_path}")
            
            # ファイルアップロード後の処理待機
            time.sleep(3)

            # 言語選択
            language_select = self.wait.until(
                EC.presence_of_element_located((By.ID, "language"))
            )
            select = Select(language_select)
            select.select_by_value(language)
            print(f"✅ 言語設定完了: {language}")
            
            # 言語選択後の処理待機
            time.sleep(2)

            # 送信ボタンがクリック可能になるまで待機（複数のセレクターを試す）
            submit_button = None
            selectors = [
                (By.CSS_SELECTOR, "button.inputs-submit"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//button[contains(@class, 'submit')]"),
                (By.XPATH, "//button[contains(text(), '送信')]"),
                (By.XPATH, "//button[contains(text(), 'Submit')]"),
            ]
            
            for selector_type, selector_value in selectors:
                try:
                    submit_button = self.wait.until(
                        EC.element_to_be_clickable((selector_type, selector_value))
                    )
                    print(f"✅ 送信ボタンが見つかりました: {selector_value}")
                    break
                except:
                    continue
            
            if not submit_button:
                # 最後の手段として、すべてのボタンを探す
                buttons = self.driver.find_elements(By.TAG_NAME, "button")
                for button in buttons:
                    if button.is_displayed() and button.is_enabled():
                        submit_button = button
                        print("✅ 代替方法で送信ボタンを見つけました")
                        break
            
            if submit_button:
                submit_button.click()
                print("✅ 文字起こし処理開始")
            else:
                raise Exception("送信ボタンが見つかりませんでした")

            # スクリーンショットを保存（デバッグ用）
            screenshot_path = (
                Path("data/debug")
                / f"processing_start_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(screenshot_path))
            print(f"📸 スクリーンショット保存: {screenshot_path}")

            # 結果が表示されるまで待機（最大20分）
            print("⏳ 処理完了を待機中...")
            max_wait_time = 1200  # 20分
            start_time = time.time()
            result_found = False

            text_ready = False
            summary_ready = False
            timestamp_ready = False

            while time.time() - start_time < max_wait_time:
                elapsed = int(time.time() - start_time)

                # 30秒ごとに進捗表示
                if elapsed % 30 == 0 and elapsed > 0:
                    status = []
                    if text_ready:
                        status.append("文字起こし✅")
                    else:
                        status.append("文字起こし⏳")
                    if summary_ready:
                        status.append("要約✅")
                    else:
                        status.append("要約⏳")
                    if timestamp_ready:
                        status.append("タイムスタンプ✅")
                    else:
                        status.append("タイムスタンプ⏳")
                    print(f"⏳ 待機中... ({elapsed}秒経過) [{', '.join(status)}]")

                try:
                    # 文字起こしチェック
                    if not text_ready:
                        text_element = self.driver.find_element(
                            By.ID, "transcribe-result-section-text"
                        )
                        if (
                            text_element
                            and text_element.text
                            and text_element.text.strip()
                        ):
                            text_ready = True
                            print(f"   ✅ 文字起こし完了（{elapsed}秒）")

                    # 要約チェック
                    if not summary_ready:
                        try:
                            summary_element = self.driver.find_element(
                                By.ID, "summary-result-section-text"
                            )
                            if (
                                summary_element
                                and summary_element.text
                                and summary_element.text.strip()
                            ):
                                summary_ready = True
                                print(f"   ✅ 要約完了（{elapsed}秒）")
                        except:
                            pass

                    # タイムスタンプチェック
                    if not timestamp_ready:
                        try:
                            timestamp_element = self.driver.find_element(
                                By.ID, "timestamp-result-section-text"
                            )
                            if (
                                timestamp_element
                                and timestamp_element.text
                                and timestamp_element.text.strip()
                            ):
                                timestamp_ready = True
                                print(f"   ✅ タイムスタンプ完了（{elapsed}秒）")
                        except:
                            pass

                    # 全て完了したら終了
                    if text_ready and summary_ready and timestamp_ready:
                        print(f"✅ 全ての処理が完了しました！（合計{elapsed}秒）")
                        result_found = True
                        break

                except:
                    pass

                # 5秒待機してから次のチェック
                time.sleep(5)

                # エラーメッセージがないか確認
                try:
                    error_elements = self.driver.find_elements(
                        By.CSS_SELECTOR, ".error, .alert-danger"
                    )
                    for error in error_elements:
                        if error.is_displayed() and error.text:
                            print(f"❌ エラーを検出: {error.text}")
                            # エラースクリーンショット
                            error_screenshot = (
                                Path("data/debug")
                                / f"error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                            )
                            self.driver.save_screenshot(str(error_screenshot))
                            raise Exception(f"処理エラー: {error.text}")
                except:
                    pass

                # 進捗を表示
                elapsed = int(time.time() - start_time)
                print(f"⏳ 待機中... ({elapsed}秒経過）")

                time.sleep(5)  # 5秒ごとにチェック

            if not result_found:
                print(f"⚠️ {max_wait_time}秒待機しましたが、結果が表示されませんでした")
                # タイムアウト時のスクリーンショット
                timeout_screenshot = (
                    Path("data/debug")
                    / f"timeout_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                )
                self.driver.save_screenshot(str(timeout_screenshot))
                print(f"📸 タイムアウト時のスクリーンショット: {timeout_screenshot}")

            # 少し待機してから結果を取得
            time.sleep(5)
            # 結果取得前のスクリーンショット
            result_screenshot = (
                Path("data/debug")
                / f"before_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            )
            result_screenshot.parent.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(result_screenshot))
            print(f"📸 結果取得前のスクリーンショット: {result_screenshot}")

            # ページソースをデバッグ用に保存
            debug_html = (
                Path("data/debug")
                / f"page_source_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
            )
            with open(debug_html, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print(f"📄 HTMLソース保存: {debug_html}")

            try:
                text_result = self.driver.find_element(
                    By.ID, "transcribe-result-section-text"
                ).text
                if text_result and text_result.strip() and text_result.strip() != "Something went wrong":
                    print(
                        f"✅ 文字起こし取得成功: {text_result[:100]}..."
                    )  # 最初の100文字を表示
                else:
                    print("⚠️ 文字起こしは空またはエラーです")
                    text_result = "文字起こしに失敗しました"
            except Exception as e:
                print(f"❌ 文字起こし取得失敗: {str(e)}")
                # 要素が見つからない場合、別のセレクターを試す
                try:
                    text_result = self.driver.find_element(
                        By.CSS_SELECTOR,
                        "[id*='transcribe'], [id*='transcript'], .transcription-result",
                    ).text
                    if text_result and text_result.strip() and text_result.strip() != "Something went wrong":
                        print(f"✅ 代替セレクターで文字起こし取得: {text_result[:50]}")
                    else:
                        text_result = "文字起こしに失敗しました"
                except:
                    text_result = "文字起こしに失敗しました"

            try:
                summary_result = self.driver.find_element(
                    By.ID, "summary-result-section-text"
                ).text
                if summary_result and summary_result.strip():
                    print(f"✅ 要約取得成功: {summary_result[:100]}...")
                else:
                    print("⚠️ 要約は空です")
                    summary_result = "要約の生成に失敗しました"
            except Exception as e:
                print(f"❌ 要約取得失敗: {str(e)}")
                # 代替セレクターを試す
                try:
                    summary_result = self.driver.find_element(
                        By.CSS_SELECTOR, "[id*='summary'], .summary-result"
                    ).text
                    if summary_result and summary_result.strip():
                        print(f"✅ 代替セレクターで要約取得: {summary_result[:50]}")
                    else:
                        summary_result = "要約の生成に失敗しました"
                except:
                    summary_result = "要約の生成に失敗しました"

            try:
                timestamp_result = self.driver.find_element(
                    By.ID, "timestamp-result-section-text"
                ).text
                if timestamp_result and timestamp_result.strip():
                    print(f"✅ タイムスタンプ取得成功: {timestamp_result[:100]}...")
                else:
                    print("⚠️ タイムスタンプは空です")
                    timestamp_result = "タイムスタンプの生成に失敗しました"
            except Exception as e:
                print(f"❌ タイムスタンプ取得失敗: {str(e)}")
                # 代替セレクターを試す
                try:
                    timestamp_result = self.driver.find_element(
                        By.CSS_SELECTOR, "[id*='timestamp'], .timestamp-result"
                    ).text
                    if timestamp_result and timestamp_result.strip():
                        print(
                            f"✅ 代替セレクターでタイムスタンプ取得: {timestamp_result[:50]}"
                        )
                    else:
                        timestamp_result = "タイムスタンプの生成に失敗しました"
                except:
                    timestamp_result = "タイムスタンプの生成に失敗しました"

            # 結果を保存
            folder_name = Path(mp3_path).stem
            output_dir = Path("data/outputs") / folder_name
            output_dir.mkdir(parents=True, exist_ok=True)

            # with open(output_dir / "episode_summary.md", "w", encoding="utf-8") as f:
            #     f.write("## **基本情報**\n\n")
            #     if spotify_url:
            #         f.write(f"- Spotify URL：[エピソードリンク]({spotify_url})\n")
            #     else:
            #         f.write("- Spotify URL：[エピソードリンク]()\n")
            #     f.write(f"- 公開日：{release_date if release_date else ''}\n")
            #     f.write(f"- 長さ：{duration if duration else ''}\n")
            #     f.write("\n## **要約**\n\n")
            #     f.write(summary_result)
            #     f.write("\n\n## **目次**\n\n")
            #     f.write(timestamp_result)
            #     f.write("\n\n## **文字起こし**\n\n")
            #     f.write(text_result)
            #     f.write("\n")

            #  英語
            with open(output_dir / "episode_summary.md", "w", encoding="utf-8") as f:
                f.write("## **Basic Information**\n\n")
                if spotify_url:
                    f.write(f"- Spotify URL: [Episode Link]({spotify_url})\n")
                else:
                    f.write("- Spotify URL: [Episode Link]()\n")

                # 日付フォーマットを英語形式に変換（YYYY年MM月DD日 → MM/DD/YYYY）
                if release_date:
                    try:
                        # 日本語形式の日付を解析
                        date_obj = datetime.strptime(release_date, "%Y年%m月%d日")
                        # 英語形式にフォーマット
                        english_date = date_obj.strftime("%m/%d/%Y")
                        f.write(f"- Release Date: {english_date}\n")
                    except:
                        # 解析できない場合はそのまま表示
                        f.write(f"- Release Date: {release_date}\n")
                else:
                    f.write("- Release Date: \n")

                f.write(f"- Duration: {duration if duration else ''}\n")
                f.write("\n## **Summary**\n\n")
                f.write(summary_result)
                f.write("\n\n## **Timestamps**\n\n")
                f.write(timestamp_result)
                f.write("\n\n## **Transcript**\n\n")
                f.write(text_result)
                f.write("\n")

                # 🔹 日本語の場合、英訳を追加
                if language == "Japanese":
                    print("✅ 日本語のエピソードなので英訳を追加します")

                    # 要約の翻訳
                    try:
                        english_summary = self.translate_to_english(summary_result)
                        if english_summary and not english_summary.startswith(
                            "[Translation"
                        ):
                            print(f"✅ 英訳成功: English Summary")
                            f.write("\n## **English Summary**\n\n")
                            f.write(english_summary)
                            f.write("\n\n")
                        else:
                            print("⚠️ English Summary の翻訳をスキップします")
                            f.write("\n## **English Summary**\n\n")
                            f.write("*Translation unavailable*\n\n")
                    except Exception as e:
                        print(f"❌ English Summary 翻訳エラー: {str(e)}")
                        f.write("\n## **English Summary**\n\n")
                        f.write("*Translation error*\n\n")

                    # 文字起こしの翻訳
                    try:
                        english_text = self.translate_to_english(text_result)
                        if english_text and not english_text.startswith("[Translation"):
                            print(f"✅ 英訳成功: English Transcription")
                            f.write("\n## **English Transcription**\n\n")
                            f.write(english_text)
                            f.write("\n\n")
                        else:
                            print("⚠️ English Transcription の翻訳をスキップします")
                            f.write("\n## **English Transcription**\n\n")
                            f.write("*Translation unavailable*\n\n")
                    except Exception as e:
                        print(f"❌ English Transcription 翻訳エラー: {str(e)}")
                        f.write("\n## **English Transcription**\n\n")
                        f.write("*Translation error*\n\n")

            print(f"✅ 結果を {output_dir} に保存しました")

            # 処理が成功した場合、アカウントの使用回数を増加
            if self.current_account:
                self.account_manager.increment_usage(self.current_account["id"])
                print(
                    f"📊 アカウント {self.current_account['name']} の使用回数を更新しました"
                )

            # 処理後のアカウント使用状況を表示
            print("\n📊 処理後のアカウント使用状況:")
            self.account_manager.print_status()

            return {
                "transcription": text_result,
                "summary": summary_result,
                "timestamps": timestamp_result,
            }

        except Exception as e:
            print(f"❌ 文字起こし処理エラー: {str(e)}")

            # エラーが発生した場合でも、制限関連のエラーの場合は使用回数を増加
            if "制限" in str(e) or "limit" in str(e).lower():
                if self.current_account:
                    self.account_manager.increment_usage(self.current_account["id"])
                    print(
                        f"⚠️ 制限エラーのため、アカウント {self.current_account['name']} の使用回数を更新しました"
                    )

            raise

    def set_language(self, language):
        """
        language: "Japanese" or "English"
        """
        language_select = self.wait.until(
            EC.presence_of_element_located((By.ID, "language"))
        )
        select = Select(language_select)
        select.select_by_value(language)

    def get_account_status(self):
        """アカウントの使用状況を取得"""
        return self.account_manager.get_all_accounts_status()

    def reset_account_usage(self, account_id=None):
        """アカウントの使用回数をリセット（テスト用）"""
        if account_id:
            self.account_manager.reset_account_usage(account_id)
        else:
            self.account_manager.reset_all_accounts()

    def print_account_status(self):
        """アカウントの使用状況を表示"""
        self.account_manager.print_status()

    def cleanup(self):
        """リソースのクリーンアップ"""
        if hasattr(self, "driver"):
            self.driver.quit()
            print("✅ ブラウザを閉じました")
