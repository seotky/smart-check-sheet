import base64
import logging
import os
import queue
from typing import Dict, Any, List, Union, Optional

import numpy as np
import pydub
import requests
import streamlit as st
from google import genai
from pydantic import BaseModel
from scipy import signal
from streamlit_webrtc import webrtc_streamer, WebRtcMode

import utils.db_operations as db_operations

LANGUAGE = "ja-JP"  # 音声認識に使用する言語

logger = logging.getLogger(__name__)


# Gemini APIのレスポンススキーマの定義
class VoiceResponse(BaseModel):
    response: str


# レスポンススキーマの定義
class CheckResult(BaseModel):
    check_id: str
    checked: bool
    remarks: Optional[str]


class OverallResult(BaseModel):
    overall_remarks: str


class WebRTCRecord:
    def __init__(self):
        self.webrtc_ctx = webrtc_streamer(
            key="sendonly-audio",
            mode=WebRtcMode.SENDONLY,
            audio_receiver_size=256,
            rtc_configuration={
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            },
            media_stream_constraints={
                "audio": True,
            }
        )

        if "audio_buffer" not in st.session_state:
            st.session_state["audio_buffer"] = pydub.AudioSegment.empty()
        
        # フローティングボタンのCSS
        st.markdown(
            """
            <style>
            .st-key-sendonly-audio-frontend-6-r--0Gea7e-2E--y-i-_UzwU--RJP-z{
                position: fixed;
                bottom: 40px;
                z-index: 999;
                border-radius: 0;
                border: 2px solid #808080;
                background-color: #ffffff;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
                transition: all 0.3s ease;
                padding: 0 8px 8px 8px;
            }
            
            .st-key-sendonly-audio-frontend-6-r--0Gea7e-2E--y-i-_UzwU--RJP-z:hover {
                transform: scale(1.05);
                box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
                border-color: #666666;
            }
            </style>
        """,
            unsafe_allow_html=True,
        )

    def recording(self, question):
        status_box = st.empty()

        while True:
            if self.webrtc_ctx.audio_receiver:
                try:
                    audio_frames = self.webrtc_ctx.audio_receiver.get_frames(timeout=1)
                except queue.Empty:
                    status_box.warning("No frame arrived.")
                    continue

                status_box.info("Now Recording...")

                sound_chunk = pydub.AudioSegment.empty()
                for audio_frame in audio_frames:
                    sound = pydub.AudioSegment(
                        data=audio_frame.to_ndarray().tobytes(),
                        sample_width=audio_frame.format.bytes,
                        frame_rate=audio_frame.sample_rate,
                        channels=len(audio_frame.layout.channels),
                    )
                    sound_chunk += sound

                if len(sound_chunk) > 0:
                    st.session_state["audio_buffer"] += sound_chunk
            else:
                break

        audio_buffer = st.session_state["audio_buffer"]
        return audio_buffer


# Google Speech-to-Text Web APIを使用した音声認識
def transcribe_audio_with_google_web_api(audio_segment):
    """
    Google Speech-to-Text Web APIを使用して音声を文字起こしします。

    Args:
        audio_segment: pydubのAudioSegmentオブジェクト

    Returns:
        str: 認識されたテキスト
    """
    try:
        # 音声データを適切な形式に変換
        samples = audio_segment.get_array_of_samples()

        # 音声データの形式を確認
        if audio_segment.sample_width == 1:
            # 8bit unsigned
            audio_array = np.array(samples, dtype=np.uint8)
            audio_array = (audio_array.astype(np.float32) - 128) / 128.0
        elif audio_segment.sample_width == 2:
            # 16bit signed
            audio_array = np.array(samples, dtype=np.int16)
            audio_array = audio_array.astype(np.float32) / 32768.0
        elif audio_segment.sample_width == 4:
            # 32bit signed
            audio_array = np.array(samples, dtype=np.int32)
            audio_array = audio_array.astype(np.float32) / 2147483648.0
        else:
            # その他の場合は16bitとして処理
            audio_array = np.array(samples, dtype=np.float32)
            if audio_array.max() > 1.0 or audio_array.min() < -1.0:
                audio_array = audio_array / 32768.0

        # Google Speech-to-Text APIは16bit PCMを要求
        # float32から16bit PCMに変換
        audio_array = (audio_array * 32767).astype(np.int16)

        # モノラルに変換（ステレオの場合は左チャンネルのみ使用）
        if audio_segment.channels == 2:
            # ステレオの場合、左右のチャンネルを平均化
            audio_array = audio_array.reshape(-1, 2).mean(axis=1).astype(np.int16)

        # サンプリングレートを確認（Google Speech-to-Text APIは8kHz, 16kHz, 32kHz, 48kHzをサポート）
        sample_rate = audio_segment.frame_rate
        if sample_rate not in [8000, 16000, 32000, 48000]:
            # サポートされていないサンプリングレートの場合は16kHzに変換
            target_rate = 16000
            audio_array = signal.resample(
                audio_array, int(len(audio_array) * target_rate / sample_rate)
            )
            audio_array = (audio_array * 32767).astype(np.int16)
            sample_rate = target_rate

        # デバッグ情報をログに出力
        logger.info(
            f"音声データ情報: 長さ={len(audio_array)}, サンプリングレート={sample_rate}, チャンネル数={audio_segment.channels}"
        )
        logger.info(f"音声データ範囲: min={audio_array.min()}, max={audio_array.max()}")

        # 音声データをbase64エンコード
        audio_bytes = audio_array.tobytes()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # Google Cloud APIキーを取得
        api_key = os.getenv("GOOGLE_CLOUD_API_KEY")
        if not api_key:
            logger.error("GOOGLE_CLOUD_API_KEY環境変数が設定されていません")
            st.error("Google Cloud APIキーが設定されていません")
            return ""

        # Web APIのエンドポイント
        url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"

        # リクエストボディの作成
        request_body = {
            "config": {
                "encoding": "LINEAR16",
                "sampleRateHertz": sample_rate,
                "languageCode": LANGUAGE,
                "enableAutomaticPunctuation": True,
                "model": "default",
            },
            "audio": {"content": audio_base64},
        }

        # APIリクエストの送信
        headers = {"Content-Type": "application/json"}

        response = requests.post(url, headers=headers, json=request_body)

        if response.status_code == 200:
            result = response.json()

            # 認識結果を取得
            if "results" in result and result["results"]:
                full_text = ""
                for res in result["results"]:
                    if "alternatives" in res and res["alternatives"]:
                        full_text += res["alternatives"][0]["transcript"] + " "
                logger.info(f"認識結果: {full_text.strip()}")
                return full_text.strip()
            else:
                logger.warning("音声認識結果が空でした")
                return ""
        else:
            logger.error(
                f"Google Speech-to-Text Web API エラー: {response.status_code} - {response.text}"
            )
            st.error(f"Google Speech-to-Text Web API エラー: {response.status_code}")
            return ""

    except Exception as e:
        logger.error(f"Google Speech-to-Text Web API エラー: {e}")
        st.error(f"Google Speech-to-Text Web API エラー: {e}")
        return ""


# デフォルトの音声認識関数（Web APIを使用）
def transcribe_audio_with_google(audio_segment):
    """
    デフォルトの音声認識関数（Web APIを使用）

    Args:
        audio_segment: pydubのAudioSegmentオブジェクト

    Returns:
        str: 認識されたテキスト
    """
    return transcribe_audio_with_google_web_api(audio_segment)


def auto_fill_check_sheet(check_group_id: int, comment: str) -> Dict[str, Any]:
    """
    ドキュメントを自動チェックし、チェック結果を返します。

    Args:
        check_group_id (int): チェックグループID
        comment (str): 音声認識結果

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
    以下は人間がチェックシートをチェックする際の音声認識の結果です。
    この音声認識の結果に基づいてチェックリストを埋めてください。
    あなたは話者になりきって、チェックリストを埋めてください。

    各チェック項目について、該当するかどうか（checked）を判定してください。
    音声が聞き取れない場合や、音声認識の結果がない場合、判断が難しい場合、checkedはfalseとなります。

    チェック項目に対して、チェック結果の理由や改善点、褒めるポイントがあれば（remarks）を記載してください。
    無ければ、remarksを空の文字列にしてください。
    特に理由や改善点がない場合、聞き取れない場合、判断が難しい場合は、remarksを空の文字列にしてください。

    また、全体としての評価や改善点（OverallResult）がもしあれば記載してください。
    なくても問題ありません。その場合は、overall_remarksを空の文字列にしてください。
    全体としての評価や改善点は、全体的にどのような点が良いか、または悪いかを記載してください。

    # 音声認識の結果:
    {comment}

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


# Gemini APIを使用した音声内容の分析
def analyze_voice_content_with_gemini(transcribed_text: str) -> str:
    """
    音声認識結果をGemini APIを使用して質問に回答します。

    Args:
        transcribed_text (str): 音声認識で得られたテキスト

    Returns:
        str: Geminiからの回答
    """
    try:
        # Gemini APIクライアントの初期化
        client = genai.Client()

        # シンプルなプロンプト
        prompt = f"""
        以下の質問や発言に対して、適切に回答してください。

        {transcribed_text}
        """

        # Gemini APIの呼び出し
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": VoiceResponse,
            },
        )

        # レスポンスの解析
        try:
            result = response.parsed
            logger.info(f"Gemini回答: {result.response}")
            return result.response
        except Exception as e:
            logger.error(
                f"Gemini APIのレスポンスの解析中にエラーが発生しました: {str(e)}"
            )
            return "回答の解析中にエラーが発生しました"

    except Exception as e:
        logger.error(f"Gemini API エラー: {e}")
        return "Gemini APIの呼び出し中にエラーが発生しました"
