import asyncio
import json
import os
from datetime import datetime
from typing import List

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, BackgroundTasks, Request
from pydantic import BaseModel

app = FastAPI(title="WhatsApp Service")

_last_qr_base64: str = ""

EVOLUTION_API_URL = os.environ["EVOLUTION_API_URL"]
EVOLUTION_API_KEY = os.environ["EVOLUTION_API_KEY"]
EVOLUTION_INSTANCE = os.environ["EVOLUTION_INSTANCE"]
WHATSAPP_GROUP_ID = os.environ["WHATSAPP_GROUP_ID"]
REDIS_URL = os.environ["REDIS_URL"]
RANKING_SVC_URL = os.environ["RANKING_SVC_URL"]
POLL_TIMEOUT = int(os.environ.get("POLL_TIMEOUT_SECONDS", 300))

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)

EVOLUTION_HEADERS = {
    "apikey": EVOLUTION_API_KEY,
    "Content-Type": "application/json",
}


class SendPollRequest(BaseModel):
    question_id: int
    question_text: str
    options: List[str]
    correct_index: int


class SendMessageRequest(BaseModel):
    text: str


class WebhookEvent(BaseModel):
    event: str
    instance: str
    data: dict


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/qr", response_class=None)
async def show_qr():
    from fastapi.responses import HTMLResponse
    if not _last_qr_base64:
        return HTMLResponse("<h2>QR code ainda não disponível. Aguarde...</h2><script>setTimeout(()=>location.reload(),3000)</script>")
    return HTMLResponse(f"<img src='{_last_qr_base64}' style='width:300px'><p>Escaneie com o WhatsApp</p><script>setTimeout(()=>location.reload(),10000)</script>")


@app.post("/send-poll")
async def send_poll(req: SendPollRequest, background_tasks: BackgroundTasks):
    async with httpx.AsyncClient() as client:
        payload = {
            "number": WHATSAPP_GROUP_ID,
            "name": req.question_text,
            "values": req.options,
            "selectableCount": 1,
        }
        response = await client.post(
            f"{EVOLUTION_API_URL}/message/sendPoll/{EVOLUTION_INSTANCE}",
            headers=EVOLUTION_HEADERS,
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()

    poll_id = result.get("key", {}).get("id", "")

    poll_data = {
        "question_id": req.question_id,
        "question_text": req.question_text,
        "options": json.dumps(req.options),
        "correct_index": req.correct_index,
        "sent_at": datetime.now().isoformat(),
    }
    await redis_client.hset(f"poll:{poll_id}", mapping=poll_data)
    await redis_client.expire(f"poll:{poll_id}", POLL_TIMEOUT + 120)

    background_tasks.add_task(close_poll_after_timeout, poll_id, POLL_TIMEOUT)

    return {"poll_id": poll_id}


@app.post("/send-message")
async def send_message_endpoint(req: SendMessageRequest):
    await _send_message(req.text)
    return {"sent": True}


@app.post("/webhook")
async def receive_webhook(request: Request):
    global _last_qr_base64
    body = await request.json()
    event_name = body.get("event", "")
    data = body.get("data", {})

    print(f"WEBHOOK event={event_name} data={data}", flush=True)

    if "qrcode" in event_name.lower() or "qr" in event_name.lower():
        qr = data.get("qrcode", {})
        b64 = qr.get("base64", "") if isinstance(qr, dict) else ""
        if b64:
            _last_qr_base64 = b64
            print("QR CODE RECEBIDO!", flush=True)
        return {"qr_received": True}

    if event_name != "messages.update":
        return {"ignored": True}

    poll_id = data.get("key", {}).get("id", "")
    poll_updates = data.get("pollUpdates", [])

    if not poll_id or not poll_updates:
        return {"ignored": True}

    poll_data = await redis_client.hgetall(f"poll:{poll_id}")
    if not poll_data:
        return {"ignored": True}

    options = json.loads(poll_data["options"])
    correct_index = int(poll_data["correct_index"])
    sent_at = datetime.fromisoformat(poll_data["sent_at"])

    for update in poll_updates:
        voter = update.get("voter", "")
        selected = update.get("votes", [])

        if not voter or not selected:
            continue

        response_key = f"response:{poll_id}:{voter}"
        if await redis_client.exists(response_key):
            continue

        selected_index = options.index(selected[0]) if selected[0] in options else -1
        elapsed = (datetime.now() - sent_at).total_seconds()

        await redis_client.hset(
            response_key,
            mapping={
                "voter": voter,
                "selected_index": selected_index,
                "is_correct": str(selected_index == correct_index),
                "elapsed_seconds": elapsed,
                "answered_at": datetime.now().isoformat(),
            },
        )
        await redis_client.expire(response_key, POLL_TIMEOUT + 120)
        await redis_client.rpush(f"responses:{poll_id}", voter)

    return {"processed": True}


async def close_poll_after_timeout(poll_id: str, timeout: int):
    await asyncio.sleep(timeout)

    poll_data = await redis_client.hgetall(f"poll:{poll_id}")
    if not poll_data:
        return

    voters = await redis_client.lrange(f"responses:{poll_id}", 0, -1)
    responses = []
    for voter in voters:
        resp = await redis_client.hgetall(f"response:{poll_id}:{voter}")
        if resp:
            responses.append(
                {
                    "phone": resp["voter"],
                    "selected_index": int(resp["selected_index"]),
                    "is_correct": resp["is_correct"] == "True",
                    "elapsed_seconds": float(resp["elapsed_seconds"]),
                    "answered_at": resp["answered_at"],
                }
            )

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{RANKING_SVC_URL}/compute",
            json={
                "poll_id": poll_id,
                "question_id": int(poll_data["question_id"]),
                "responses": responses,
            },
            timeout=30,
        )


async def _send_message(text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}",
            headers=EVOLUTION_HEADERS,
            json={"number": WHATSAPP_GROUP_ID, "text": text},
            timeout=30,
        )
