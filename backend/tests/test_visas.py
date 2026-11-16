"""«Мои визы»: добавление, показ на главной, напоминания за 20/15/7 дней."""
from app.services import visas as visas_svc


def test_thresholds():
    assert visas_svc.threshold_for(25) is None
    assert visas_svc.threshold_for(20) == 20 and visas_svc.threshold_for(18) == 20
    assert visas_svc.threshold_for(15) == 15 and visas_svc.threshold_for(10) == 15
    assert visas_svc.threshold_for(7) == 7 and visas_svc.threshold_for(0) == 7
    assert visas_svc.threshold_for(-1) is None


def test_upcoming_includes_manual_visa_of_non_client():
    from datetime import date, timedelta

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.kommo.mock import MockKommo
    from app.models import Base, User, UserVisa

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = Session(eng)
    u = User(telegram_id=77, first_name="Оля")
    db.add(u); db.flush()
    db.add(UserVisa(user_id=u.id, visa_type="KITAS удалёнщика E33G", expires_on=date.today() + timedelta(days=18)))
    db.add(UserVisa(user_id=u.id, visa_type="VOA (виза по прилёту)", expires_on=date.today() + timedelta(days=60)))
    db.commit()
    due = visas_svc.upcoming(db, MockKommo())
    assert [d.title for d in due] == ["KITAS удалёнщика E33G"] and not due[0].is_client
    assert visas_svc.threshold_for(due[0].days_left) == 20 and "18 дн." in visas_svc.reminder_text(due[0])
