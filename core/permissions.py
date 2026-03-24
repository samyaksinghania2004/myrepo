from __future__ import annotations

from typing import Optional

from accounts.models import User


LOCAL_ROLE_MEMBER = "member"
LOCAL_ROLE_SECRETARY = "secretary"
LOCAL_ROLE_COORDINATOR = "coordinator"


def is_system_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.role == User.Role.SYSTEM_ADMIN)


def is_institute_admin(user) -> bool:
    return bool(user and user.is_authenticated and user.role == User.Role.INSTITUTE_ADMIN)


def is_global_admin(user) -> bool:
    return is_system_admin(user) or is_institute_admin(user)


def can_create_club(user) -> bool:
    return is_global_admin(user)


def can_archive_or_delete_club(user) -> bool:
    return is_global_admin(user)


def get_membership(club, user):
    if not user or not user.is_authenticated:
        return None
    return club.memberships.filter(user=user, status="active").first()


def has_local_role(club, user, local_roles: set[str]) -> bool:
    membership = get_membership(club, user)
    return bool(membership and membership.local_role in local_roles)


def can_manage_club(user, club) -> bool:
    return is_global_admin(user) or has_local_role(club, user, {LOCAL_ROLE_COORDINATOR})


def can_assign_secretary(user, club, target_user) -> bool:
    if is_global_admin(user):
        return True
    if not has_local_role(club, user, {LOCAL_ROLE_COORDINATOR}):
        return False
    target = get_membership(club, target_user)
    return bool(target and target.status == "active")


def can_create_event(user, club) -> bool:
    if is_global_admin(user):
        return True
    return has_local_role(club, user, {LOCAL_ROLE_COORDINATOR, LOCAL_ROLE_SECRETARY})


def can_manage_event(user, event) -> bool:
    if is_global_admin(user):
        return True
    if event.created_by_id == user.id:
        return True
    return has_local_role(event.club, user, {LOCAL_ROLE_COORDINATOR})


def can_create_room(user, club=None, event=None) -> bool:
    if is_global_admin(user):
        return True
    target_club = club or (event.club if event else None)
    if target_club is None:
        return False
    return has_local_role(target_club, user, {LOCAL_ROLE_COORDINATOR, LOCAL_ROLE_SECRETARY})


def can_manage_room(user, room) -> bool:
    if is_global_admin(user):
        return True
    if room.created_by_id == user.id:
        return True
    if room.club:
        return has_local_role(room.club, user, {LOCAL_ROLE_COORDINATOR})
    if room.event:
        return has_local_role(room.event.club, user, {LOCAL_ROLE_COORDINATOR})
    return False


def can_view_reports(user) -> bool:
    return is_global_admin(user)


def can_post_announcement(user, *, club=None, event=None, room=None) -> bool:
    if is_global_admin(user):
        return True
    base_club = club
    if event is not None:
        base_club = event.club
    if room is not None:
        base_club = room.club or (room.event.club if room.event else None)
    if base_club is None:
        return False
    return has_local_role(base_club, user, {LOCAL_ROLE_COORDINATOR})
