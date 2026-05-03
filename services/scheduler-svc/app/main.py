import asyncio
import httpx
import os
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QUESTION_SVC_URL = os.environ["QUESTION_SVC_URL"]
WHATSAPP_SVC_URL = os.environ["WHATSAPP_SVC_URL"]
SCHEDULE_HOUR = int(os.environ.get("SCHEDULE_HOUR", 9))
SCHEDULE_MINUTE = int(os.environ.get("SCHEDULE_MINUTE", 0))


async def send_daily_quiz():
    logger.info("Disparando quiz diário...")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{QUESTION_SVC_URL}/questions/random", timeout=10)
        resp.raise_for_status()
        question = resp.json()

        await client.post(
            f"{WHATSAPP_SVC_URL}/send-poll",
            json={
                "question_id": question["id"],
                "question_text": question["text"],
                "options": question["options"],
                "correct_index": question["correct_index"],
            },
            timeout=30,
        )
    logger.info(f"Quiz enviado: {question['text']}")


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_daily_quiz,
        CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),
        id="daily_quiz",
    )
    scheduler.start()
    logger.info(f"Scheduler iniciado — quiz todo dia às {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
