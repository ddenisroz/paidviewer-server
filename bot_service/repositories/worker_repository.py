"""Repository helpers for worker-agent state."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models.worker import Worker, WorkerPairingToken
from services.worker_control.tokens import hash_secret


class WorkerRepository:
    """Database access helpers for workers and pairing tokens."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_worker_key(self, worker_key: str) -> Optional[Worker]:
        return self.db.query(Worker).filter(Worker.worker_key == worker_key).first()

    def get_by_auth_token(self, raw_token: str) -> Optional[Worker]:
        token_hash = hash_secret(raw_token)
        return self.db.query(Worker).filter(Worker.auth_token_hash == token_hash).first()

    def list_for_user(self, owner_user_id: int) -> list[Worker]:
        return (
            self.db.query(Worker)
            .filter(Worker.owner_user_id == owner_user_id)
            .order_by(Worker.created_at.desc())
            .all()
        )

    def get_for_user(self, owner_user_id: int, worker_key: str) -> Optional[Worker]:
        return (
            self.db.query(Worker)
            .filter(Worker.owner_user_id == owner_user_id, Worker.worker_key == worker_key)
            .first()
        )

    def create_pairing_token(self, token: WorkerPairingToken) -> WorkerPairingToken:
        self.db.add(token)
        self.db.commit()
        self.db.refresh(token)
        return token

    def get_pairing_token(self, raw_token: str) -> Optional[WorkerPairingToken]:
        token_hash = hash_secret(raw_token)
        return (
            self.db.query(WorkerPairingToken)
            .filter(WorkerPairingToken.token_hash == token_hash)
            .first()
        )

    def create_worker(self, worker: Worker) -> Worker:
        self.db.add(worker)
        self.db.commit()
        self.db.refresh(worker)
        return worker

    def save(self, worker: Worker) -> Worker:
        self.db.add(worker)
        self.db.commit()
        self.db.refresh(worker)
        return worker

    def delete(self, worker: Worker) -> None:
        self.db.delete(worker)
        self.db.commit()
