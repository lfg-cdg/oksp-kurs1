"""Страницы клиентской части (формируются сервером, используют те же операции)."""
from functools import wraps

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from . import services as svc

web = Blueprint("web", __name__)

STATUS_LABELS = {"active": "на руках", "overdue": "просрочена",
                 "returned": "возвращена", "on_hand": "на руках (все)", "free": "свободен"}


@web.app_context_processor
def _globals():
    return {"STATUS_LABELS": STATUS_LABELS, "PREFIX": current_app.config["DB_SCHEMA"]}


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("web.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@web.errorhandler(svc.ServiceError)
def _service_error(exc: svc.ServiceError):
    return render_template("error.html", error=exc), exc.status


@web.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        try:
            user = svc.authenticate(g.session, request.form.get("login", ""),
                                    request.form.get("password", ""))
        except svc.ServiceError as exc:
            error = exc.message
        else:
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.full_name
            target = request.args.get("next", "")
            return redirect(target if target.startswith("/") else url_for("web.loans"))
    return render_template("login.html", error=error)


@web.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.login"))


@web.get("/")
def index():
    return redirect(url_for("web.loans"))


@web.get("/loans")
@login_required
def loans():
    page, size = svc.parse_paging(request.args)
    status = request.args.get("status") or None
    q = request.args.get("q") or None
    data = svc.list_loans(g.session, g.today, page, size, status=status, q=q)
    return render_template("loans.html", data=data, status=status or "", q=q or "")


@web.get("/loans/<int:loan_id>")
@login_required
def loan(loan_id: int):
    return render_template("loan.html", loan=svc.get_loan(g.session, g.today, loan_id))


@web.post("/loans/<int:loan_id>/return")
@login_required
def loan_return(loan_id: int):
    result = svc.return_loan(g.session, g.today, loan_id)
    flash(f"Возврат принят. Просрочка: {result['overdue_days']} дн., штраф: {result['fine']} ₽")
    return redirect(url_for("web.loan", loan_id=loan_id))


@web.route("/loans/new", methods=["GET", "POST"])
@login_required
def loan_new():
    form = {"reader_id": request.values.get("reader_id", ""),
            "copy_id": request.values.get("copy_id", ""),
            "days": request.values.get("days", "14")}
    error = None
    if request.method == "POST":
        try:
            created = svc.create_loan(
                g.session, g.today,
                reader_id=svc.parse_int(form["reader_id"], "reader_id", minimum=1),
                copy_id=svc.parse_int(form["copy_id"], "copy_id", minimum=1),
                days=svc.parse_int(form["days"], "days", default=14),
            )
        except svc.ServiceError as exc:
            error = exc.message
        else:
            flash("Экземпляр выдан")
            return redirect(url_for("web.loan", loan_id=created["id"]))
    return render_template("loan_new.html", form=form, error=error)


@web.get("/readers")
@login_required
def readers():
    page, size = svc.parse_paging(request.args)
    q = request.args.get("q") or None
    return render_template("readers.html", data=svc.list_readers(g.session, page, size, q=q),
                           q=q or "")


@web.get("/readers/<int:reader_id>")
@login_required
def reader(reader_id: int):
    return render_template("reader.html", reader=svc.get_reader(g.session, g.today, reader_id))


@web.get("/books")
@login_required
def books():
    page, size = svc.parse_paging(request.args)
    q = request.args.get("q") or None
    return render_template("books.html", data=svc.list_books(g.session, page, size, q=q),
                           q=q or "")


@web.get("/books/<int:book_id>")
@login_required
def book(book_id: int):
    return render_template("book.html", book=svc.get_book(g.session, g.today, book_id))


@web.get("/summary")
@login_required
def summary():
    return render_template("summary.html", s=svc.summary(g.session, g.today))
