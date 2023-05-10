from typing import Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    # https://www.sqlite.org/wal.html
    # https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#foreign-key-support
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.close()


class Base(DeclarativeBase):
    pass


class Page(Base):
    __tablename__ = "pages"

    title: Mapped[str] = mapped_column(primary_key=True)
    namespace_id: Mapped[int] = mapped_column(primary_key=True)
    redirect_to: Mapped[Optional[str]]
    need_pre_expand: Mapped[bool] = mapped_column(default=False)
    body: Mapped[Optional[str]]
    model: Mapped[Optional[str]]

    def __repr__(self) -> str:
        return f"Page(title={self.title!r}, namespace_id={self.namespace_id!r}, " + \
            f"redirect_to={self.redirect_to!r}, need_pre_expand={self.need_pre_expand!r} " + \
            f"model={self.model!r})"
