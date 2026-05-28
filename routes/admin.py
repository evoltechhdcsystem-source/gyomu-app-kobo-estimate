from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta, timezone

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from models import Estimate, Inquiry, db

admin_bp = Blueprint("admin", __name__)
JST = timezone(timedelta(hours=9), "JST")


def admin_required():
    return session.get("admin_logged_in") is True


def format_jst(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(JST).strftime("%Y-%m-%d %H:%M")


def estimate_item_label(item_name: str) -> str:
    if " 画面単価 x " in item_name:
        return item_name.rsplit(" x ", 1)[-1]
    return item_name


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("admin_login.html")

    if (
        request.form.get("username") == current_app.config["ADMIN_USERNAME"]
        and request.form.get("password") == current_app.config["ADMIN_PASSWORD"]
    ):
        session["admin_logged_in"] = True
        return redirect(url_for("admin.dashboard"))

    flash("ログイン情報が正しくありません。", "danger")
    return render_template("admin_login.html"), 401


@admin_bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.get("/")
def dashboard():
    if not admin_required():
        return redirect(url_for("admin.login"))
    counts = {
        "total": Inquiry.query.count(),
        "open": Inquiry.query.filter_by(status="未対応").count(),
        "done": Inquiry.query.filter_by(status="対応済み").count(),
        "estimates": Estimate.query.count(),
    }
    return render_template("admin_dashboard.html", counts=counts)


@admin_bp.get("/estimates")
def estimates():
    if not admin_required():
        return redirect(url_for("admin.login"))
    rows = Estimate.query.order_by(Estimate.created_at.desc()).all()
    return render_template(
        "admin_estimates.html",
        estimates=rows,
        format_jst=format_jst,
        estimate_item_label=estimate_item_label,
    )


@admin_bp.get("/inquiries")
def inquiries():
    if not admin_required():
        return redirect(url_for("admin.login"))
    rows = Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    return render_template("admin_inquiries.html", inquiries=rows, format_jst=format_jst)


@admin_bp.route("/inquiries/<int:inquiry_id>", methods=["GET", "POST"])
def inquiry_detail(inquiry_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    inquiry = Inquiry.query.get_or_404(inquiry_id)
    back_to = request.args.get("from")
    back_url = url_for("admin.estimates") if back_to == "estimates" else url_for("admin.inquiries")
    back_label = "見積り履歴一覧へ戻る" if back_to == "estimates" else "一覧へ戻る"
    if request.method == "POST":
        inquiry.status = request.form.get("status", inquiry.status)
        db.session.commit()
        flash("ステータスを更新しました。", "success")
    return render_template(
        "admin_inquiry_detail.html",
        inquiry=inquiry,
        back_url=back_url,
        back_label=back_label,
    )


@admin_bp.get("/inquiries.csv")
def export_csv():
    if not admin_required():
        return redirect(url_for("admin.login"))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "会社名", "担当者名", "メール", "電話番号", "ステータス", "見積り金額", "作成日時"])
    for inquiry in Inquiry.query.order_by(Inquiry.created_at.desc()).all():
        writer.writerow(
            [
                inquiry.id,
                inquiry.company_name,
                inquiry.person_name,
                inquiry.email,
                inquiry.phone or "",
                inquiry.status,
                inquiry.estimate.total_price,
                format_jst(inquiry.created_at),
            ]
        )

    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inquiries.csv"},
    )
