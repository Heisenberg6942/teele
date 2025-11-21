import os
import json
import traceback
from telethon import TelegramClient, events
from telethon.tl.types import (
    Message,
    InputReplyToMessage,
    InputMediaUploadedPhoto,
    InputMediaUploadedDocument,
    DocumentAttributeFilename,
    DocumentAttributeVideo
)
from telethon.tl.functions.messages import (
    SendMessageRequest,
    SendMediaRequest
)

# -------------------------
# CONFIG
# -------------------------
API_ID = int(os.getenv("API_ID", "25446764"))
API_HASH = os.getenv("API_HASH", "05f812747ae6b913cac3db7ba0dbcec9")
SESSION_NAME = os.getenv("SESSION_NAME", "session_name")

SOURCE_GROUPS = [
    -1003058619673,
    -1001556054753, #watcher guru
    -1002006131201, #brics news
    -1001685592361, #crypto news
    -1002229136312, #wizard calls
    -1001513104671, #perps calls
    -1001263412188, #autistic news

]

DESTINATION_GROUP = -1002436012210

TOPIC_MAP = {
    -1003058619673: 1,
    -1001263412188: 7049,
    -1002229136312: 6804,
    -1002006131201: 6802,
    -1001556054753: 6803,
    -1001685592361: 6803,
    -1002337482415: 6801,
}

MAP_FILE = "message_map.json"
TMP_DIR = "tmp_media"
os.makedirs(TMP_DIR, exist_ok=True)

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


# -------------------------
# LOAD / SAVE MESSAGE MAP
# -------------------------
def load_map():
    if os.path.exists(MAP_FILE):
        try:
            with open(MAP_FILE, "r") as f:
                raw = json.load(f)
                return {int(k): int(v) for k, v in raw.items()}
        except:
            return {}
    return {}


def save_map(mapping):
    with open(MAP_FILE, "w") as f:
        json.dump({str(k): v for k, v in mapping.items()}, f)


message_map = load_map()


# -------------------------
# RAW TEXT SENDER
# -------------------------
async def safe_send_text(peer, text, reply_struct):
    resp = await client(SendMessageRequest(
        peer=peer,
        message=text or "",
        reply_to=reply_struct
    ))

    for u in resp.updates:
        if hasattr(u, "message") and getattr(u.message, "id", None):
            return u.message.id
        if hasattr(u, "id"):
            return u.id

    return None


# -------------------------
# RAW MEDIA SENDER
# -------------------------
async def safe_send_media(peer, file_path, caption, reply_struct, message):
    """
    Sends media with proper detection:
    - Photos --> InputMediaUploadedPhoto
    - Videos/GIFs/Documents --> InputMediaUploadedDocument
    """

    uploaded = await client.upload_file(file_path)

    # Detect image vs video vs doc
    is_photo = bool(getattr(message.media, "photo", None))
    is_document = bool(getattr(message.media, "document", None))

    # Check if video attributes exist
    is_video = False
    if is_document and hasattr(message.media.document, "attributes"):
        for attr in message.media.document.attributes:
            if isinstance(attr, DocumentAttributeVideo):
                is_video = True
                break

    # PHOTO LOGIC
    if is_photo and not is_video:
        media_to_send = InputMediaUploadedPhoto(file=uploaded)

    # VIDEO / GIF / FILE
    else:
        filename = os.path.basename(file_path)

        media_to_send = InputMediaUploadedDocument(
            file=uploaded,
            mime_type="application/octet-stream",
            attributes=[
                DocumentAttributeFilename(file_name=filename)
            ]
        )

    resp = await client(SendMediaRequest(
        peer=peer,
        media=media_to_send,
        message=caption or "",
        reply_to=reply_struct
    ))

    # Extract message ID
    for u in resp.updates:
        if hasattr(u, "message") and getattr(u.message, "id", None):
            return u.message.id
        if hasattr(u, "id"):
            return u.id

    return None


# -------------------------
# MAIN HANDLER
# -------------------------
@client.on(events.NewMessage(chats=SOURCE_GROUPS))
async def handler(event):
    try:
        message: Message = event.message
        source_chat = event.chat_id

        topic_id = TOPIC_MAP.get(source_chat)
        if topic_id is None:
            print(f"[skip] No topic mapped for source group {source_chat}")
            return

        # Default: reply to topic root
        reply_struct = InputReplyToMessage(
            reply_to_msg_id=topic_id,
            top_msg_id=topic_id
        )

        # Reply chain mapping
        if message.reply_to and message.reply_to.reply_to_msg_id:
            original_id = message.reply_to.reply_to_msg_id
            mapped = message_map.get(original_id)
            if mapped:
                reply_struct = InputReplyToMessage(
                    reply_to_msg_id=mapped,
                    top_msg_id=topic_id
                )

        sent_id = None

        # -------------------------
        # TEXT
        # -------------------------
        if not message.media:
            sent_id = await safe_send_text(
                DESTINATION_GROUP,
                message.text or "",
                reply_struct
            )
            print(f"[text] {message.id} -> {sent_id}")

        # -------------------------
        # MEDIA
        # -------------------------
        else:
            file_path = await message.download_media(file=TMP_DIR)
            if not file_path:
                print("Failed to download media.")
                return

            sent_id = await safe_send_media(
                DESTINATION_GROUP,
                file_path,
                message.text,
                reply_struct,
                message
            )

            print(f"[media] {message.id} -> {sent_id}  ({file_path})")

            # cleanup
            if os.path.exists(file_path):
                os.remove(file_path)

        # Save mapping
        if sent_id:
            message_map[message.id] = sent_id
            save_map(message_map)

    except Exception as e:
        print("ERROR in handler:")
        traceback.print_exc()


# -------------------------
# RUN BOT
# -------------------------
if __name__ == "__main__":
    print("🚀 Forwarder running with full media support + topic routing")
    with client:
        client.run_until_disconnected()
