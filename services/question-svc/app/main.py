from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional

from .database import Question, Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Question Service")


class QuestionCreate(BaseModel):
    text: str
    options: List[str]
    correct_index: int
    category: Optional[str] = None


class QuestionOut(BaseModel):
    id: int
    text: str
    options: List[str]
    correct_index: int
    category: Optional[str]

    class Config:
        from_attributes = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/questions", response_model=QuestionOut, status_code=201)
def create_question(q: QuestionCreate, db: Session = Depends(get_db)):
    question = Question(**q.model_dump())
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@app.get("/questions", response_model=List[QuestionOut])
def list_questions(db: Session = Depends(get_db)):
    return db.query(Question).all()


@app.get("/questions/random", response_model=QuestionOut)
def random_question(db: Session = Depends(get_db)):
    question = db.query(Question).order_by(func.random()).first()
    if not question:
        raise HTTPException(status_code=404, detail="Nenhuma pergunta cadastrada")
    return question


@app.get("/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")
    return question


@app.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: int, db: Session = Depends(get_db)):
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")
    db.delete(question)
    db.commit()
