from models import FULL_PLAN, FeatureMaster, stored_master_name

MAINTENANCE_NAME = "サーバー保守/月"


def maintenance_option(plan_key):
    if plan_key != FULL_PLAN:
        return None
    return FeatureMaster.query.filter_by(
        plan_key=FULL_PLAN, name=stored_master_name(FULL_PLAN, MAINTENANCE_NAME), is_active=True,
    ).first()
