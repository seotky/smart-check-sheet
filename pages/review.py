import pydub
import streamlit as st
import traceback

import utils.db_operations as db_operations
import utils.voice_utils as voice_utils
from utils.suggest_check_items import suggest_check_items, add_suggested_items
from utils.suggest_user_note import suggest_check_note, add_suggested_note


def main():
    # ユーザーIDの取得（ログインユーザーのメールアドレスから）
    user_id = st.user.email

    st.set_page_config(layout="wide")
    
    # クエリパラメータからタイムスタンプを取得
    try:
        timestamp = st.query_params.get("id")
        if not timestamp and "timestamp" in st.session_state:
            timestamp = st.session_state["timestamp"]

        if not timestamp:
            st.warning("結果IDが指定されていません。")
            return

        # チェックシート情報を読み込む
        check_sheet = db_operations.load_check_sheet_metadata(timestamp)
        if not check_sheet:
            st.error("指定されたチェックシートが見つかりませんでした。")
            return

        # チェック結果を読み込む
        check_results = db_operations.load_check_results(timestamp)
        if not check_results:
            st.error("チェック結果が見つかりませんでした。")
            return

        # 既存のレビュー結果を読み込む
        existing_review = db_operations.load_check_results(
            timestamp, check_type="review"
        )

        # チェックシートデータの読み込み
        check_group_id = check_sheet.get("check_group_id")
        if check_group_id:
            # 担当者のIDを使用してチェックシートデータを読み込み
            assignee_id = check_sheet.get("created_by")
            # auto_checkの場合はログインユーザーのIDを使用
            if assignee_id == "auto_check":
                assignee_id = user_id
            checksheet_data = db_operations.load_checksheet_by_check_sheet_id(
                check_sheet_id=timestamp, user_id=assignee_id
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

        st.title(f"{check_group_name} レビュー")

        # トップページに戻るボタンを右側に配置
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        with col4:
            if st.button("🏠 トップページに戻る", type="secondary", use_container_width=True):
                st.switch_page("app.py")

        # 音声認識処理
        voice_check_results = {}
        voice_overall_remarks = ""

        record = voice_utils.WebRTCRecord()

        audio_buffer = record.recording("test")
        if audio_buffer:
            full_text = voice_utils.transcribe_audio_with_google(audio_buffer)
            st.session_state["audio_buffer"] = pydub.AudioSegment.empty()

            if full_text:
                gemini_response = voice_utils.auto_fill_check_sheet(
                    check_group_id, full_text
                )
                voice_check_results = {
                    result.check_id: {
                        "checked": result.checked,
                        "remarks": result.remarks,
                    }
                    for result in gemini_response
                    if isinstance(result, voice_utils.CheckResult)
                }
                voice_overall_remarks = [
                    result.overall_remarks
                    for result in gemini_response
                    if isinstance(result, voice_utils.OverallResult)
                ]
                st.session_state["results"] = voice_check_results.copy()
                voice_overall_remarks = (
                    voice_overall_remarks[0] if len(voice_overall_remarks) > 0 else ""
                )
                # 結果を保存
                db_operations.save_review_with_status(
                    timestamp,
                    st.session_state["results"],
                    voice_overall_remarks,
                    user_id,
                    "review_waiting",
                )

                # 結果画面に遷移
                st.session_state["timestamp"] = timestamp
                st.rerun()
            else:
                st.warning("音声認識結果が空でした。音声を録音してください。")

        # レビュー結果を格納する辞書
        review_results = {}

        # フォームの作成
        with st.form("review_form"):
            # カテゴリーごとに結果を表示
            for category, items in checksheet_data.items():
                st.subheader(f"{category}", divider=True)

                for item in items:
                    col1, col2 = st.columns([1, 9])

                    with col1:
                        # チェック状態を表示
                        check_id = item["check_id"]
                        checked = check_results.get(check_id, {}).get("checked", False)
                        st.markdown(f"{'✅' if checked else '❌'}")

                        # レビューチェックボックス
                        review_key = f"review_{check_id}"
                        # 既存のレビュー結果があれば初期値として設定
                        if existing_review:
                            initial_review_checked = (
                                existing_review.get(check_id)["checked"]
                                if existing_review.get(check_id)
                                else False
                            )
                        else:
                            initial_review_checked = False
                        review_checked = st.checkbox(
                            "レビューOK",
                            key=review_key,
                            label_visibility="collapsed",
                            value=initial_review_checked,
                        )
                        review_results[check_id] = {"checked": review_checked}

                    with col2:
                        # 項目名と説明を表示
                        st.markdown(f"**{item['name']}** (レベル: {item['level']})")
                        st.markdown(f"*{item['description']}*")

                        # 注意事項がある場合は表示
                        if item.get("note"):
                            st.warning(item["note"])

                        # コメントを表示
                        comment = check_results.get(check_id, {}).get("remarks", "")
                        if comment:
                            st.markdown(
                                f"**コメント:** <br>{comment}", unsafe_allow_html=True
                            )

                        # レビューコメント入力
                        review_comment_key = f"review_comment_{check_id}"
                        if existing_review:
                            # 既存のレビューコメントがあれば初期値として設定
                            initial_review_comment = (
                                existing_review.get(check_id)["remarks"]
                                if existing_review.get(check_id)
                                else ""
                            )
                        else:
                            initial_review_comment = ""
                        review_comment = st.text_area(
                            "レビューコメント",
                            key=review_comment_key,
                            height=68,
                            value=initial_review_comment,
                        )
                        review_results[check_id]["remarks"] = review_comment

            # 備考の表示
            if check_sheet["check_remarks"]:
                st.markdown("### その他備考")
                st.markdown(check_sheet["check_remarks"])

            # レビュー備考欄
            st.markdown("### レビュー備考")
            # 既存のレビュー備考があれば初期値として設定
            initial_review_remarks = (
                check_sheet.get("review_remarks", "") if existing_review else ""
            )
            review_remarks = st.text_area(
                "レビューに関する追加のコメントや特記事項があればご記入ください",
                key="review_remarks",
                height=100,
                value=initial_review_remarks,
                placeholder="例：\n・改善が必要な点\n・特に良い点\n・次回レビュー時の確認事項など",
            )

            # ボタン配置
            col1, col2, col3 = st.columns([1, 1, 2])

            with col1:
                # 差し戻しボタン
                return_button = st.form_submit_button("差し戻し", type="secondary")

            with col2:
                # 完了ボタン
                complete_button = st.form_submit_button("完了", type="primary")

            # 差し戻しボタンが押された場合の処理
            if return_button:

                # レビュー結果を保存（ステータス: returned）
                db_operations.save_review_with_status(
                    timestamp, review_results, review_remarks, user_id, "returned"
                )

                # 結果画面に遷移
                st.session_state["timestamp"] = timestamp
                st.switch_page("pages/result.py")

            # 完了ボタンが押された場合の処理
            if complete_button:

                # レビュー結果を保存（ステータス: completed）
                db_operations.save_review_with_status(
                    timestamp, review_results, review_remarks, user_id, "completed"
                )

                # 新しいチェック項目の提案を生成
                try:
                    suggested_items = suggest_check_items(
                        review_results, review_remarks, check_sheet["check_group_id"]
                    )
                    if suggested_items:
                        add_suggested_items(
                            suggested_items, check_sheet["check_group_id"]
                        )
                        st.success("新しいチェック項目が提案されました")
                except Exception as e:
                    st.warning(f"チェック項目の提案中にエラーが発生しました: {e}")

                # 新しいチェック注意事項の提案を生成
                try:
                    suggested_note = suggest_check_note(review_results)
                    if suggested_note:
                        add_suggested_note(suggested_note, user_id)
                        st.success("新しいチェック注意事項が提案されました")
                except Exception as e:
                    st.warning(f"チェック注意事項の提案中にエラーが発生しました: {e}")

                # 結果画面に遷移
                st.session_state["timestamp"] = timestamp
                st.switch_page("pages/result.py")
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        st.error(f"スタックトレース:\n{traceback.format_exc()}")


if __name__ == "__main__":
    main()
