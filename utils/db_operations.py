from sqlalchemy import (
    create_engine,
    Column,
    String,
    Boolean,
    Text,
    DateTime,
    Enum,
    ForeignKey,
    text,
    Integer,
    BigInteger,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from collections import defaultdict
import os
from google.cloud.sql.connector import Connector
from dotenv import load_dotenv
from typing import Dict

# 環境変数の読み込み
load_dotenv(override=True)

# 環境変数から接続情報を取得
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME")


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
    pool_pre_ping=True,  # 接続の有効性を確認
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def load_checksheet(check_group_id: int, user_id: str = None):
    """チェックシートデータを取得する（statusが'open'の項目のみ）"""
    try:
        db = next(get_db())
        # カテゴリーごとにデータをグループ化
        checksheet_by_category = defaultdict(list)

        # 最新の注意事項を取得（user_idが指定されている場合のみ）
        note_data = None
        if user_id:
            note_data = get_latest_check_item_note(user_id, check_group_id)

        # チェック項目を取得
        result = db.execute(
            text(
                """
            SELECT 
                ci.id,
                ci.name,
                c.name as category,
                ci.description,
                ci.level,
                cg.name as group_name
            FROM check_items ci
            JOIN categories c ON ci.category_id = c.id
            JOIN check_groups cg ON ci.group_id = cg.id
            WHERE ci.status = 'open' AND ci.group_id = :check_group_id
            ORDER BY c.name, ci.id
        """
            ),
            {"check_group_id": check_group_id},
        )

        for row in result:
            # check_idが一致する場合のみnoteを設定
            latest_note = ""
            if note_data and note_data.get("check_id") == row.id:
                latest_note = note_data.get("note_text", "")

            item = {
                "check_id": str(row.id),  # idを文字列として扱う
                "name": row.name,
                "category": row.category,
                "description": row.description,
                "level": row.level,
                "group": row.group_name,
                "note": latest_note,
            }
            checksheet_by_category[row.category].append(item)

        return checksheet_by_category
    except Exception as e:
        raise Exception(f"チェックシートデータの取得中にエラーが発生しました: {e}")


# モデル定義
class User(Base):
    __tablename__ = "users"
    user_id = Column(String(255), primary_key=True)
    user_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CheckGroup(Base):
    __tablename__ = "check_groups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class UserCheckGroup(Base):
    __tablename__ = "user_check_groups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    check_group_id = Column(BigInteger, ForeignKey("check_groups.id"), nullable=False)
    reviewer_id = Column(
        String(255), ForeignKey("users.user_id"), comment="レビュアーのユーザーID"
    )
    role = Column(Enum("member", "reviewer", "admin"), nullable=False, default="member")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CheckSheet(Base):
    __tablename__ = "check_sheets"
    check_sheet_id = Column(String(255), primary_key=True)
    check_status = Column(
        Enum("checking", "review_waiting", "returned", "completed"), nullable=False
    )
    created_by = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    reviewer_id = Column(
        String(255), ForeignKey("users.user_id"), comment="レビュアーのユーザーID"
    )
    check_group_id = Column(
        BigInteger, ForeignKey("check_groups.id"), comment="チェックグループID"
    )
    check_remarks = Column(Text, comment="チェック時の備考")
    review_remarks = Column(Text, comment="レビュー時の備考")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CheckResult(Base):
    __tablename__ = "check_results"
    check_sheet_id = Column(
        String(255), ForeignKey("check_sheets.check_sheet_id"), primary_key=True
    )
    check_id = Column(BigInteger, ForeignKey("check_items.id"), primary_key=True)
    check_type = Column(Enum("check", "review"), nullable=False)
    checked = Column(Boolean, nullable=False)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    remarks = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CheckItem(Base):
    __tablename__ = "check_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    level = Column(Integer, nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"))
    group_id = Column(Integer, ForeignKey("check_groups.id"))
    status = Column(
        Enum("open", "pending", "rejected", "closed"), nullable=False, default="open"
    )
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class CheckItemNote(Base):
    __tablename__ = "check_item_notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    check_id = Column(BigInteger, ForeignKey("check_items.id"), nullable=False)
    note_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise Exception(f"データベース操作中にエラーが発生しました: {e}")
    finally:
        db.close()


def create_user(user_id="default_user", user_name="デフォルトユーザー"):
    """ユーザーを作成する"""
    try:
        db = next(get_db())
        # ユーザーが存在するか確認
        existing_user = db.query(User).filter(User.user_id == user_id).first()
        if not existing_user:
            user = User(user_id=user_id, user_name=user_name)
            db.add(user)
            db.commit()
        return user_id
    except Exception as e:
        db.rollback()
        raise Exception(f"ユーザーの作成中にエラーが発生しました: {e}")


def update_results(
    check_sheet_id, results, check_remarks, user_id, status="review_waiting"
):
    """既存のチェックシートを更新する"""
    try:
        db = next(get_db())

        # 既存のチェックシートを確認
        existing_sheet = (
            db.query(CheckSheet)
            .filter(CheckSheet.check_sheet_id == check_sheet_id)
            .first()
        )
        if not existing_sheet:
            raise Exception(f"チェックシートが見つかりません: {check_sheet_id}")

        # チェックシートを更新
        existing_sheet.check_status = status
        existing_sheet.check_remarks = check_remarks

        # チェックシートの変更を即座に保存
        db.flush()

        # 既存のチェック結果を削除
        db.query(CheckResult).filter(
            CheckResult.check_sheet_id == check_sheet_id,
            CheckResult.check_type == "check",
        ).delete()

        # 削除を確定
        db.flush()

        # 新しいチェック結果を保存
        for check_id, result in results.items():
            check_result = CheckResult(
                check_sheet_id=check_sheet_id,
                check_id=int(check_id),  # 文字列を数値に変換
                check_type="check",
                checked=result["checked"],  # 辞書からcheckedの値を取得
                user_id=user_id,
                remarks=result.get(
                    "remarks"
                ),  # 辞書からremarksの値を取得（存在しない場合はNone）
            )
            db.add(check_result)

        db.commit()
        return check_sheet_id
    except Exception as e:
        db.rollback()
        raise Exception(f"チェックシートの更新中にエラーが発生しました: {e}")


def save_results(
    check_sheet_id,
    results,
    check_remarks,
    user_id,
    reviewer_id=None,
    check_group_id=None,
    status="review_waiting",
):
    """チェック結果を保存する"""
    try:
        db = next(get_db())

        # ユーザーの存在確認と作成
        create_user(user_id)

        # 既存のチェックシートを確認
        existing_sheet = (
            db.query(CheckSheet)
            .filter(CheckSheet.check_sheet_id == check_sheet_id)
            .first()
        )
        if existing_sheet:
            return update_results(
                check_sheet_id, results, check_remarks, user_id, status
            )

        # 新しいチェックシートを作成
        check_sheet = CheckSheet(
            check_sheet_id=check_sheet_id,
            check_status=status,
            created_by=user_id,
            reviewer_id=reviewer_id,
            check_group_id=check_group_id,
            check_remarks=check_remarks,
            review_remarks=None,
        )
        db.add(check_sheet)
        db.flush()  # チェックシートを先に保存

        # チェック結果の保存
        for check_id, result in results.items():
            check_result = CheckResult(
                check_sheet_id=check_sheet_id,
                check_id=int(check_id),  # 文字列を数値に変換
                check_type="check",
                checked=result["checked"],
                user_id=user_id,
                remarks=result["remarks"],
            )
            db.add(check_result)

        db.commit()
        return check_sheet_id
    except Exception as e:
        db.rollback()
        raise Exception(f"チェック結果の保存中にエラーが発生しました: {e}")


def save_review(check_sheet_id, review_results, review_remarks, user_id):
    """レビュー結果を保存する"""
    try:
        db = next(get_db())

        # 既存のレビュー結果を削除
        db.query(CheckResult).filter(
            CheckResult.check_sheet_id == check_sheet_id,
            CheckResult.check_type == "review",
        ).delete()

        db.flush()  # 削除を確定

        # 新しいレビュー結果を保存
        for check_id, result in review_results.items():
            review_result = CheckResult(
                check_sheet_id=check_sheet_id,
                check_id=int(check_id),  # 文字列を数値に変換
                check_type="review",
                checked=result["checked"],
                user_id=user_id,
                remarks=result["remarks"],
            )
            db.add(review_result)

        # チェックシートのステータスとレビュー備考を更新
        check_sheet = (
            db.query(CheckSheet)
            .filter(CheckSheet.check_sheet_id == check_sheet_id)
            .first()
        )
        if check_sheet:
            check_sheet.check_status = "completed"
            check_sheet.review_remarks = review_remarks

        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"レビュー結果の保存中にエラーが発生しました: {e}")


def save_review_with_status(
    check_sheet_id, review_results, review_remarks, user_id, status
):
    """指定されたステータスでレビュー結果を保存する"""
    try:
        db = next(get_db())

        # 既存のレビュー結果を削除
        db.query(CheckResult).filter(
            CheckResult.check_sheet_id == check_sheet_id,
            CheckResult.check_type == "review",
        ).delete()

        db.flush()  # 削除を確定

        # 新しいレビュー結果を保存
        for check_id, result in review_results.items():
            review_result = CheckResult(
                check_sheet_id=check_sheet_id,
                check_id=int(check_id),  # 文字列を数値に変換
                check_type="review",
                checked=result["checked"],
                user_id=user_id,
                remarks=result["remarks"],
            )
            db.add(review_result)

        # チェックシートのステータスとレビュー備考を更新
        check_sheet = (
            db.query(CheckSheet)
            .filter(CheckSheet.check_sheet_id == check_sheet_id)
            .first()
        )
        if check_sheet:
            check_sheet.check_status = status
            check_sheet.review_remarks = review_remarks

        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"レビュー結果の保存中にエラーが発生しました: {e}")


def load_check_sheet(check_sheet_id):
    """チェックシート情報を取得する"""
    try:
        db = next(get_db())
        check_sheet = (
            db.query(CheckSheet)
            .filter(CheckSheet.check_sheet_id == check_sheet_id)
            .first()
        )

        if not check_sheet:
            return None

        return {
            "check_sheet_id": check_sheet.check_sheet_id,
            "check_status": check_sheet.check_status,
            "created_by": check_sheet.created_by,
            "reviewer_id": check_sheet.reviewer_id,
            "check_group_id": check_sheet.check_group_id,
            "check_remarks": check_sheet.check_remarks,
            "review_remarks": check_sheet.review_remarks,
            "created_at": check_sheet.created_at,
            "updated_at": check_sheet.updated_at,
        }
    except Exception as e:
        raise Exception(f"チェックシート情報の取得中にエラーが発生しました: {e}")


def load_check_results(check_sheet_id, check_type="check"):
    """チェック結果を取得する"""
    try:
        db = next(get_db())
        results = (
            db.query(CheckResult)
            .filter(
                CheckResult.check_sheet_id == check_sheet_id,
                CheckResult.check_type == check_type,
            )
            .all()
        )

        return (
            {
                str(result.check_id): {
                    "checked": result.checked,
                    "remarks": result.remarks,
                }
                for result in results
            }
            if results
            else {}
        )
    except Exception as e:
        raise Exception(f"チェック結果の取得中にエラーが発生しました: {e}")


def load_review(check_sheet_id):
    """レビュー結果を取得する"""
    try:
        db = next(get_db())
        reviews = (
            db.query(CheckResult)
            .filter(
                CheckResult.check_sheet_id == check_sheet_id,
                CheckResult.check_type == "review",
            )
            .all()
        )

        return (
            {str(review.check_id): review.checked for review in reviews}
            if reviews
            else None
        )
    except Exception as e:
        raise Exception(f"レビュー結果の取得中にエラーが発生しました: {e}")


def get_all_results():
    """すべてのチェックシート結果を取得する"""
    try:
        db = next(get_db())
        check_sheets = db.query(CheckSheet).all()

        results_list = []
        for sheet in check_sheets:
            # チェック結果の集計
            check_results = (
                db.query(CheckResult)
                .filter(
                    CheckResult.check_sheet_id == sheet.check_sheet_id,
                    CheckResult.check_type == "check",
                )
                .all()
            )

            checked_count = sum(1 for r in check_results if r.checked)
            total_checks = len(check_results)

            # レビューの状態を確認
            review_exists = (
                db.query(CheckResult)
                .filter(
                    CheckResult.check_sheet_id == sheet.check_sheet_id,
                    CheckResult.check_type == "review",
                )
                .first()
                is not None
            )

            review_status = "レビュー済み" if review_exists else "レビュー待ち"

            # グループ情報を取得
            group_info = db.execute(
                text(
                    """
                SELECT DISTINCT cg.name as group_name
                FROM check_results cr
                JOIN check_items ci ON cr.check_id = ci.id
                JOIN check_groups cg ON ci.group_id = cg.id
                WHERE cr.check_sheet_id = :check_sheet_id
            """
                ),
                {"check_sheet_id": sheet.check_sheet_id},
            ).first()

            group_name = group_info.group_name if group_info else "未分類"

            # 担当者とレビュアーの名前を取得
            assignee_name = "不明"
            reviewer_name = "未設定"

            if sheet.created_by:
                assignee_user = (
                    db.query(User).filter(User.user_id == sheet.created_by).first()
                )
                assignee_name = assignee_user.user_name if assignee_user else "不明"

            if sheet.reviewer_id:
                reviewer_user = (
                    db.query(User).filter(User.user_id == sheet.reviewer_id).first()
                )
                reviewer_name = reviewer_user.user_name if reviewer_user else "不明"

            # ステータスを日本語に変換
            status_mapping = {
                "checking": "チェック中",
                "review_waiting": "レビュー待ち",
                "returned": "差し戻し",
                "completed": "完了",
            }
            status_japanese = status_mapping.get(sheet.check_status, sheet.check_status)

            results_list.append(
                {
                    "ID": sheet.check_sheet_id,
                    "グループ": group_name,
                    "担当者": assignee_name,
                    "レビュアー": reviewer_name,
                    "日時": sheet.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "チェック済み項目": f"{checked_count}/{total_checks}",
                    "備考": sheet.check_remarks if sheet.check_remarks else "なし",
                    "ステータス": status_japanese,
                }
            )

        return results_list
    except Exception as e:
        raise Exception(f"チェックシート結果の取得中にエラーが発生しました: {e}")


def get_check_group_id_by_check_id(check_id: str) -> int:
    """チェックIDからグループIDを取得する"""
    try:
        db = next(get_db())
        result = db.execute(
            text(
                """
            SELECT group_id 
            FROM check_items 
            WHERE id = :check_id
        """
            ),
            {"check_id": int(check_id)},
        ).first()

        return result.group_id if result else None
    except Exception as e:
        raise Exception(f"グループIDの取得中にエラーが発生しました: {e}")


def get_user_check_groups(user_id: str) -> list:
    """ユーザーのチェックグループ一覧を取得する"""
    try:
        db = next(get_db())
        result = db.execute(
            text(
                """
            SELECT 
                ucg.check_group_id,
                cg.name as group_name,
                ucg.role
            FROM user_check_groups ucg
            JOIN check_groups cg ON ucg.check_group_id = cg.id
            WHERE ucg.user_id = :user_id
            ORDER BY cg.name
        """
            ),
            {"user_id": user_id},
        ).fetchall()

        return [
            {
                "check_group_id": row.check_group_id,
                "group_name": row.group_name,
                "role": row.role,
            }
            for row in result
        ]
    except Exception as e:
        raise Exception(f"ユーザーのチェックグループ取得中にエラーが発生しました: {e}")


def get_user_reviewer_id(user_id: str, check_group_id: int) -> str:
    """ユーザーのレビュアーIDを取得する"""
    try:
        db = next(get_db())
        result = db.execute(
            text(
                """
            SELECT reviewer_id 
            FROM user_check_groups 
            WHERE user_id = :user_id AND check_group_id = :check_group_id
            LIMIT 1
        """
            ),
            {"user_id": user_id, "check_group_id": check_group_id},
        ).first()

        return result.reviewer_id if result and result.reviewer_id else None
    except Exception as e:
        raise Exception(f"レビュアーIDの取得中にエラーが発生しました: {e}")


def get_categories_by_group_id(group_id: int) -> list:
    """指定されたグループIDに関連するカテゴリとカテゴリIDの一覧を取得する"""
    try:
        db = next(get_db())
        result = db.execute(
            text(
                """
            SELECT DISTINCT 
                c.id as category_id,
                c.name as category_name
            FROM categories c
            JOIN check_items ci ON c.id = ci.category_id
            WHERE ci.group_id = :group_id
            ORDER BY c.name
        """
            ),
            {"group_id": group_id},
        ).fetchall()

        return [
            {"category_id": row.category_id, "category_name": row.category_name}
            for row in result
        ]
    except Exception as e:
        raise Exception(f"カテゴリ一覧の取得中にエラーが発生しました: {e}")


def add_check_item(item: Dict, group_id: int) -> None:
    """
    新しいチェック項目をデータベースに追加する（statusは'pending'で追加）

    Args:
        item (Dict): 追加するチェック項目の情報
            {
                "name": str,
                "description": str,
                "level": int,
                "category_id": int
            }
        group_id (int): チェックグループID
    """
    try:
        db = next(get_db())

        # 新しいチェック項目を作成
        check_item = CheckItem(
            name=item["name"],
            description=item["description"],
            level=item["level"],
            category_id=item["category_id"],
            group_id=group_id,
            status="pending",  # statusを'pending'に設定
        )

        db.add(check_item)
        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"チェック項目の追加中にエラーが発生しました: {e}")


def insert_user(user_id: str, user_name: str) -> bool:
    """
    ユーザーデータを挿入する

    Args:
        user_id (str): ユーザーID（メールアドレス）
        user_name (str): ユーザー名
        
    Returns:
        bool: ユーザーが新規作成された場合はTrue、既に存在する場合はFalse
    """
    try:
        db = next(get_db())

        # 既存のユーザーをチェック
        existing_user = db.query(User).filter(User.user_id == user_id).first()
        if existing_user:
            print(f"ユーザー {user_id} は既に存在します。")
            return False

        # 新しいユーザーを作成
        user = User(user_id=user_id, user_name=user_name)
        db.add(user)
        db.commit()
        print(f"ユーザー {user_id} が正常に作成されました。")
        return True
    except Exception as e:
        db.rollback()
        raise Exception(f"ユーザーの挿入中にエラーが発生しました: {e}")


def insert_user_check_group(
    user_id: str, check_group_id: int, reviewer_id: str = None, role: str = "member"
) -> None:
    """
    ユーザーとチェックグループの関連データを挿入する

    Args:
        user_id (str): ユーザーID（メールアドレス）
        check_group_id (int): チェックグループID
        reviewer_id (str, optional): レビュアーのユーザーID
        role (str): ロール（'member', 'reviewer', 'admin'）
    """
    try:
        db = next(get_db())

        # 既存の関連をチェック
        existing_group = (
            db.query(UserCheckGroup)
            .filter(
                UserCheckGroup.user_id == user_id,
                UserCheckGroup.check_group_id == check_group_id,
            )
            .first()
        )

        if existing_group:
            print(
                f"ユーザー {user_id} は既にチェックグループ {check_group_id} に所属しています。"
            )
            return

        # 新しい関連を作成
        user_check_group = UserCheckGroup(
            user_id=user_id,
            check_group_id=check_group_id,
            reviewer_id=reviewer_id,
            role=role,
        )
        db.add(user_check_group)
        db.commit()
        print(
            f"ユーザー {user_id} をチェックグループ {check_group_id} に追加しました（ロール: {role}）。"
        )
    except Exception as e:
        db.rollback()
        raise Exception(f"ユーザーチェックグループの挿入中にエラーが発生しました: {e}")


def get_all_users() -> list:
    """すべてのユーザー一覧を取得する"""
    try:
        db = next(get_db())
        users = db.query(User).order_by(User.user_name).all()

        return [
            {"user_id": user.user_id, "user_name": user.user_name} for user in users
        ]
    except Exception as e:
        raise Exception(f"ユーザー一覧の取得中にエラーが発生しました: {e}")


def get_all_check_groups() -> list:
    """すべてのチェックグループ一覧を取得する"""
    try:
        db = next(get_db())
        result = db.execute(
            text(
                """
            SELECT id, name
            FROM check_groups
            ORDER BY name
        """
            )
        ).fetchall()

        return [{"id": row.id, "name": row.name} for row in result]
    except Exception as e:
        raise Exception(f"チェックグループ一覧の取得中にエラーが発生しました: {e}")


def get_check_group_name(check_group_id: int) -> str:
    """指定されたチェックグループIDから名前を取得する"""
    try:
        db = next(get_db())
        result = db.execute(
            text(
                """
            SELECT name
            FROM check_groups
            WHERE id = :check_group_id
        """
            ),
            {"check_group_id": check_group_id},
        ).first()

        return result.name if result else "未分類"
    except Exception as e:
        raise Exception(f"チェックグループ名の取得中にエラーが発生しました: {e}")


def get_pending_check_items(user_id: str) -> list:
    """ログインユーザーがreviewerまたはadminであるuser_check_groupに紐づく、statusがpendingのcheck_itemsを取得する"""
    try:
        db = next(get_db())

        # ユーザーがreviewerまたはadminであるcheck_group_idを取得
        result = db.execute(
            text(
                """
            SELECT DISTINCT ucg.check_group_id
            FROM user_check_groups ucg
            WHERE ucg.user_id = :user_id 
            AND ucg.role IN ('reviewer', 'admin')
        """
            ),
            {"user_id": user_id},
        )

        check_group_ids = [row.check_group_id for row in result]

        if not check_group_ids:
            return []

        # 該当するcheck_group_idに紐づく、statusがpendingのcheck_itemsを取得
        result = db.execute(
            text(
                """
            SELECT 
                ci.id,
                ci.name,
                ci.description,
                ci.level,
                ci.status,
                ci.group_id,
                c.name as category_name,
                cg.name as group_name,
                ci.created_at,
                ci.updated_at
            FROM check_items ci
            JOIN categories c ON ci.category_id = c.id
            JOIN check_groups cg ON ci.group_id = cg.id
            WHERE ci.status = 'pending' 
            AND ci.group_id IN :check_group_ids
            ORDER BY ci.created_at DESC
        """
            ),
            {"check_group_ids": tuple(check_group_ids)},
        )

        pending_items = []
        for row in result:
            item = {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "level": row.level,
                "status": row.status,
                "group_id": row.group_id,
                "category_name": row.category_name,
                "group_name": row.group_name,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            pending_items.append(item)

        return pending_items
    except Exception as e:
        raise Exception(f"pendingのcheck_items取得中にエラーが発生しました: {e}")


def reject_check_item(check_item_id: int, user_id: str) -> None:
    """check_itemのstatusをrejectedに更新する"""
    try:
        db = next(get_db())

        # check_itemが存在し、ユーザーがreviewerまたはadminであることを確認
        result = db.execute(
            text(
                """
            SELECT ci.id 
            FROM check_items ci
            JOIN user_check_groups ucg ON ci.group_id = ucg.check_group_id
            WHERE ci.id = :check_item_id 
            AND ucg.user_id = :user_id 
            AND ucg.role IN ('reviewer', 'admin')
            AND ci.status = 'pending'
        """
            ),
            {"check_item_id": check_item_id, "user_id": user_id},
        )

        if not result.fetchone():
            raise Exception("却下権限がないか、項目が見つかりません")

        # statusをrejectedに更新
        db.execute(
            text(
                """
            UPDATE check_items 
            SET status = 'rejected', updated_at = NOW()
            WHERE id = :check_item_id
        """
            ),
            {"check_item_id": check_item_id},
        )

        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"チェック項目の却下中にエラーが発生しました: {e}")


def approve_check_item(check_item_id: int, user_id: str) -> None:
    """check_itemのstatusをopenに更新してチェックシートに登録する"""
    try:
        db = next(get_db())

        # check_itemが存在し、ユーザーがreviewerまたはadminであることを確認
        result = db.execute(
            text(
                """
            SELECT ci.id 
            FROM check_items ci
            JOIN user_check_groups ucg ON ci.group_id = ucg.check_group_id
            WHERE ci.id = :check_item_id 
            AND ucg.user_id = :user_id 
            AND ucg.role IN ('reviewer', 'admin')
            AND ci.status = 'pending'
        """
            ),
            {"check_item_id": check_item_id, "user_id": user_id},
        )

        if not result.fetchone():
            raise Exception("承認権限がないか、項目が見つかりません")

        # statusをopenに更新
        db.execute(
            text(
                """
            UPDATE check_items 
            SET status = 'open', updated_at = NOW()
            WHERE id = :check_item_id
        """
            ),
            {"check_item_id": check_item_id},
        )

        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"チェック項目の承認中にエラーが発生しました: {e}")


def add_check_item_note(check_id: int, user_id: str, note_text: str) -> None:
    """
    チェック項目の注意事項をデータベースに追加する

    Args:
        check_id (int): チェック項目のID
        user_id (str): 注意事項を作成したユーザーID
        note_text (str): 注意事項の内容
    """
    try:
        db = next(get_db())

        # check_idが存在するかチェック
        check_item = db.query(CheckItem).filter(CheckItem.id == check_id).first()
        if not check_item:
            raise Exception(f"Check ID {check_id} は存在しません")

        # 新しい注意事項を作成
        check_item_note = CheckItemNote(
            check_id=check_id, user_id=user_id, note_text=note_text
        )

        db.add(check_item_note)
        db.commit()
    except Exception as e:
        db.rollback()
        raise Exception(f"注意事項の追加中にエラーが発生しました: {e}")


def get_latest_check_item_note(user_id: str, check_group_id: int) -> dict:
    """
    指定されたユーザーとチェックグループの最新の注意事項を取得する

    Args:
        user_id (str): ユーザーID
        check_group_id (int): チェックグループID

    Returns:
        dict: 最新の注意事項の情報（存在しない場合は空の辞書）
            {
                "check_id": int,
                "note_text": str
            }
    """
    try:
        db = next(get_db())

        # 最新の注意事項を取得（ユーザーIDとcheck_group_idでフィルタリング）
        result = db.execute(
            text(
                """
            SELECT cin.check_id, cin.note_text 
            FROM check_item_notes cin
            JOIN check_items ci ON cin.check_id = ci.id
            JOIN user_check_groups ucg ON ci.group_id = ucg.check_group_id
            WHERE cin.user_id = :user_id
            AND ucg.check_group_id = :check_group_id
            AND ucg.user_id = :user_id
            ORDER BY cin.created_at DESC 
            LIMIT 1
        """
            ),
            {"user_id": user_id, "check_group_id": check_group_id},
        ).first()

        if result:
            return {"check_id": result.check_id, "note_text": result.note_text}
        else:
            return {}
    except Exception as e:
        raise Exception(f"注意事項の取得中にエラーが発生しました: {e}")


def get_user_tasks(user_id: str) -> list:
    """指定されたユーザーのタスク（完了以外のステータスで、担当者またはレビュアーがユーザーであるチェックシート）を取得する"""
    try:
        db = next(get_db())

        # 完了以外のステータスで、担当者またはレビュアーがユーザーであるチェックシートを取得
        check_sheets = (
            db.query(CheckSheet)
            .filter(
                (CheckSheet.check_status != "completed")
                & (
                    (CheckSheet.created_by == user_id)
                    | (CheckSheet.reviewer_id == user_id)
                )
            )
            .order_by(CheckSheet.updated_at.desc())
            .all()
        )

        results_list = []
        for sheet in check_sheets:
            # チェック結果の集計
            check_results = (
                db.query(CheckResult)
                .filter(
                    CheckResult.check_sheet_id == sheet.check_sheet_id,
                    CheckResult.check_type == "check",
                )
                .all()
            )

            checked_count = sum(1 for r in check_results if r.checked)
            total_checks = len(check_results)

            # レビューの状態を確認
            review_exists = (
                db.query(CheckResult)
                .filter(
                    CheckResult.check_sheet_id == sheet.check_sheet_id,
                    CheckResult.check_type == "review",
                )
                .first()
                is not None
            )

            review_status = "レビュー済み" if review_exists else "レビュー待ち"

            # グループ情報を取得
            group_info = db.execute(
                text(
                    """
                SELECT DISTINCT cg.name as group_name
                FROM check_results cr
                JOIN check_items ci ON cr.check_id = ci.id
                JOIN check_groups cg ON ci.group_id = cg.id
                WHERE cr.check_sheet_id = :check_sheet_id
            """
                ),
                {"check_sheet_id": sheet.check_sheet_id},
            ).first()

            group_name = group_info.group_name if group_info else "未分類"

            # 担当者とレビュアーの名前を取得
            assignee_name = "不明"
            reviewer_name = "未設定"

            if sheet.created_by:
                assignee_user = (
                    db.query(User).filter(User.user_id == sheet.created_by).first()
                )
                assignee_name = assignee_user.user_name if assignee_user else "不明"

            if sheet.reviewer_id:
                reviewer_user = (
                    db.query(User).filter(User.user_id == sheet.reviewer_id).first()
                )
                reviewer_name = reviewer_user.user_name if reviewer_user else "不明"

            # ステータスを日本語に変換
            status_mapping = {
                "checking": "チェック中",
                "review_waiting": "レビュー待ち",
                "returned": "差し戻し",
                "completed": "完了",
            }
            status_japanese = status_mapping.get(sheet.check_status, sheet.check_status)

            results_list.append(
                {
                    "ID": sheet.check_sheet_id,
                    "グループ": group_name,
                    "担当者": assignee_name,
                    "レビュアー": reviewer_name,
                    "日時": sheet.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "チェック済み項目": f"{checked_count}/{total_checks}",
                    "備考": sheet.check_remarks if sheet.check_remarks else "なし",
                    "ステータス": status_japanese,
                }
            )

        return results_list
    except Exception as e:
        raise Exception(f"ユーザータスクの取得中にエラーが発生しました: {e}")
