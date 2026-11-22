from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import uuid

from pynamer import process

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    sys.exit(
        "TELEGRAM_BOT_TOKEN is not set.\n"
        "Run with:  TELEGRAM_BOT_TOKEN=<token> python telegram_bot.py"
    )

API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

HELP = (
    "PyNamer bot\n\n"
    "Send me a .py file and I will return an obfuscated copy "
    "(same behaviour, renamed symbols).\n"
    "You can also paste Python source directly as a text message.\n\n"
    "Everything runs through the PyNamer library (scope-aware renamer)."
)


def call(method: str, **params):
    data = json.dumps(params).encode("utf-8")
    request = urllib.request.Request(
        f"{API}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def download(file_id: str) -> bytes:
    info = call("getFile", file_id=file_id)
    path = info["result"]["file_path"]
    with urllib.request.urlopen(f"{FILE_API}/{path}", timeout=90) as response:
        return response.read()


def send_message(chat_id: int, text: str) -> None:
    call("sendMessage", chat_id=chat_id, text=text)


def send_document(chat_id: int, filename: str, content: bytes, caption: str) -> None:
    boundary = uuid.uuid4().hex
    body = bytearray()

    def field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        )
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    field("chat_id", str(chat_id))
    field("caption", caption)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="document"; '
            f'filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
    )
    body.extend(content)
    body.extend(f"\r\n--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"{API}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        response.read()


def obfuscated_name(name: str) -> str:
    base = name[:-3] if name.endswith(".py") else name
    return f"{base}.obf.py"


def caption_for(result) -> str:
    stats = result.stats
    return (
        "Obfuscated with PyNamer\n"
        f"symbols: {stats.symbols}  attributes: {stats.attributes}  "
        f"builtins: {stats.builtins}\n"
        f"size: {stats.input_size} -> {stats.output_size} bytes"
    )


def handle_code(chat_id: int, source: str, name: str) -> None:
    result = process(source, filename=name)
    send_document(
        chat_id,
        obfuscated_name(name),
        result.source.encode("utf-8"),
        caption_for(result),
    )


def handle(message: dict) -> None:
    chat_id = message["chat"]["id"]

    if "document" in message:
        document = message["document"]
        name = document.get("file_name") or "module.py"
        raw = download(document["file_id"])
        try:
            source = raw.decode("utf-8")
        except UnicodeDecodeError:
            send_message(chat_id, "Only UTF-8 encoded .py files are supported.")
            return
        try:
            handle_code(chat_id, source, name)
        except Exception as exc:
            send_message(chat_id, f"Could not process {name}:\n{exc}")
        return

    text = message.get("text")
    if not text:
        return

    text = text.strip()
    if text.startswith("/start") or text.startswith("/help"):
        send_message(chat_id, HELP)
        return
    if text.startswith("/"):
        send_message(chat_id, "Unknown command. Send a .py file or paste code.")
        return

    try:
        handle_code(chat_id, text, "snippet.py")
    except Exception as exc:
        send_message(chat_id, f"Could not process that snippet:\n{exc}")


def main() -> None:
    me = call("getMe")["result"]
    print(f"PyNamer bot running as @{me.get('username')} (id={me['id']})", flush=True)

    offset = 0
    while True:
        try:
            updates = call("getUpdates", offset=offset, timeout=50)
        except Exception as exc:
            print(f"poll error: {exc}", flush=True)
            time.sleep(3)
            continue

        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message")
            if not message:
                continue
            try:
                handle(message)
                print(
                    f"handled message from chat {message['chat']['id']}",
                    flush=True,
                )
            except Exception as exc:
                print(f"handler error: {exc}", flush=True)


if __name__ == "__main__":
    main()
