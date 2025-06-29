from typing import Dict, List, Union
import os

from google import genai
from pydantic import BaseModel

import utils.db_operations as db_operations

class SuggestedNote(BaseModel):
    check_id: int
    note_text: str


def suggest_check_note(review_results: Dict, user_id: str) -> List[SuggestedNote]:
    """
    レビュー結果を分析し、新しいチェック項目を提案する

    Args:
        review_results (Dict): レビュー結果の辞書
        user_id (str): ユーザーID

    Returns:
        List[SuggestedNote]: 提案されたチェック項目のリスト
    """
    # Gemini APIのクライアントを初期化
    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location="us-central1"
    )

    # レビュー結果からcheck_group_idを取得
    check_group_id = None
    if review_results:
        first_check_id = list(review_results.keys())[0]
        check_group_id = db_operations.get_check_group_id_by_check_id(str(first_check_id))

    if not check_group_id:
        raise Exception("チェックグループIDを取得できませんでした")

    # ユーザーの既存の注意事項を取得
    existing_notes = []
    try:
        existing_notes = db_operations.get_user_check_item_notes(user_id, check_group_id)
    except Exception as e:
        print(f"既存の注意事項の取得中にエラーが発生しました: {e}")

    # レビュー結果をテキストに変換
    review_text = ""
    for check_id, result in review_results.items():
        review_text += (
            f"- Check ID: {check_id}: {'OK' if result['checked'] else 'NG'}\n"
        )
        if result.get("remarks"):
            review_text += f"  コメント: {result['remarks']}\n"

    # 既存の注意事項をテキストに変換
    existing_notes_text = ""
    if existing_notes:
        for note in existing_notes:
            # 日付をフォーマット
            created_date = note['created_at'].strftime("%Y-%m-%d %H:%M:%S")
            existing_notes_text += f"- Check ID: {note['check_id']} ({created_date}): {note['note_text']}\n"

    # プロンプトの作成
    prompt = f"""
    あなたはチェックリストのレビュー結果から、レビューイの注意事項を提案するAIです。
    レビューイがチェックリストをもとにチェックをする際に、注意すべき事項を提案し、チェックの効率や品質を向上させることを目的としています。
    以下のレビュー結果と過去の注意事項を分析し、次回以降に注意すべきチェック項目を選定し、次回以降の注意コメントを生成してください。
    注意すべきチェック項目がない場合や、判断が難しい場合は空のリストを返却してください。
    今回のレビュー結果と過去の注意事項を参考に、新しい注意事項を作成してください。
    もしくは、必要に応じて既存の注意事項のアップデートを提案してください。既存の注意事項と同じ内容でも問題ありませんが、その場合でも作成は行なってください。
    注意すべきチェック項目は基本的には0件、または1件、多くても2件程度です。
    
    # レビュー結果:
    {review_text}

    # 過去の注意事項:
    {existing_notes_text}
    
    """
    try:
        # Gemini APIの呼び出し
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": list[SuggestedNote],
            },
        )
    except Exception as e:
        print(f"Gemini APIのリクエスト中にエラーが発生しました: {str(e)}")
        raise Exception(
            f"Gemini APIのリクエスト中にエラーが発生しました: {str(e)}"
        )

    # レスポンスの解析
    try:
        return response.parsed
    except Exception as e:
        raise Exception(
            f"Gemini APIのレスポンスの解析中にエラーが発生しました: {str(e)}"
        )


def add_suggested_note(suggested_items: List[SuggestedNote], user_id: str) -> None:
    """
    提案されたチェック項目の注意事項をデータベースに追加する

    Args:
        suggested_items (List[SuggestedNote]): 追加する注意事項のリスト
        user_id (str): 注意事項を作成したユーザーID
    """
    for suggested_item in suggested_items:
        try:
            # SuggestedNoteオブジェクトからデータを取得
            check_id = suggested_item.check_id
            note_text = suggested_item.note_text

            # check_idが存在するかチェック
            try:
                # check_idの存在確認
                group_id = db_operations.get_check_group_id_by_check_id(str(check_id))
                if group_id is None:
                    print(f"警告: Check ID {check_id} は存在しません。注意事項の追加をスキップします。")
                    continue
            except Exception as e:
                print(f"警告: Check ID {check_id} の確認中にエラーが発生しました: {e}")
                continue

            # データベースに注意事項を追加
            db_operations.add_check_item_note(check_id, user_id, note_text)
            print(f"注意事項が正常に追加されました。Check ID: {check_id}")

        except Exception as e:
            print(f"注意事項の追加中にエラーが発生しました: {e}")
            # エラーを再発生させずに、ログのみ出力
            continue
