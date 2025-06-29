import streamlit as st
import pandas as pd

import utils.db_operations as db_operations


def main():
    st.set_page_config(layout="wide")
    # ログイン状態の確認
    if not st.user.is_logged_in:
        if st.button("Googleアカウントでログイン", icon=":material/login:"):
            st.login()
        st.stop()

    st.title("チェックシート結果一覧")

    # トップページに戻るボタンを右側に配置
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col4:
        if st.button("🏠 トップページに戻る", type="secondary", use_container_width=True):
            st.switch_page("app.py")

    # ログアウトボタン
    _, _, _, col3 = st.columns([1, 1, 1, 1])
    if col3.button(
        "ログアウトする",
        icon=":material/logout:",
        use_container_width=True,
        type="secondary",
    ):
        st.logout()  # ログアウト処理

    try:
        # すべてのチェックシート結果を取得
        results_list = db_operations.get_all_results()

        if not results_list:
            st.info("チェックシート結果がまだありません。")
            return

        # DataFrameに変換して表示
        df = pd.DataFrame(results_list)

        # リンク用のカラムを追加
        df["リンク"] = df["ID"].apply(lambda x: f"../result?id={x}")

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
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")


if __name__ == "__main__":
    main()
