"""Зависимости доступа внутри отдела.

Строятся поверх app.core.security.staff_user: общая роль по-прежнему EMPLOYEE,
роль внутри отдела добирается из staff_profiles.
"""

from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import staff_user
from app.models import User
from app.staff_pipeline.enums import StaffRole
from app.staff_pipeline.models import StaffProfile


@dataclass(frozen=True)
class DepartmentMember:
    """Сотрудник банка вместе с его ролью внутри отдела."""

    user: User
    staff_role: StaffRole | None
    # Применяются ли к сотруднику правила конвейера. Для учётных записей, существовавших
    # до появления отдела, — нет: их поведение по контракту менять нельзя.
    pipeline_enforced: bool = True

    @property
    def is_verifier(self) -> bool:
        return self.staff_role == StaffRole.VERIFIER

    @property
    def is_underwriter(self) -> bool:
        return self.staff_role == StaffRole.UNDERWRITER


def staff_role_of(db: Session, user: User) -> StaffRole | None:
    profile = db.get(StaffProfile, user.id)
    if profile is None:
        return None
    try:
        return StaffRole(profile.staff_role)
    except ValueError:  # незнакомое значение в базе не должно ронять ручку
        return None


def member_of(db: Session, user: User) -> DepartmentMember:
    """Сотрудник без профиля отдела работает как раньше: правила конвейера к нему не применяются."""
    profile = db.get(StaffProfile, user.id)
    return DepartmentMember(
        user=user,
        staff_role=staff_role_of(db, user),
        pipeline_enforced=bool(profile.pipeline_enforced) if profile else False,
    )


def current_member(user: User = Depends(staff_user), db: Session = Depends(get_db)) -> DepartmentMember:
    return member_of(db, user)
