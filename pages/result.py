import streamlit as st

import utils.db_operations as db_operations


def main():
    st.set_page_config(layout="wide")

    # ユーザーIDの取得（ログインユーザーのメールアドレスから）
    user_id = st.user.email

    # クエリパラメータからタイムスタンプを取得
    try:
        timestamp = st.query_params.get("id")
        if not timestamp and "timestamp" in st.session_state:
            timestamp = st.session_state["timestamp"]

        if not timestamp:
            st.warning("結果IDが指定されていません。")
            return

        check_sheet = db_operations.load_check_sheet(timestamp)
        check_results = db_operations.load_check_results(timestamp)
        if not check_sheet or not check_results:
            st.error("指定された結果が見つかりませんでした。")
            return

        # レビュー結果の読み込み
        review = db_operations.load_check_results(timestamp, check_type="review")

        # チェックシートデータの読み込み
        check_group_id = check_sheet.get("check_group_id")
        if check_group_id:
            # 担当者のIDを使用してチェックシートデータを読み込み
            assignee_id = check_sheet.get("created_by")
            # auto_checkの場合はログインユーザーのIDを使用
            if assignee_id == "auto_check":
                assignee_id = user_id
            checksheet_data = db_operations.load_checksheet(
                check_group_id=check_group_id, user_id=assignee_id
            )
        else:
            st.error("チェックグループIDが見つかりませんでした。")
            return

        # チェックグループ名を取得
        check_group_name = "未分類"
        if check_group_id:
            try:
                check_group_name = db_operations.get_check_group_name(check_group_id)
            except Exception as e:
                st.error(f"チェックグループ名の取得中にエラーが発生しました: {e}")

        st.title(f"{check_group_name} チェックシート結果")

        # トップページに戻るボタンを右側に配置
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col4:
            if st.button("🏠 トップページに戻る", type="secondary", use_container_width=True):
                st.switch_page("app.py")

        # カテゴリーごとに結果を表示
        for category, items in checksheet_data.items():
            st.markdown(f"### {category}")

            # カテゴリーごとの表を作成
            table_md = "| CHK | REV | 項目 |\n|:---:|:---:|:---|\n"

            for item in items:
                # チェック状態を取得
                key = item["check_id"]
                check_result = check_results.get(key, {})
                checked = (
                    check_result.get("checked", False)
                    if isinstance(check_result, dict)
                    else check_result
                )
                check_status = "✅" if checked else "❌"

                # レビュー状態を取得
                if review:
                    review_result = review.get(key, {})
                    review_checked = (
                        review_result.get("checked", False)
                        if isinstance(review_result, dict)
                        else review_result
                    )
                    review_status = "✅" if review_checked else "❌"
                else:
                    review_status = "⏳"

                # コメントを取得
                comment = (
                    check_result.get("remarks", "")
                    if isinstance(check_result, dict)
                    else ""
                )
                comment_text = (
                    f"<br>**チェックコメント:** <br>{comment}" if comment else ""
                )

                # レビューコメントを取得
                if review:
                    review_comment = (
                        review_result.get("remarks", "")
                        if isinstance(review_result, dict)
                        else ""
                    )
                    review_comment_text = (
                        f"<br>**レビューコメント:** <br>{review_comment}"
                        if review_comment
                        else ""
                    )
                else:
                    review_comment_text = ""

                # 表の行を追加
                table_md += f"| {check_status} | {review_status} | **{item['name']}** (レベル: {item['level']})<br>*{item['description']}*{comment_text}{review_comment_text} |\n"

            # 表を表示
            st.markdown(table_md, unsafe_allow_html=True)

            st.divider()

        # 備考の表示
        col1, col2 = st.columns(2)
        with col1:
            if check_sheet.get("check_remarks"):
                st.markdown("### チェック備考")
                st.markdown(check_sheet["check_remarks"])

        # レビュー備考がある場合は表示
        with col2:
            if review and check_sheet.get("review_remarks"):
                st.markdown("### レビュー備考")
                st.markdown(check_sheet["review_remarks"])

        # 再チェックボタンを追加（画面の一番下）
        st.session_state["timestamp"] = timestamp
        col1, col2 = st.columns(2)
        with col1:
            if st.button("再チェック", type="primary", use_container_width=True):
                st.switch_page("pages/checksheet.py")
        with col2:
            if st.button("レビュー", type="primary", use_container_width=True):
                st.switch_page("pages/review.py")

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")


if __name__ == "__main__":
    main()
