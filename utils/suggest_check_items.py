from typing import Dict, List, Union

from google import genai
from pydantic import BaseModel
import os

import utils.db_operations as db_operations

class SuggestedItem(BaseModel):
    name: str
    description: str
    level: int
    category_id: int


def suggest_check_items(
    review_results: Dict, review_remarks: str, check_group_id: int
) -> Dict[str, any]:
    """
    レビュー結果を分析し、新しいチェック項目を提案する

    Args:
        review_results (Dict): レビュー結果の辞書
        review_remarks (str): レビュー備考
        check_group_id (int): チェックグループID

    Returns:
        Dict[str, Any]: 提案されたチェック項目のリストを含む辞書
    """
    # Gemini APIのクライアントを初期化
    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location="us-central1"
    )

    # カテゴリ情報を取得
    categories = db_operations.get_categories_by_group_id(check_group_id)
    category_info = ""
    for cat in categories:
        category_info += f"- ID: {cat['category_id']}, 名前: {cat['category_name']}\n"

    # レビュー結果をテキストに変換
    review_text = ""
    for check_id, result in review_results.items():
        review_text += f"- 項目 {check_id}: {'OK' if result['checked'] else 'NG'}\n"
        if result.get("remarks"):
            review_text += f"  コメント: {result['remarks']}\n"

    if review_remarks:
        review_text += f"\nレビュー備考:\n{review_remarks}"

    # プロンプトの作成
    prompt = f"""
    あなたはチェックシート生成AIエージェントです。
    既存のチェックシートに対して、新しくチェック項目を追加し、チェックシートを改善、業務の効率を向上することを目的としています。
    以下のレビュー結果を分析し、新しく追加すべきチェック項目があれば提案してください。
    提案は、レビュー結果から見つかった改善点や、より良い設計のために必要な項目を基にしてください。
    新しく追加すべきチェック項目がない場合や、判断が難しい場合は空のリストを返却してください。
    新しく追加すべきチェック項目は基本的には0件、または1件、多くても2件程度です。
    既存のチェック項目と重複するチェック項目は追加しないでください。

    # 利用可能なカテゴリ:
    {category_info}
    
    # レビュー結果:
    {review_text}
    """

    # Gemini APIの呼び出し
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[SuggestedItem],
        },
    )

    # レスポンスの解析
    try:
        print(response.parsed)
        return response.parsed
    except Exception as e:
        raise Exception(
            f"Gemini APIのレスポンスの解析中にエラーが発生しました: {str(e)}"
        )


def add_suggested_items(suggested_items: List[SuggestedItem], group_id: int) -> None:
    """
    提案されたチェック項目をデータベースに追加する

    Args:
        suggested_items (List[SuggestedItem]): 追加するチェック項目のリスト
        group_id (int): チェックグループID
    """
    # SuggestedItemのリストをdictのリストに変換
    items_dict = [item.model_dump() for item in suggested_items]

    for item in items_dict:
        try:
            db_operations.add_check_item(item, group_id)
        except Exception as e:
            print(f"チェック項目の追加中にエラーが発生しました: {e}")
            continue
