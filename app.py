import os
import traceback
from datetime import datetime

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

import utils.db_operations as db_operations
from utils.auto_check import (
    process_and_save_pdf_results,
)

# 環境変数の読み込み
load_dotenv()

# Document AIの設定
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("DOCUMENT_AI_LOCATION", "us")  # デフォルトは'us'
PROCESSOR_ID = os.getenv("DOCUMENT_AI_PROCESSOR_ID")

st.set_page_config(layout="wide")

# ログイン状態の確認
if not st.user.is_logged_in:
    if st.button("Googleアカウントでログイン", icon=":material/login:"):
        st.login()
    st.stop()

# ログイン後の処理
if st.user.is_logged_in:
    # ユーザーIDの取得（ログインユーザーのメールアドレスから）
    user_id = st.user.email

    # ユーザー名の取得（st.user.nameを使用）
    user_name = st.user.name

    try:
        # ユーザーが存在しない場合は作成
        user_created = db_operations.insert_user(user_id, user_name)
        
        # ユーザーが新規作成された場合、すべてのチェックグループに追加
        if user_created:
            # すべてのチェックグループを取得
            all_check_groups = db_operations.get_all_check_groups()
            
            # 各チェックグループに対してuser_check_groupsテーブルにレコードを追加
            for group in all_check_groups:
                try:
                    db_operations.insert_user_check_group(
                        user_id=user_id,
                        check_group_id=group["id"],
                        reviewer_id=user_id,  # 自分自身をレビュアーに設定
                        role="reviewer"
                    )
                except Exception as e:
                    st.error(f"チェックグループ '{group['name']}' への追加中にエラーが発生しました: {str(e)}")
    except Exception as e:
        st.error(f"ユーザー情報の処理中にエラーが発生しました: {str(e)}")
        st.code(traceback.format_exc())

st.title("Smart Check Sheet")

# ログアウトボタン
_, _, col2, col3 = st.columns([1, 1, 1, 1])
with col2:
    # 管理者のみユーザー管理ボタンを表示
    if user_id == os.getenv("ADMIN_USER"):
        if st.button(
            "ユーザー管理",
            icon=":material/people:",
            use_container_width=True,
            type="secondary",
        ):
            st.switch_page("pages/user_management.py")
with col3:
    if st.button(
        "ログアウトする",
        icon=":material/logout:",
        use_container_width=True,
        type="secondary",
    ):
        st.logout()  # ログアウト処理

# ユーザーIDの取得（ログインユーザーのメールアドレスから）
user_id = st.user.email

# 新しいチェックボタン
st.header("新しいチェックを開始する", divider=True)

# ユーザーのチェックグループ一覧を取得
user_groups = db_operations.get_user_check_groups(user_id)

if user_groups:
    # 3列のレイアウトでチェックグループを表示
    for i in range(0, len(user_groups), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(user_groups):
                group = user_groups[i + j]
                group_name = group["group_name"]
                check_group_id = group["check_group_id"]
                role = group["role"]

                with cols[j]:
                    st.subheader(group_name, divider="gray")

                    # チェックグループごとのボタンを作成
                    if st.button(
                        "手動チェックを開始する",
                        key=f"check_group_{check_group_id}",
                        use_container_width=True,
                        type="primary",
                    ):
                        # セッション状態のタイムスタンプを初期化
                        st.session_state["timestamp"] = None
                        # チェックグループIDをセッションに設定
                        st.session_state["check_group_id"] = check_group_id
                        # チェックシートページに遷移
                        st.switch_page("pages/checksheet.py")

                    # ファイルアップロード機能
                    uploaded_file = st.file_uploader(
                        "ファイルをアップロードして自動チェック",
                        type=["pdf"],
                        key=f"uploader_{check_group_id}",
                    )

                    if uploaded_file is not None:
                        # ファイル情報の表示
                        file_details = {
                            "ファイル名": uploaded_file.name,
                            "ファイルタイプ": uploaded_file.type,
                            "ファイルサイズ": f"{uploaded_file.size / 1024:.2f} KB",
                        }
                        st.write("### アップロードされたファイルの情報")
                        for key, value in file_details.items():
                            st.write(f"**{key}:** {value}")

                        # PDFファイルの内容を読み込む
                        pdf_content = uploaded_file.getvalue()

                        try:
                            # PDFファイルの処理と結果の保存
                            check_sheet_id = process_and_save_pdf_results(
                                pdf_content=pdf_content,
                                project_id=PROJECT_ID,
                                location=LOCATION,
                                processor_id=PROCESSOR_ID,
                                user_id=user_id,
                                check_group_id=check_group_id,
                            )

                            # セッション状態のタイムスタンプを初期化
                            st.session_state["timestamp"] = check_sheet_id
                            # チェックシートページに遷移
                            st.switch_page("pages/result.py")
                        except Exception as e:
                            st.error(f"テキスト抽出中にエラーが発生しました: {str(e)}")
                            st.error("スタックトレース:")
                            st.code(traceback.format_exc())

else:
    st.warning("あなたに割り当てられたチェックグループがありません。")

st.header("あなたのタスク", divider=True)

# 全てのタスクへのリンク
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
with col4:
    if st.button("📋 全タスク一覧はこちら", type="secondary", use_container_width=True):
        st.switch_page("pages/checksheet_list.py")

# 差し戻されたチェックシートを取得
try:
    user_tasks = db_operations.get_user_tasks(user_id)

    if user_tasks:
        # DataFrameに変換して表示
        df = pd.DataFrame(user_tasks)

        # リンク用のカラムを追加
        df["リンク"] = df["ID"].apply(lambda x: f"/result?id={x}")

        # 表形式で表示
        st.dataframe(
            df[
                [
                    "ID",
                    "グループ",
                    "担当者",
                    "レビュアー",
                    "日時",
                    "ステータス",
                    "リンク",
                ]
            ].sort_values(by="日時", ascending=False),
            column_config={
                "リンク": st.column_config.LinkColumn("リンク", display_text="詳細"),
            },
            hide_index=True,
        )
    else:
        st.info("あなたのタスクはありません。")

except Exception as e:
    st.error(f"ユーザータスクの取得中にエラーが発生しました: {str(e)}")
    st.code(traceback.format_exc())

# Pendingのチェック項目一覧を表示
st.header("新規チェック項目の追加の提案", divider=True)

# pendingのcheck_itemsを取得
pending_items = db_operations.get_pending_check_items(user_id)

if pending_items:
    st.info(
        f"あなたがレビュアーまたは管理者として担当している保留中のチェック項目が {len(pending_items)} 件あります。"
    )

    # 各pending項目を表示
    for item in pending_items:
        with st.expander(
            f"📋 {item['name']} - {item['category_name']} ({item['group_name']})"
        ):
            col1, col2 = st.columns([2, 1])

            with col1:
                st.write(f"**説明:** {item['description']}")
                st.write(f"**レベル:** {item['level']}")
                st.write(f"**ステータス:** {item['status']}")

            with col2:
                st.write(f"**作成日:** {item['created_at'].strftime('%Y-%m-%d %H:%M')}")
                st.write(f"**更新日:** {item['updated_at'].strftime('%Y-%m-%d %H:%M')}")

            # アクションボタン
            col3, col4, col5 = st.columns([1, 1, 2])

            with col3:
                if st.button(f"✅ 登録", key=f"approve_{item['id']}"):
                    try:
                        db_operations.approve_check_item(item["id"], user_id)
                        st.success(
                            f"「{item['name']}」をチェックシートに登録しました。"
                        )
                        st.rerun()  # ページを再読み込み
                    except Exception as e:
                        st.error(f"登録中にエラーが発生しました: {str(e)}")

            with col4:
                if st.button(f"❌ 却下", key=f"reject_{item['id']}"):
                    try:
                        db_operations.reject_check_item(item["id"], user_id)
                        st.success(f"「{item['name']}」を却下しました。")
                        st.rerun()  # ページを再読み込み
                    except Exception as e:
                        st.error(f"却下中にエラーが発生しました: {str(e)}")
else:
    st.info("あなたが担当している保留中のチェック項目はありません。")
