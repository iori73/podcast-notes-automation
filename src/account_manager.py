# src/account_manager.py
"""
Summary.fmアカウント管理システム
月5回制限を回避するため、複数アカウントを自動切り替え
"""

import json
from pathlib import Path
from datetime import datetime
from utils import load_config


class AccountManager:
    def __init__(self):
        """アカウント管理を初期化"""
        self.config = load_config()
        self.usage_file = Path("data/account_usage.json")
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        
        # アカウント設定をconfig.yamlから読み込む
        # 設定がない場合はデフォルトの空のアカウントリストを使用
        accounts_config = self.config.get("summary_fm", {}).get("accounts", [])
        
        if not accounts_config:
            # デフォルトアカウント（設定ファイルに追加する必要がある）
            print("⚠️ config.yamlにsummary_fm.accountsの設定が見つかりません")
            print("💡 以下の形式でconfig.yamlに追加してください:")
            print("""
summary_fm:
  accounts:
    - id: account1
      name: Account 1
      email: your_email1@example.com
      password: your_password1
    - id: account2
      name: Account 2
      email: your_email2@example.com
      password: your_password2
""")
            # 空のアカウントリストで初期化（エラーを避けるため）
            self.accounts = []
        else:
            self.accounts = accounts_config
        
        # 使用データを読み込む
        self.usage_data = self._load_usage_data()
    
    def _get_current_month_key(self):
        """現在の月のキーを取得（YYYY-MM形式）"""
        return datetime.now().strftime("%Y-%m")
    
    def _load_usage_data(self):
        """使用データをファイルから読み込む"""
        if self.usage_file.exists():
            try:
                with open(self.usage_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 使用データの読み込みエラー: {e}")
                return {}
        return {}
    
    def _save_usage_data(self):
        """使用データをファイルに保存"""
        try:
            with open(self.usage_file, "w", encoding="utf-8") as f:
                json.dump(self.usage_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 使用データの保存エラー: {e}")
    
    def _get_account_usage(self, account_id):
        """アカウントの使用回数を取得"""
        month_key = self._get_current_month_key()
        if account_id not in self.usage_data:
            self.usage_data[account_id] = {}
        if month_key not in self.usage_data[account_id]:
            self.usage_data[account_id][month_key] = 0
        return self.usage_data[account_id][month_key]
    
    def get_available_account(self):
        """使用可能なアカウントを取得（月5回未満のアカウント）"""
        if not self.accounts:
            print("⚠️ アカウントが設定されていません")
            return None
        
        month_key = self._get_current_month_key()
        
        for account in self.accounts:
            account_id = account["id"]
            usage = self._get_account_usage(account_id)
            
            if usage < 5:
                # 使用回数と残り回数を追加
                account_with_usage = account.copy()
                account_with_usage["usage"] = usage
                account_with_usage["remaining"] = 5 - usage
                return account_with_usage
        
        return None
    
    def increment_usage(self, account_id):
        """アカウントの使用回数を増加"""
        month_key = self._get_current_month_key()
        
        if account_id not in self.usage_data:
            self.usage_data[account_id] = {}
        if month_key not in self.usage_data[account_id]:
            self.usage_data[account_id][month_key] = 0
        
        self.usage_data[account_id][month_key] += 1
        self._save_usage_data()
    
    def print_status(self):
        """アカウント使用状況を表示"""
        if not self.accounts:
            print("⚠️ アカウントが設定されていません")
            return
        
        month_key = self._get_current_month_key()
        print(f"\n📊 アカウント使用状況 ({month_key}):")
        print("-" * 60)
        
        for account in self.accounts:
            account_id = account["id"]
            usage = self._get_account_usage(account_id)
            remaining = 5 - usage
            status = "✅" if remaining > 0 else "❌"
            
            print(
                f"{status} {account['name']} ({account['email']}): "
                f"{usage}/5 回使用 (残り: {remaining}回)"
            )
        print("-" * 60)
    
    def get_all_accounts_status(self):
        """全アカウントの状態を取得"""
        if not self.accounts:
            return []
        
        month_key = self._get_current_month_key()
        status_list = []
        
        for account in self.accounts:
            account_id = account["id"]
            usage = self._get_account_usage(account_id)
            status_list.append({
                "id": account_id,
                "name": account["name"],
                "email": account["email"],
                "usage": usage,
                "remaining": 5 - usage,
                "month": month_key
            })
        
        return status_list
    
    def reset_account_usage(self, account_id):
        """特定アカウントの使用回数をリセット"""
        month_key = self._get_current_month_key()
        if account_id in self.usage_data:
            if month_key in self.usage_data[account_id]:
                self.usage_data[account_id][month_key] = 0
                self._save_usage_data()
                print(f"✅ アカウント {account_id} の使用回数をリセットしました")
    
    def reset_all_accounts(self):
        """全アカウントの使用回数をリセット"""
        month_key = self._get_current_month_key()
        for account in self.accounts:
            account_id = account["id"]
            if account_id in self.usage_data:
                self.usage_data[account_id][month_key] = 0
        self._save_usage_data()
        print("✅ 全アカウントの使用回数をリセットしました")

