# ClubsHub Permissions Matrix

## Global roles
- `student`
- `institute_admin`
- `system_admin`

## Scoped local roles (via `ClubMembership.local_role`)
- `member`
- `secretary`
- `coordinator`

## Key rules
- Students join/leave clubs through one membership model.
- Leaving a club resets local role to `member`; rejoining returns as normal member.
- Only institute/system admins can create or hard-delete clubs/events/rooms.
- Coordinators manage club-scoped operations and may assign/revoke secretary inside their active club.
- Secretaries can create club-scoped events/rooms, but cannot grant roles or moderate reports.
- Report dashboard/actions are restricted to institute/system admins.
- Private invite-only rooms require accepted invite before joining.
- Announcements may be posted by coordinators (club scope) and admins.

## Archive vs delete
- Events and rooms support archive-style lifecycle fields (`is_archived` / status transitions).
- Hard deletion remains admin-only at policy level.

## Migration notes
- Legacy global `club_rep` and `moderator` logic is retired in app authorization.
- Legacy follower/representative relationships are not used for access decisions.
