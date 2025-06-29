from datetime import datetime

import pydub
import streamlit as st

import utils.db_operations as db_operations
import utils.voice_utils as voice_utils


def main():
    st.set_page_config(layout="wide")

    # 変数の初期化
    check_sheet = None
    check_results = None
    review_results = None

    # 結果を格納する辞書
    st.session_state["results"] = {}

    # チェックグループIDを取得（セッションから）
    check_group_id = st.session_state.get("check_group_id")

    # クエリパラメータからタイムスタンプを取得
    try:
        timestamp = st.query_params.get("id")
        if not timestamp and "timestamp" in st.session_state:
            timestamp = st.session_state["timestamp"]

        if timestamp:
            check_sheet = db_operations.load_check_sheet_metadata(timestamp)
            check_results = db_operations.load_check_results(timestamp)
            review_results = db_operations.load_check_results(
                timestamp, check_type="review"
            )
            if check_sheet and check_results:
                # チェックグループIDをセッションに設定
                if check_sheet.get("check_group_id"):
                    st.session_state["check_group_id"] = check_sheet["check_group_id"]

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

    # チェックグループ名を取得
    check_group_name = "未分類"
    if check_group_id:
        try:
            check_group_name = db_operations.get_check_group_name(check_group_id)
        except Exception as e:
            st.error(f"チェックグループ名の取得中にエラーが発生しました: {e}")

    st.title(f"{check_group_name} チェックシート")

    # トップページに戻るボタンを右側に配置
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col4:
        if st.button("🏠 トップページに戻る", type="secondary", use_container_width=True):
            st.switch_page("app.py")

    # ユーザーIDの取得（ログインユーザーのメールアドレスから）
    user_id = st.user.email

    # チェックシートIDの生成（タイムスタンプベース）
    check_sheet_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    if timestamp:  # 既存のチェックシートの場合
        check_sheet_id = timestamp

    # ユーザーのレビュアーIDを取得
    reviewer_id = (
        db_operations.get_user_reviewer_id(user_id, check_group_id)
        if check_group_id
        else None
    )

    voice_check_results = {}
    voice_overall_remarks = ""

    record = voice_utils.WebRTCRecord()

    audio_buffer = record.recording("test")
    if audio_buffer:
        full_text = voice_utils.transcribe_audio_with_google(audio_buffer)
        st.session_state["audio_buffer"] = pydub.AudioSegment.empty()

        if full_text:
            gemini_response = voice_utils.auto_fill_check_sheet(
                st.session_state["check_group_id"], full_text
            )
            voice_check_results = {
                result.check_id: {"checked": result.checked, "remarks": result.remarks}
                for result in gemini_response
                if isinstance(result, voice_utils.CheckResult)
            }
            voice_overall_remarks = [
                result.overall_remarks
                for result in gemini_response
                if isinstance(result, voice_utils.OverallResult)
            ]
            # 既存の結果と新しい結果をマージ
            existing_results = st.session_state.get("results", {})
            
            # st.session_state["results"]がない場合、review_resultsをベースとして使用
            if not existing_results and review_results:
                existing_results = review_results.copy()
            
            merged_results = existing_results.copy()
            
            for check_id, new_result in voice_check_results.items():
                if check_id in merged_results:
                    # 既存の値がある場合：checkedはOR演算、remarksは結合
                    existing_result = merged_results[check_id]
                    merged_results[check_id] = {
                        "checked": existing_result.get("checked", False) or new_result.get("checked", False),
                        "remarks": (existing_result.get("remarks", "") + "\n" + new_result.get("remarks", "")).strip()
                    }
                else:
                    # 新しい値の場合：そのまま設定
                    merged_results[check_id] = new_result
            
            st.session_state["results"] = merged_results
            voice_overall_remarks = (
                voice_overall_remarks[0] if len(voice_overall_remarks) > 0 else ""
            )
            # 結果を保存
            timestamp = db_operations.save_results(
                check_sheet_id,
                st.session_state["results"],
                voice_overall_remarks,
                user_id,
                reviewer_id=reviewer_id,
                check_group_id=check_group_id,
                status="checking",
            )

            # session_stateに保存してページ遷移
            st.session_state["timestamp"] = timestamp
            st.rerun()
        else:
            st.warning("音声認識結果が空でした。音声を録音してください。")

    # チェックシートデータの読み込み
    if check_group_id:
        if check_results:
            # 既存のチェックシートを編集する場合：チェック結果に含まれるcheck_idのみを対象
            checksheet_data = db_operations.load_checksheet_by_check_sheet_id(
                check_sheet_id=timestamp, user_id=user_id
            )
        else:
            # 新規作成の場合：チェックグループ全体のデータを取得
            checksheet_data = db_operations.load_check_items_by_group(check_group_id=check_group_id, user_id=user_id)
    else:
        st.error("チェックグループが選択されていません。")
        st.stop()

    # フォームの作成
    # カテゴリーごとにセクションを作成
    for category, items in checksheet_data.items():
        st.subheader(f"{category}", divider=True)

        # チェック項目をリスト形式で表示
        for item in items:
            col1, col2 = st.columns([1, 9])

            with col1:
                # チェックボックス
                key = item["check_id"]
                # 既存の結果があれば、その値を初期値として設定
                initial_checked = (
                    check_results.get(key)["checked"] if check_results else False
                )

                # geminiの回答があれば、その値を初期値として設定
                initial_checked = (
                    voice_check_results.get(key).checked
                    if voice_check_results.get(key)
                    else initial_checked
                )

                checked = st.checkbox(
                    "チェック",
                    key=key,
                    label_visibility="collapsed",
                    value=initial_checked,
                )
                if voice_check_results.get(key):
                    st.session_state["results"][key] = {
                        "checked": voice_check_results.get(key).checked
                    }
                else:
                    st.session_state["results"][key] = {"checked": checked}

            with col2:
                # 項目名と説明を表示
                st.markdown(f"#### {item['name']}")
                st.markdown(f"*{item['description']}*")

                # 注意事項がある場合は表示
                if item.get("note"):
                    st.warning(item["note"])

                # コメント入力
                comment_key = f"comment_{item['check_id']}"

                # 既存の結果があれば、その値を初期値として設定
                initial_comment = (
                    check_results.get(key)["remarks"] if check_results else ""
                )

                # geminiの回答があれば、その値を初期値として設定
                initial_comment = (
                    voice_check_results.get(key).remarks
                    if voice_check_results.get(key)
                    else initial_comment
                )

                comment = st.text_area(
                    "コメント", key=comment_key, height=68, value=initial_comment
                )

                if voice_check_results.get(key):
                    st.session_state["results"][key]["remarks"] = (
                        voice_check_results.get(key).remarks
                    )
                else:
                    st.session_state["results"][key]["remarks"] = comment

                # レビュー結果がある場合は表示
                if review_results and key in review_results:
                    review_result = review_results[key]
                    review_status = "✅" if review_result["checked"] else "❌"
                    review_comment = review_result.get("remarks", "")
                    st.markdown(f"**レビュー結果:** {review_status}")
                    if review_comment:
                        st.markdown(f"**レビューコメント:** {review_comment}")

    # その他備考欄
    st.subheader("その他備考", divider=True)
    # 既存の結果があれば、その値を初期値として設定
    initial_remarks = check_sheet.get("check_remarks") if check_sheet else ""

    # geminiの回答があれば、その値を初期値として設定
    initial_remarks = (
        voice_overall_remarks if voice_overall_remarks != "" else initial_remarks
    )

    remarks = st.text_area(
        "追加のコメントや特記事項があればご記入ください",
        key="remarks",
        height=100,
        value=initial_remarks,
        placeholder="例：\n・次回レビュー時の確認事項\n・特に注意が必要な点\n・改善提案など",
    )

    # レビュー備考がある場合は表示
    if review_results and check_sheet and check_sheet.get("review_remarks"):
        st.markdown("### レビュー備考")
        st.markdown(check_sheet["review_remarks"])

    # 送信ボタン
    submitted = st.button("チェック結果を送信", type="primary")

    if submitted:
        # 結果を保存
        timestamp = db_operations.save_results(
            check_sheet_id,
            st.session_state["results"],
            remarks,
            user_id,
            reviewer_id=reviewer_id,
            check_group_id=check_group_id,
        )

        # session_stateに保存してページ遷移
        st.session_state["timestamp"] = timestamp
        st.switch_page("pages/result.py")


if __name__ == "__main__":
    main()
