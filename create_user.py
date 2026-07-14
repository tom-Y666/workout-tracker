"""
管理者用ユーザー管理スクリプト

使い方:
  ユーザー作成:   python create_user.py add <username> <password>
  ロック解除:     python create_user.py unlock <username>
  ユーザー一覧:   python create_user.py list
"""
import sys
import auth


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "add":
        if len(sys.argv) != 4:
            print("Usage: python create_user.py add <username> <password>")
            sys.exit(1)
        username, password = sys.argv[2], sys.argv[3]
        if auth.register_user(username, password):
            print(f"✅ ユーザー '{username}' を作成しました")
        else:
            print(f"❌ ユーザー '{username}' は既に存在します")

    elif cmd == "unlock":
        if len(sys.argv) != 3:
            print("Usage: python create_user.py unlock <username>")
            sys.exit(1)
        username = sys.argv[2]
        if auth.unlock_user(username):
            print(f"✅ '{username}' のロックを解除しました")
        else:
            print(f"❌ ユーザー '{username}' が見つかりません")

    elif cmd == "list":
        users = auth.list_users()
        if not users:
            print("ユーザーが登録されていません")
            return
        print(f"{'ユーザー名':<20} {'ロック':<8} {'失敗回数'}")
        print("-" * 40)
        for name, info in users.items():
            locked = "🔒 ロック中" if info.get("locked") else "✅ 正常"
            fails = info.get("failed_attempts", 0)
            print(f"{name:<20} {locked:<10} {fails}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
