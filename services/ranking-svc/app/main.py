import os
from datetime import datetime
from typing import List

import httpx
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy import Column, Float, Integer, String, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

DATABASE_URL = os.environ["DATABASE_URL"]
WHATSAPP_SVC_URL = os.environ["WHATSAPP_SVC_URL"]

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class RankingEntry(Base):
    __tablename__ = "ranking"
    id = Column(Integer, primary_key=True)
    participant_phone = Column(String(50), unique=True, nullable=False)
    participant_name = Column(String(255))
    total_correct = Column(Integer, default=0)
    total_responses = Column(Integer, default=0)
    avg_response_time = Column(Float, default=0)
    score = Column(Float, default=0)
    updated_at = Column(DateTime, default=datetime.now)


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Ranking Service")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ResponseItem(BaseModel):
    phone: str
    selected_index: int
    is_correct: bool
    elapsed_seconds: float
    answered_at: str


class ComputeRequest(BaseModel):
    poll_id: str
    question_id: int
    responses: List[ResponseItem]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/compute")
async def compute_ranking(req: ComputeRequest, db: Session = Depends(get_db)):
    for resp in req.responses:
        entry = db.query(RankingEntry).filter_by(participant_phone=resp.phone).first()
        if not entry:
            entry = RankingEntry(participant_phone=resp.phone, total_correct=0, total_responses=0, avg_response_time=0)
            db.add(entry)

        entry.total_responses += 1
        if resp.is_correct:
            entry.total_correct += 1

        n = entry.total_responses
        entry.avg_response_time = ((entry.avg_response_time * (n - 1)) + resp.elapsed_seconds) / n
        # Acertos valem 100pts, velocidade é desempate (penalidade mínima por segundo)
        entry.score = (entry.total_correct * 100) - (entry.avg_response_time * 0.1)
        entry.updated_at = datetime.now()

    db.commit()

    top = db.query(RankingEntry).order_by(RankingEntry.score.desc()).limit(10).all()

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 *Ranking Geral*\n"]
    for i, r in enumerate(top, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = r.participant_name or r.participant_phone
        lines.append(f"{prefix} {name}: {r.total_correct} acertos | {r.avg_response_time:.1f}s médio")

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{WHATSAPP_SVC_URL}/send-message",
            json={"text": "\n".join(lines)},
            timeout=30,
        )

    return {"updated": len(req.responses)}


@app.get("/ranking")
def get_ranking(db: Session = Depends(get_db)):
    entries = db.query(RankingEntry).order_by(RankingEntry.score.desc()).all()
    return [
        {
            "position": i,
            "phone": e.participant_phone,
            "name": e.participant_name,
            "correct": e.total_correct,
            "total": e.total_responses,
            "avg_time_seconds": round(e.avg_response_time, 2),
            "score": round(e.score, 2),
        }
        for i, e in enumerate(entries, 1)
    ]
