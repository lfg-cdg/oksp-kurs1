"""ORM-модели: читатель, книга, экземпляр, выдача и учётная запись библиотекаря."""
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Librarian(Base):
    __tablename__ = "librarian"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    full_name: Mapped[str]


class Reader(Base):
    __tablename__ = "reader"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str]
    card_number: Mapped[str]
    email: Mapped[Optional[str]]
    phone: Mapped[Optional[str]]
    registered_at: Mapped[date]

    loans: Mapped[list["Loan"]] = relationship(back_populates="reader")


class Book(Base):
    __tablename__ = "book"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author: Mapped[str]
    year: Mapped[Optional[int]]
    isbn: Mapped[Optional[str]]

    copies: Mapped[list["Copy"]] = relationship(back_populates="book")


class Copy(Base):
    __tablename__ = "copy"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"))
    inventory_number: Mapped[str]
    shelf: Mapped[Optional[str]]

    book: Mapped[Book] = relationship(back_populates="copies")
    loans: Mapped[list["Loan"]] = relationship(back_populates="copy")


class Loan(Base):
    __tablename__ = "loan"

    id: Mapped[int] = mapped_column(primary_key=True)
    copy_id: Mapped[int] = mapped_column(ForeignKey("copy.id"))
    reader_id: Mapped[int] = mapped_column(ForeignKey("reader.id"))
    issued_at: Mapped[date]
    due_at: Mapped[date]
    returned_at: Mapped[Optional[date]]
    fine: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    copy: Mapped[Copy] = relationship(back_populates="loans")
    reader: Mapped[Reader] = relationship(back_populates="loans")
