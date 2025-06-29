from datetime import datetime
from typing import Dict, Any, List, Union, Optional
import os

from google import genai
from google.cloud import documentai_v1 as documentai
from pydantic import BaseModel

import utils.db_operations as db_operations

# レスポンススキーマの定義
class CheckResult(BaseModel):
    check_id: str
    checked: bool
    remarks: Optional[str]


class OverallResult(BaseModel):
    overall_remarks: str


def process_pdf(
    pdf_content: bytes, project_id: str, location: str, processor_id: str
) -> Dict[str, Any]:
    """
    PDFファイルをGoogle Cloud Document AIを使用して解析し、テキストを抽出します。

    Args:
        pdf_content (bytes): PDFファイルのバイナリデータ
        project_id (str): Google Cloud プロジェクトID
        location (str): Document AIのロケーション（例：'us' または 'asia1'）
        processor_id (str): Document AIプロセッサーID

    Returns:
        Dict[str, Any]: 解析結果を含む辞書

    Raises:
        ValueError: 必要なパラメータが指定されていない場合
    """
    # パラメータのチェック
    if not all([project_id, processor_id]):
        raise ValueError(
            "必要なパラメータが指定されていません。"
            "project_id, processor_idを指定してください。"
        )

    # Document AIクライアントの初期化
    client = documentai.DocumentProcessorServiceClient()

    # プロセッサーの完全なリソース名を構築
    name = f"projects/{project_id}/locations/{location}/processors/{processor_id}"
    name = client.processor_path(project_id, location, processor_id)

    # ドキュメントの設定
    document = documentai.RawDocument(content=pdf_content, mime_type="application/pdf")

    # 処理リクエストの作成
    request = documentai.ProcessRequest(name=name, raw_document=document)

    try:
        # ドキュメントの処理
        result = client.process_document(request=request)
        document = result.document

        # 結果の整形
        result_dict = {"text": "", "pages": [], "entities": [], "blocks": []}

        # document_layoutの情報を抽出
        if hasattr(document, "document_layout") and document.document_layout:
            # テキストの抽出
            all_text = []
            for block in document.document_layout.blocks:
                if hasattr(block, "text_block") and block.text_block.text:
                    all_text.append(block.text_block.text)
            result_dict["text"] = "\n".join(all_text)

            # ブロック情報の抽出
            for block in document.document_layout.blocks:
                block_info = {
                    "block_id": block.block_id,
                    "text": (
                        block.text_block.text if hasattr(block, "text_block") else ""
                    ),
                    "type": (
                        block.text_block.type_ if hasattr(block, "text_block") else ""
                    ),
                    "page_span": (
                        {
                            "page_start": block.page_span.page_start,
                            "page_end": block.page_span.page_end,
                        }
                        if hasattr(block, "page_span")
                        else None
                    ),
                }
                result_dict["blocks"].append(block_info)

        # ページ情報の抽出
        for page in document.pages:
            page_info = {
                "page_number": page.page_number,
                "text": page.text_anchor.content if page.text_anchor else "",
                "blocks": [],
            }

            # ブロック情報の抽出
            for block in page.blocks:
                block_info = {
                    "text": block.text_anchor.content if block.text_anchor else "",
                    "confidence": block.layout.confidence,
                }
                page_info["blocks"].append(block_info)

            result_dict["pages"].append(page_info)

        # エンティティ情報の抽出
        for entity in document.entities:
            entity_info = {
                "type": entity.type_,
                "mention_text": entity.mention_text,
                "confidence": entity.confidence,
            }
            result_dict["entities"].append(entity_info)

        return result_dict

    except Exception as e:
        raise Exception(f"Document AIの処理中にエラーが発生しました: {str(e)}")


def extract_text_from_pdf(
    pdf_content: bytes, project_id: str, location: str, processor_id: str
) -> str:
    """
    PDFファイルからテキストのみを抽出する簡易関数

    Args:
        pdf_content (bytes): PDFファイルのバイナリデータ
        project_id (str): Google Cloud プロジェクトID
        location (str): Document AIのロケーション
        processor_id (str): Document AIプロセッサーID

    Returns:
        str: 抽出されたテキスト
    """
    result = process_pdf(pdf_content, project_id, location, processor_id)
    return result["text"]


def auto_check_document(check_group_id: int, document: str) -> Dict[str, Any]:
    """
    ドキュメントを自動チェックし、チェック結果を返します。

    Args:
        check_group_id (int): チェックグループID
        document (str): チェック対象のドキュメントテキスト

    Returns:
        Dict[str, Any]: チェック結果を含む辞書
    """

    # チェックリストの取得（指定されたグループの項目を取得）
    checksheet_data = db_operations.load_checksheet(check_group_id=check_group_id)

    # チェック項目の情報を収集
    check_items = []
    for category, items in checksheet_data.items():
        for item in items:
            check_items.append(
                {
                    "check_id": item["check_id"],
                    "name": item["name"],
                    "description": item["description"],
                    "level": item["level"],
                }
            )

    # Gemini APIの呼び出し
    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location="us-central1",
    )

    # プロンプトの作成
    prompt = f"""
    以下のドキュメントを、チェックリストに基づいて評価してください。
    各チェック項目について、該当するかどうか（checked）を判定してください。
    そもそも対象のドキュメントについて、チェック項目の対象とならないようなケースの場合は、checkedはtrueとなります。
    例えば、専門用語について説明されているか、というチェック項目について、そもそも専門用語を利用していなければ、checkedはtrueとなります。

    チェック項目に対して、当てはまらない場合は、その理由や改善点（remarks）を記載してください。
    特に理由や改善点がない場合は、remarksを空の文字列にしてください。
    ただし、特記事項や素晴らしい点などあれば記載ください。

    また、全体としての評価や改善点（OverallResult）ももしあれば記載してください。
    なくても問題ありません。その場合は、overall_remarksを空の文字列にしてください。
    全体としての評価や改善点は、全体的にどのような点が良いか、または悪いかを記載してください。

    # ドキュメント:
    {document}

    # チェックリスト:
    {check_items}
    """

    # Gemini APIの呼び出し
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": list[Union[CheckResult, OverallResult]],
        },
    )

    # レスポンスの解析
    try:
        return response.parsed
    except Exception as e:
        raise Exception(
            f"Gemini APIのレスポンスの解析中にエラーが発生しました: {str(e)}"
        )


def process_and_save_pdf_results(
    pdf_content: bytes,
    project_id: str,
    location: str,
    processor_id: str,
    user_id: str,
    check_group_id: int,
) -> str:
    """
    PDFファイルを処理し、チェック結果を保存します。

    Args:
        pdf_content (bytes): PDFファイルのバイナリデータ
        project_id (str): Google Cloud プロジェクトID
        location (str): Document AIのロケーション
        processor_id (str): Document AIプロセッサーID
        user_id (str): 実行したユーザーID
        check_group_id (int): チェックグループID

    Returns:
        str: 保存されたチェックシートID

    Raises:
        Exception: 処理中にエラーが発生した場合
    """

    # Document AIでテキストを抽出
    extracted_text = extract_text_from_pdf(
        pdf_content, project_id=project_id, location=location, processor_id=processor_id
    )

    # 自動チェックの実行
    check_result = auto_check_document(
        check_group_id=check_group_id, document=extracted_text
    )

    # チェック結果を辞書形式に変換
    results_dict = {}
    overall_remarks = ""

    for result in check_result:
        if isinstance(result, OverallResult):
            overall_remarks += result.overall_remarks + "\n"
        else:
            results_dict[result.check_id] = {
                "checked": result.checked,
                "remarks": result.remarks,
            }

    # データベースに保存
    current_time = datetime.now()
    check_sheet_id = current_time.strftime("%Y%m%d_%H%M%S")  # YYYYMMDD_HHMMSS形式

    check_sheet_id = db_operations.save_results(
        check_sheet_id=check_sheet_id,
        results=results_dict,
        check_remarks=overall_remarks,
        user_id="auto_check",  # 自動チェックの場合は固定のユーザーIDを使用
        reviewer_id=user_id,  # 実行したユーザーIDをレビュアーとして設定
        check_group_id=check_group_id,
    )

    return check_sheet_id
