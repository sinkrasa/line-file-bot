import os
import io
import requests
import tempfile
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent, ImageMessageContent, VideoMessageContent,
    AudioMessageContent, FileMessageContent
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import json
import mimetypes
from datetime import datetime

app = Flask(__name__)

# === LINE Config ===
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === Google Drive Config ===
GDRIVE_FOLDER_ID = os.environ.get("GDRIVE_FOLDER_ID", "")  # optional: specific folder
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

def get_gdrive_service():
    """Build Google Drive service from credentials JSON string."""
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return build("drive", "v3", credentials=creds)

def upload_to_gdrive(file_bytes: bytes, filename: str, mime_type: str) -> str:
    """Upload file to Google Drive and return shareable link."""
    service = get_gdrive_service()
    
    file_metadata = {"name": filename}
    if GDRIVE_FOLDER_ID:
        file_metadata["parents"] = [GDRIVE_FOLDER_ID]

    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime_type,
        resumable=True
    )
    
    uploaded = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, webViewLink"
    ).execute()

    # Make it accessible to anyone with link
    service.permissions().create(
        fileId=uploaded["id"],
        body={"role": "reader", "type": "anyone"}
    ).execute()

    return uploaded.get("webViewLink", "")

def download_line_content(message_id: str) -> bytes:
    """Download content from LINE servers."""
    url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
    headers = {"Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.content

def reply_message(reply_token: str, text: str):
    """Send reply message."""
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )

def get_timestamp_filename(original_name: str) -> str:
    """Add timestamp prefix to filename."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{original_name}"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):
    try:
        content = download_line_content(event.message.id)
        filename = get_timestamp_filename("image.jpg")
        link = upload_to_gdrive(content, filename, "image/jpeg")
        reply_message(event.reply_token, f"✅ บันทึกรูปภาพแล้ว!\n📁 {filename}\n🔗 {link}")
    except Exception as e:
        reply_message(event.reply_token, f"❌ เกิดข้อผิดพลาด: {str(e)}")

@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event):
    try:
        content = download_line_content(event.message.id)
        filename = get_timestamp_filename("video.mp4")
        link = upload_to_gdrive(content, filename, "video/mp4")
        reply_message(event.reply_token, f"✅ บันทึกวิดีโอแล้ว!\n📁 {filename}\n🔗 {link}")
    except Exception as e:
        reply_message(event.reply_token, f"❌ เกิดข้อผิดพลาด: {str(e)}")

@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    try:
        content = download_line_content(event.message.id)
        filename = get_timestamp_filename("audio.m4a")
        link = upload_to_gdrive(content, filename, "audio/mp4")
        reply_message(event.reply_token, f"✅ บันทึกไฟล์เสียงแล้ว!\n📁 {filename}\n🔗 {link}")
    except Exception as e:
        reply_message(event.reply_token, f"❌ เกิดข้อผิดพลาด: {str(e)}")

@handler.add(MessageEvent, message=FileMessageContent)
def handle_file(event):
    try:
        content = download_line_content(event.message.id)
        original_name = event.message.file_name or "file"
        filename = get_timestamp_filename(original_name)
        
        mime_type, _ = mimetypes.guess_type(original_name)
        mime_type = mime_type or "application/octet-stream"
        
        link = upload_to_gdrive(content, filename, mime_type)
        reply_message(event.reply_token, f"✅ บันทึกไฟล์แล้ว!\n📁 {filename}\n🔗 {link}")
    except Exception as e:
        reply_message(event.reply_token, f"❌ เกิดข้อผิดพลาด: {str(e)}")

@app.route("/", methods=["GET"])
def index():
    return "LINE Bot is running! 🤖"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
