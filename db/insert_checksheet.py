import json
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from google.cloud.sql.connector import Connector
import os
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv(override=True)

# 環境変数から接続情報を取得
INSTANCE_CONNECTION_NAME = os.getenv('INSTANCE_CONNECTION_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASS = os.getenv('DB_PASS')
DB_NAME = os.getenv('DB_NAME')

def getconn():
    """データベース接続を取得する"""
    connector = Connector()
    conn = connector.connect(
        INSTANCE_CONNECTION_NAME,
        "pymysql",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
    )
    return conn

# データベース接続設定
engine = create_engine(
    "mysql+pymysql://",
    creator=getconn,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # 30分で接続を再作成
    pool_pre_ping=True  # 接続の有効性を確認
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """データベースセッションを取得する"""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise Exception(f"データベース操作中にエラーが発生しました: {e}")
    finally:
        db.close()

def insert_checksheet_data():
    """チェックシートデータをデータベースに挿入する"""
    try:
        # JSONファイルの読み込み
        with open('data/sample_checksheet.json', 'r', encoding='utf-8') as f:
            checksheet_data = json.load(f)

        db = next(get_db())
        
        # 既存データの削除（外部キー制約を考慮した順序）
        print("既存データを削除しています...")
        db.execute(text("DELETE FROM check_item_notes"))
        db.execute(text("DELETE FROM questions_answers"))
        db.execute(text("DELETE FROM check_results"))
        db.execute(text("DELETE FROM check_sheets"))
        db.execute(text("DELETE FROM check_items"))
        db.execute(text("DELETE FROM user_check_groups"))
        db.execute(text("DELETE FROM check_groups"))
        db.execute(text("DELETE FROM categories"))
        db.execute(text("DELETE FROM users"))
        db.commit()
        print("既存データの削除が完了しました。")
        
        # auto_checkユーザーの作成
        print("auto_checkユーザーを作成しています...")
        db.execute(
            text("INSERT INTO users (user_id, user_name) VALUES (:user_id, :user_name)"),
            {"user_id": "auto_check", "user_name": "自動チェックユーザー"}
        )
        print("auto_checkユーザーの作成が完了しました。")
        
        # カテゴリーの挿入
        print("カテゴリーを挿入しています...")
        categories = set(item['category'] for item in checksheet_data['checklist'])
        category_map = {}
        for category in categories:
            result = db.execute(
                text("INSERT INTO categories (name) VALUES (:name)"),
                {"name": category}
            )
            category_map[category] = result.lastrowid
        print("カテゴリーの挿入が完了しました。")

        # グループの挿入
        print("グループを挿入しています...")
        groups = set(item['group'] for item in checksheet_data['checklist'])
        group_map = {}
        for group in groups:
            result = db.execute(
                text("INSERT INTO check_groups (name) VALUES (:name)"),
                {"name": group}
            )
            group_map[group] = result.lastrowid
        print("グループの挿入が完了しました。")

        # チェック項目の挿入
        print("チェック項目を挿入しています...")
        for item in checksheet_data['checklist']:
            result = db.execute(
                text("""
                    INSERT INTO check_items 
                    (name, category_id, description, level, group_id, status)
                    VALUES 
                    (:name, :category_id, :description, :level, :group_id, :status)
                """),
                {
                    "name": item['name'],
                    "category_id": category_map[item['category']],
                    "description": item['description'],
                    "level": item['level'],
                    "group_id": group_map[item['group']],
                    "status": "open"
                }
            )
            # 挿入されたcheck_itemのidを保存（後でcheck_resultsで使用する場合）
            item['inserted_id'] = result.lastrowid

        db.commit()
        print("チェックシートデータの挿入が完了しました。")

    except Exception as e:
        print(f"エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    insert_checksheet_data() 