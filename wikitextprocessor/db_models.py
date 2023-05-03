from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, composite, mapped_column


class Base(DeclarativeBase):
    pass


@dataclass
class PageKey:
    title: str
    namespace_id: int


class Page(Base):
    __tablename__ = "pages"

    key: Mapped[PageKey] = composite(
        mapped_column("title"), mapped_column("namespace_id")
    )
    body: Mapped[str | None]
    redirect_to: Mapped[str | None] = mapped_column(index=True)
    need_pre_expand: Mapped[bool] = mapped_column(index=True, default=False)

    def __repr__(self) -> str:
        return f"Page(title={self.key.title!r}, namespace_id={self.key.namespace_id!r}, \
        redirect_to={self.redirect_to!r}, need_pre_expand={self.need_pre_expand!r})"
