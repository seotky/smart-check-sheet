import traceback

import streamlit as st

import utils.db_operations as db_operations

def main():
    st.set_page_config(layout="wide")
    
    # ログイン状態の確認
    if not st.user.is_logged_in:
        if st.button("Googleアカウントでログイン", icon=":material/login:"):
            st.login()
        st.stop()
    
    st.title('ユーザー管理')
    
    # トップページに戻るボタンを右側に配置
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    with col4:
        if st.button("🏠 トップページに戻る", type="secondary", use_container_width=True):
            st.switch_page("app.py")
    
    # ユーザー情報の表示
    st.info(f"ログインユーザー: {st.user.name} ({st.user.email})")
    
    st.header("ユーザーチェックグループ追加")
    
    try:
        # ユーザー一覧とチェックグループ一覧を取得
        users = db_operations.get_all_users()
        check_groups = db_operations.get_all_check_groups()
        
        if not users:
            st.warning("ユーザーが登録されていません。")
            return
            
        if not check_groups:
            st.warning("チェックグループが登録されていません。")
            return
        
        with st.form("add_user_check_group_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                # ユーザー選択（プルダウン）
                user_options = {f"{user['user_name']} ({user['user_id']})": user['user_id'] for user in users}
                selected_user_display = st.selectbox("ユーザー", list(user_options.keys()))
                user_id = user_options[selected_user_display] if selected_user_display else None
                
                # チェックグループ選択（プルダウン）
                group_options = {group['name']: group['id'] for group in check_groups}
                selected_group_name = st.selectbox("チェックグループ", list(group_options.keys()))
                check_group_id = group_options[selected_group_name] if selected_group_name else None
            
            with col2:
                # レビュアー選択（プルダウン、空欄可）
                reviewer_options = {"なし": None}
                reviewer_options.update({f"{user['user_name']} ({user['user_id']})": user['user_id'] for user in users})
                selected_reviewer_display = st.selectbox("レビュアー", list(reviewer_options.keys()))
                reviewer_id = reviewer_options[selected_reviewer_display] if selected_reviewer_display else None
                
                role = st.selectbox("ロール", ["member", "reviewer", "admin"], index=0)
            
            submitted = st.form_submit_button("ユーザーチェックグループを追加", type="primary")
            
            if submitted:
                if user_id and check_group_id:
                    try:
                        db_operations.insert_user_check_group(
                            user_id=user_id,
                            check_group_id=check_group_id,
                            reviewer_id=reviewer_id,
                            role=role
                        )
                        st.success(f"ユーザー {user_id} をチェックグループ {selected_group_name} に追加しました（ロール: {role}）。")
                    except Exception as e:
                        st.error(f"ユーザーチェックグループの追加中にエラーが発生しました: {str(e)}")
                        st.code(traceback.format_exc())
                else:
                    st.error("ユーザーとチェックグループを選択してください。")
                    
    except Exception as e:
        st.error(f"データの取得中にエラーが発生しました: {str(e)}")
        st.code(traceback.format_exc())
    
    # 現在のユーザーとチェックグループの一覧表示
    st.header("現在のユーザーとチェックグループ一覧")
    
    try:
        # ユーザーのチェックグループ一覧を取得
        user_id = st.user.email
        user_groups = db_operations.get_user_check_groups(user_id)
        
        if user_groups:
            st.subheader("あなたのチェックグループ")
            for group in user_groups:
                st.write(f"- **{group['group_name']}** (ロール: {group['role']})")
        else:
            st.info("あなたに割り当てられたチェックグループがありません。")
            
    except Exception as e:
        st.error(f"チェックグループの取得中にエラーが発生しました: {str(e)}")
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main() 