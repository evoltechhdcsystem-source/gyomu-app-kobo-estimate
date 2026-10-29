from models import FULL_PLAN, FeatureMaster, stored_master_name

MAINTENANCE_NAME = "サーバー保守/月"
GOOGLE_CLOUD_MONTHLY_MIN = 3000


def monthly_total_label(estimate):
    if estimate.maintenance_monthly_price is None:
        return f"{GOOGLE_CLOUD_MONTHLY_MIN:,}円～／月"
    if estimate.maintenance_quote_required:
        return f"{GOOGLE_CLOUD_MONTHLY_MIN:,}円～／月"
    return f"{GOOGLE_CLOUD_MONTHLY_MIN + estimate.maintenance_monthly_price:,}円～／月"


def monthly_total_note(estimate):
    if estimate.maintenance_monthly_price is not None and estimate.maintenance_quote_required:
        return "サーバー保守は要相談のため、合計に含みません。"
    return ""


def maintenance_option(plan_key):
    if plan_key != FULL_PLAN:
        return None
    return FeatureMaster.query.filter_by(
        plan_key=FULL_PLAN, name=stored_master_name(FULL_PLAN, MAINTENANCE_NAME), is_active=True,
    ).first()
