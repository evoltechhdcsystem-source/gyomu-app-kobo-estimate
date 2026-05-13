from __future__ import annotations

import csv
import io

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

from models import Inquiry, db

admin_bp = Blueprint("admin", __name__)


def admin_required():
    return session.get("admin_logged_in") is True


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
    }
    return render_template("admin_dashboard.html", counts=counts)


@admin_bp.get("/inquiries")
def inquiries():
    if not admin_required():
        return redirect(url_for("admin.login"))
    rows = Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    return render_template("admin_inquiries.html", inquiries=rows)


@admin_bp.route("/inquiries/<int:inquiry_id>", methods=["GET", "POST"])
def inquiry_detail(inquiry_id: int):
    if not admin_required():
        return redirect(url_for("admin.login"))
    inquiry = Inquiry.query.get_or_404(inquiry_id)
    if request.method == "POST":
        inquiry.status = request.form.get("status", inquiry.status)
        db.session.commit()
        flash("ステータスを更新しました。", "success")
    return render_template("admin_inquiry_detail.html", inquiry=inquiry)


@admin_bp.get("/inquiries.csv")
def export_csv():
    if not admin_required():
        return redirect(url_for("admin.login"))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "会社名", "担当者名", "メール", "電話番号", "ステータス", "見積金額", "作成日時"])
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
                inquiry.created_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )

    return Response(
        output.getvalue().encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=inquiries.csv"},
    )

