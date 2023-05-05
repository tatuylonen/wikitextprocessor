from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, composite, mapped_column


class Base(DeclarativeBase):
    pass


class Page(Base):
    __tablename__ = "pages"

    title: Mapped[str] = mapped_column(primary_key=True)
    namespace_id: Mapped[int] = mapped_column(primary_key=True)
    redirect_to: Mapped[Optional[str]] = mapped_column(index=True)
    need_pre_expand: Mapped[bool] = mapped_column(index=True, default=False)
    body: Mapped[Optional[str]]
    model: Mapped[Optional[str]]

    def __repr__(self) -> str:
        return f"Page(title={self.title!r}, namespace_id={self.namespace_id!r}, " + \
            f"redirect_to={self.redirect_to!r}, need_pre_expand={self.need_pre_expand!r})" + \
            f"model={self.model!r}"
