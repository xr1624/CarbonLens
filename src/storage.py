"""SQLite/PostgreSQL case storage with owner checks and atomic quota reservations."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Column, Integer, MetaData, String, Table, Text, create_engine, select, update,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from src.cases import Case, decode_case, encode_case


class ConflictError(ValueError):
    pass


class QuotaError(ValueError):
    pass


class Store:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        if self.engine.dialect.name not in ("sqlite", "postgresql"):
            raise ValueError("資料庫支援 SQLite 與 PostgreSQL。")
        metadata = MetaData()
        self.cases = Table(
            "carbonlens_cases", metadata,
            Column("case_id", String(64), primary_key=True),
            Column("owner", String(128), nullable=False, index=True),
            Column("revision", Integer, nullable=False),
            Column("payload", Text, nullable=False),
        )
        self.versions = Table(
            "carbonlens_versions", metadata,
            Column("case_id", String(64), primary_key=True),
            Column("revision", Integer, primary_key=True),
            Column("owner", String(128), nullable=False),
            Column("payload", Text, nullable=False),
        )
        self.counters = Table(
            "carbonlens_usage", metadata,
            Column("period", String(16), primary_key=True),
            Column("scope", String(256), primary_key=True),
            Column("used", Integer, nullable=False),
        )
        self.attempts = Table(
            "carbonlens_api_attempts", metadata,
            Column("run_id", String(64), primary_key=True),
            Column("owner", String(128), nullable=False),
            Column("at", String(64), nullable=False),
        )
        metadata.create_all(self.engine)

    def save(self, owner: str, case: Case) -> Case:
        if not owner:
            raise ValueError("保存案件需要已驗證的使用者。")
        saved = replace(case, revision=case.revision + 1)
        payload = encode_case(saved)
        try:
            with self.engine.begin() as connection:
                if case.revision == 0:
                    connection.execute(self.cases.insert().values(
                        case_id=case.case_id, owner=owner, revision=1, payload=payload
                    ))
                else:
                    outcome = connection.execute(
                        update(self.cases).where(
                            self.cases.c.case_id == case.case_id,
                            self.cases.c.owner == owner,
                            self.cases.c.revision == case.revision,
                        ).values(revision=saved.revision, payload=payload)
                    )
                    if outcome.rowcount != 1:
                        raise ConflictError("案件已更新或無存取權限，請重新載入。")
                connection.execute(self.versions.insert().values(
                    case_id=case.case_id, owner=owner,
                    revision=saved.revision, payload=payload,
                ))
        except IntegrityError:
            raise ConflictError("案件版本已存在，請重新載入。") from None
        return saved

    def list_cases(self, owner: str) -> list[Case]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(self.cases.c.payload).where(self.cases.c.owner == owner)
            )
            return sorted((decode_case(row.payload) for row in rows), key=lambda case: case.created_at)

    def history(self, owner: str, case_id: str) -> list[Case]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(self.versions.c.payload).where(
                self.versions.c.owner == owner, self.versions.c.case_id == case_id,
            ).order_by(self.versions.c.revision))
            return [decode_case(row.payload) for row in rows]

    def reserve_call(self, owner: str, run_id: str, user_limit: int, global_limit: int):
        if not owner:
            raise PermissionError("付費分析需要登入。")
        period = datetime.now(timezone.utc).date().isoformat()
        insert = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        try:
            with self.engine.begin() as connection:
                connection.execute(self.attempts.insert().values(
                    run_id=run_id, owner=owner, at=datetime.now(timezone.utc).isoformat()
                ))
                for scope, limit in (("global", global_limit), (f"user:{owner}", user_limit)):
                    connection.execute(insert(self.counters).values(
                        period=period, scope=scope, used=0
                    ).on_conflict_do_nothing())
                    outcome = connection.execute(update(self.counters).where(
                        self.counters.c.period == period, self.counters.c.scope == scope,
                        self.counters.c.used < limit,
                    ).values(used=self.counters.c.used + 1))
                    if outcome.rowcount != 1:
                        raise QuotaError("今日 AI 呼叫額度已用完，請稍後再試或聯絡管理者。")
        except IntegrityError:
            raise QuotaError("此執行已送出過模型請求，請使用新的重試執行。") from None


def default_database_url() -> str:
    directory = Path(__file__).resolve().parents[1] / "runtime"
    directory.mkdir(exist_ok=True)
    return f"sqlite:///{(directory / 'CarbonLens.sqlite3').as_posix()}"
