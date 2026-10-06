from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

from app.models import (
    Staff, Theme, Venue, StaffTheme, StaffVenue, School,
    Session, Assignment, Review, Warning,
    ChangeRequest, ChangeHistory, SessionConflict, RescheduleSuggestion,
    LevelBadge, PointRecord, MonthlyRanking, StaffBadge,
    StaffType, SessionType, SessionStatus, AssignmentRole,
    AudienceType, WarningType, ChangeType, ChangeStatus,
    ConflictType, RescheduleStatus, PointSourceType
)
from app import schemas
from app.config import settings


def _check_time_overlap(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    return start1 < end2 and start2 < end1


def get_staff(db: Session, staff_id: int) -> Optional[Staff]:
    return db.query(Staff).filter(Staff.id == staff_id).first()


def get_staff_list(db: Session, skip: int = 0, limit: int = 100,
                   staff_type: Optional[StaffType] = None,
                   theme_id: Optional[int] = None) -> List[Staff]:
    query = db.query(Staff).options(
        joinedload(Staff.themes).joinedload(StaffTheme.theme),
        joinedload(Staff.venues).joinedload(StaffVenue.venue)
    ).filter(Staff.is_active == True)
    if staff_type:
        query = query.filter(Staff.staff_type == staff_type)
    if theme_id:
        query = query.filter(Staff.themes.any(StaffTheme.theme_id == theme_id))
    return query.offset(skip).limit(limit).all()


def create_staff(db: Session, staff_in: schemas.StaffCreate) -> Staff:
    db_staff = Staff(
        name=staff_in.name,
        staff_type=staff_in.staff_type,
        phone=staff_in.phone,
        email=staff_in.email
    )
    db.add(db_staff)
    db.flush()

    for theme in staff_in.themes:
        db_staff_theme = StaffTheme(
            staff_id=db_staff.id,
            theme_id=theme.theme_id,
            proficiency_level=theme.proficiency_level
        )
        db.add(db_staff_theme)

    for venue in staff_in.venues:
        db_staff_venue = StaffVenue(
            staff_id=db_staff.id,
            venue_id=venue.venue_id,
            is_certified=venue.is_certified
        )
        db.add(db_staff_venue)

    db.commit()
    db.refresh(db_staff)
    return db_staff


def update_staff(db: Session, staff_id: int, staff_in: schemas.StaffUpdate) -> Optional[Staff]:
    db_staff = get_staff(db, staff_id)
    if not db_staff:
        return None

    update_data = staff_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field not in ["themes", "venues"]:
            setattr(db_staff, field, value)

    if staff_in.themes is not None:
        db.query(StaffTheme).filter(StaffTheme.staff_id == staff_id).delete()
        for theme in staff_in.themes:
            db_staff_theme = StaffTheme(
                staff_id=staff_id,
                theme_id=theme.theme_id,
                proficiency_level=theme.proficiency_level
            )
            db.add(db_staff_theme)

    if staff_in.venues is not None:
        db.query(StaffVenue).filter(StaffVenue.staff_id == staff_id).delete()
        for venue in staff_in.venues:
            db_staff_venue = StaffVenue(
                staff_id=staff_id,
                venue_id=venue.venue_id,
                is_certified=venue.is_certified
            )
            db.add(db_staff_venue)

    db.commit()
    db.refresh(db_staff)
    return db_staff


def get_theme(db: Session, theme_id: int) -> Optional[Theme]:
    return db.query(Theme).filter(Theme.id == theme_id).first()


def get_theme_list(db: Session, skip: int = 0, limit: int = 100) -> List[Theme]:
    return db.query(Theme).offset(skip).limit(limit).all()


def create_theme(db: Session, theme_in: schemas.ThemeCreate) -> Theme:
    db_theme = Theme(**theme_in.model_dump())
    db.add(db_theme)
    db.commit()
    db.refresh(db_theme)
    return db_theme


def get_venue(db: Session, venue_id: int) -> Optional[Venue]:
    return db.query(Venue).filter(Venue.id == venue_id).first()


def get_venue_list(db: Session, skip: int = 0, limit: int = 100) -> List[Venue]:
    return db.query(Venue).offset(skip).limit(limit).all()


def create_venue(db: Session, venue_in: schemas.VenueCreate) -> Venue:
    db_venue = Venue(**venue_in.model_dump())
    db.add(db_venue)
    db.commit()
    db.refresh(db_venue)
    return db_venue


def get_school(db: Session, school_id: int) -> Optional[School]:
    return db.query(School).filter(School.id == school_id).first()


def get_school_list(db: Session, skip: int = 0, limit: int = 100) -> List[School]:
    return db.query(School).offset(skip).limit(limit).all()


def create_school(db: Session, school_in: schemas.SchoolCreate) -> School:
    db_school = School(**school_in.model_dump())
    db.add(db_school)
    db.commit()
    db.refresh(db_school)
    return db_school


def is_staff_available(db: Session, staff_id: int, start_time: datetime,
                       end_time: datetime, exclude_session_id: Optional[int] = None) -> bool:
    query = db.query(Assignment).join(Session).filter(
        Assignment.staff_id == staff_id,
        Session.status.in_([SessionStatus.SCHEDULED, SessionStatus.DRAFT])
    )
    if exclude_session_id:
        query = query.filter(Assignment.session_id != exclude_session_id)

    assignments = query.all()
    for assignment in assignments:
        if _check_time_overlap(start_time, end_time,
                               assignment.session.start_time, assignment.session.end_time):
            return False
    return True


def is_staff_qualified(db: Session, staff_id: int, theme_id: int, venue_id: int,
                       role: AssignmentRole) -> Tuple[bool, List[str]]:
    errors = []
    staff = get_staff(db, staff_id)
    if not staff:
        return False, ["人员不存在"]

    if role == AssignmentRole.LECTURER and staff.staff_type != StaffType.LECTURER:
        errors.append(f"人员 {staff.name} 不是讲师，不能担任主讲")
    if role == AssignmentRole.GUIDE and staff.staff_type != StaffType.GUIDE:
        errors.append(f"人员 {staff.name} 不是讲解员，不能担任讲解员")

    has_theme = db.query(StaffTheme).filter(
        StaffTheme.staff_id == staff_id,
        StaffTheme.theme_id == theme_id
    ).first()
    if not has_theme:
        errors.append(f"人员 {staff.name} 不擅长该主题领域")

    has_venue = db.query(StaffVenue).filter(
        StaffVenue.staff_id == staff_id,
        StaffVenue.venue_id == venue_id,
        StaffVenue.is_certified == True
    ).first()
    if not has_venue:
        errors.append(f"人员 {staff.name} 不具备该场地的上岗资格")

    return len(errors) == 0, errors


def validate_assignment(db: Session, session_id: int, staff_id: int,
                        role: AssignmentRole) -> schemas.AssignmentValidationResult:
    errors = []
    warnings = []

    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        return schemas.AssignmentValidationResult(valid=False, errors=["场次不存在"])

    qualified, qual_errors = is_staff_qualified(db, staff_id, session.theme_id, session.venue_id, role)
    if not qualified:
        errors.extend(qual_errors)

    if not is_staff_available(db, staff_id, session.start_time, session.end_time, session_id):
        errors.append(f"该人员在 {session.start_time} - {session.end_time} 已有安排")

    existing_role_count = db.query(Assignment).filter(
        Assignment.session_id == session_id,
        Assignment.role == role
    ).count()

    if role == AssignmentRole.LECTURER and existing_role_count >= 1:
        errors.append("该场次已安排主讲，不能重复安排")

    if role == AssignmentRole.GUIDE and existing_role_count >= session.guides_needed:
        warnings.append(f"该场次所需讲解员已达 {session.guides_needed} 人，继续安排将超出需求")

    return schemas.AssignmentValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings
    )


def is_session_fully_staffed(db: Session, session_id: int) -> bool:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        return False

    guide_count = db.query(Assignment).filter(
        Assignment.session_id == session_id,
        Assignment.role == AssignmentRole.GUIDE
    ).count()

    has_lecturer = db.query(Assignment).filter(
        Assignment.session_id == session_id,
        Assignment.role == AssignmentRole.LECTURER
    ).first() is not None

    guides_ok = guide_count >= session.guides_needed
    lecturer_ok = not session.needs_lecturer or has_lecturer

    return guides_ok and lecturer_ok


def get_session(db: Session, session_id: int) -> Optional[Session]:
    return db.query(Session).options(
        joinedload(Session.assignments).joinedload(Assignment.staff),
        joinedload(Session.theme),
        joinedload(Session.venue),
        joinedload(Session.school)
    ).filter(Session.id == session_id).first()


def get_session_list(db: Session, skip: int = 0, limit: int = 100,
                     status: Optional[SessionStatus] = None,
                     start_date: Optional[datetime] = None,
                     end_date: Optional[datetime] = None,
                     theme_id: Optional[int] = None) -> List[Session]:
    query = db.query(Session).options(
        joinedload(Session.assignments).joinedload(Assignment.staff),
        joinedload(Session.theme),
        joinedload(Session.venue),
        joinedload(Session.school)
    )
    if status:
        query = query.filter(Session.status == status)
    if start_date:
        query = query.filter(Session.start_time >= start_date)
    if end_date:
        query = query.filter(Session.end_time <= end_date)
    if theme_id:
        query = query.filter(Session.theme_id == theme_id)
    return query.order_by(Session.start_time).offset(skip).limit(limit).all()


def create_session(db: Session, session_in: schemas.SessionCreate) -> Session:
    db_session = Session(**session_in.model_dump())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


def update_session(db: Session, session_id: int,
                   session_in: schemas.SessionUpdate) -> Tuple[Optional[Session], List[str]]:
    db_session = get_session(db, session_id)
    if not db_session:
        return None, ["场次不存在"]

    old_start = db_session.start_time
    old_end = db_session.end_time
    old_guides_needed = db_session.guides_needed
    old_needs_lecturer = db_session.needs_lecturer
    old_status = db_session.status

    update_data = session_in.model_dump(exclude_unset=True)

    validation_errors = []

    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == SessionStatus.SCHEDULED and old_status != SessionStatus.SCHEDULED:
            if not is_session_fully_staffed(db, session_id):
                validation_errors.append("人员配置不足，无法标记为已排定状态")
                del update_data["status"]

    for field, value in update_data.items():
        setattr(db_session, field, value)

    time_changed = (session_in.start_time is not None and session_in.start_time != old_start) or \
                   (session_in.end_time is not None and session_in.end_time != old_end)
    needs_changed = (session_in.guides_needed is not None and session_in.guides_needed != old_guides_needed) or \
                    (session_in.needs_lecturer is not None and session_in.needs_lecturer != old_needs_lecturer)

    if time_changed or needs_changed:
        for assignment in db_session.assignments:
            if time_changed:
                if not is_staff_available(db, assignment.staff_id,
                                          db_session.start_time, db_session.end_time, session_id):
                    staff = get_staff(db, assignment.staff_id)
                    validation_errors.append(
                        f"人员 {staff.name if staff else assignment.staff_id} 在新时间段已有安排"
                    )

        if not is_session_fully_staffed(db, session_id):
            if db_session.status == SessionStatus.SCHEDULED:
                validation_errors.append("人员配置不足，已自动将状态改回草稿")
                db_session.status = SessionStatus.DRAFT
            else:
                validation_errors.append("人员配置不足，需重新核对排班")

    # 场次改期：若冻结的内容版本在新时间不再生效，置为“待重新确认”
    if time_changed:
        if refresh_confirmation_after_reschedule(db, db_session):
            validation_errors.append("改期后原内容版本不再覆盖新时间，场次内容需重新确认")

    db.commit()
    db.refresh(db_session)
    return db_session, validation_errors


def create_assignment(db: Session, session_id: int,
                      assignment_in: schemas.AssignmentCreate) -> Tuple[Optional[Assignment], List[str]]:
    validation = validate_assignment(db, session_id, assignment_in.staff_id, assignment_in.role)
    if not validation.valid:
        return None, validation.errors

    db_assignment = Assignment(
        session_id=session_id,
        staff_id=assignment_in.staff_id,
        role=assignment_in.role,
        is_primary=assignment_in.is_primary
    )
    db.add(db_assignment)
    db.flush()

    session = db.query(Session).filter(Session.id == session_id).first()
    if is_session_fully_staffed(db, session_id) and session.status == SessionStatus.DRAFT:
        session.status = SessionStatus.SCHEDULED

    db.commit()
    db.refresh(db_assignment)
    return db_assignment, []


def delete_assignment(db: Session, assignment_id: int) -> Tuple[bool, List[str]]:
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        return False, ["排班记录不存在"]

    session_id = assignment.session_id
    db.delete(assignment)
    db.flush()

    session = db.query(Session).filter(Session.id == session_id).first()
    if session and session.status == SessionStatus.SCHEDULED:
        if not is_session_fully_staffed(db, session_id):
            session.status = SessionStatus.DRAFT

    db.commit()
    return True, []


def get_review(db: Session, review_id: int) -> Optional[Review]:
    return db.query(Review).join(Session).filter(Review.id == review_id).first()


def get_review_list(db: Session, skip: int = 0, limit: int = 100,
                    session_id: Optional[int] = None,
                    staff_id: Optional[int] = None) -> List[Review]:
    query = db.query(Review).join(Session)
    if session_id:
        query = query.filter(Review.session_id == session_id)
    if staff_id:
        query = query.join(Assignment).filter(Assignment.staff_id == staff_id)
    return query.order_by(Review.created_at.desc()).offset(skip).limit(limit).all()





def check_staff_shortage(db: Session) -> List[Warning]:
    existing_warnings = db.query(Warning).filter(
        Warning.warning_type == WarningType.STAFF_SHORTAGE,
        Warning.resolved == False
    ).all()
    for w in existing_warnings:
        w.resolved = True
    db.flush()

    upcoming_sessions = db.query(Session).filter(
        Session.status.in_([SessionStatus.DRAFT, SessionStatus.SCHEDULED]),
        Session.start_time >= datetime.now()
    ).all()

    theme_demand = {}
    for session in upcoming_sessions:
        theme_id = session.theme_id
        if theme_id not in theme_demand:
            theme_demand[theme_id] = {"sessions": 0, "guides_needed": 0, "lecturers_needed": 0}
        theme_demand[theme_id]["sessions"] += 1
        theme_demand[theme_id]["guides_needed"] += session.guides_needed
        if session.needs_lecturer:
            theme_demand[theme_id]["lecturers_needed"] += 1

    warnings = []
    for theme_id, demand in theme_demand.items():
        theme = get_theme(db, theme_id)
        if not theme:
            continue

        available_guides = db.query(Staff).join(StaffTheme).filter(
            Staff.staff_type == StaffType.GUIDE,
            Staff.is_active == True,
            StaffTheme.theme_id == theme_id
        ).count()

        available_lecturers = db.query(Staff).join(StaffTheme).filter(
            Staff.staff_type == StaffType.LECTURER,
            Staff.is_active == True,
            StaffTheme.theme_id == theme_id
        ).count()

        if demand["guides_needed"] > 0 and available_guides > 0:
            ratio = available_guides / demand["guides_needed"]
            if ratio < settings.WARNING_STAFF_SHORTAGE_THRESHOLD:
                message = f"主题「{theme.name}」讲解员缺口较大：需求 {demand['guides_needed']} 人，可用仅 {available_guides} 人"
                warning = Warning(
                    theme_id=theme_id,
                    warning_type=WarningType.STAFF_SHORTAGE,
                    message=message
                )
                db.add(warning)
                warnings.append(warning)

        if demand["lecturers_needed"] > 0 and available_lecturers == 0:
            message = f"主题「{theme.name}」无可用讲师：需求 {demand['lecturers_needed']} 人"
            warning = Warning(
                theme_id=theme_id,
                warning_type=WarningType.STAFF_SHORTAGE,
                message=message
            )
            db.add(warning)
            warnings.append(warning)

    db.commit()
    return warnings


def get_warning_list(db: Session, resolved: Optional[bool] = None) -> List[Warning]:
    query = db.query(Warning).join(Theme)
    if resolved is not None:
        query = query.filter(Warning.resolved == resolved)
    return query.order_by(Warning.created_at.desc()).all()


def get_theme_session_stats(db: Session, start_date: Optional[datetime] = None,
                            end_date: Optional[datetime] = None) -> List[schemas.ThemeSessionStats]:
    query = db.query(
        Session.theme_id,
        Theme.name.label("theme_name"),
        func.count(Session.id).label("session_count"),
        func.sum(Session.guides_needed).label("guide_count")
    ).join(Theme).filter(Session.status != SessionStatus.CANCELLED)

    if start_date:
        query = query.filter(Session.start_time >= start_date)
    if end_date:
        query = query.filter(Session.end_time <= end_date)

    results = query.group_by(Session.theme_id, Theme.name).all()

    return [
        schemas.ThemeSessionStats(
            theme_id=r.theme_id,
            theme_name=r.theme_name,
            session_count=r.session_count,
            guide_count=r.guide_count or 0
        )
        for r in results
    ]


def get_staff_saturation(db: Session, start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> List[schemas.StaffSaturationStats]:
    if not start_date:
        start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    if not end_date:
        next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month - timedelta(seconds=1)

    total_hours = (end_date - start_date).total_seconds() / 3600
    working_hours_per_day = 8
    working_days = max(1, int(total_hours / 24))
    available_hours = working_hours_per_day * working_days

    staff_list = get_staff_list(db)
    stats = []

    for staff in staff_list:
        assignments = db.query(Assignment).join(Session).filter(
            Assignment.staff_id == staff.id,
            Session.start_time >= start_date,
            Session.end_time <= end_date,
            Session.status.in_([SessionStatus.SCHEDULED, SessionStatus.COMPLETED])
        ).all()

        assigned_hours = 0.0
        for a in assignments:
            session_start = max(a.session.start_time, start_date)
            session_end = min(a.session.end_time, end_date)
            assigned_hours += max(0, (session_end - session_start).total_seconds() / 3600)

        saturation_rate = round(assigned_hours / available_hours * 100, 1) if available_hours > 0 else 0

        stats.append(schemas.StaffSaturationStats(
            staff_id=staff.id,
            staff_name=staff.name,
            staff_type=staff.staff_type.value,
            assigned_hours=round(assigned_hours, 1),
            available_hours=available_hours,
            saturation_rate=saturation_rate
        ))

    return sorted(stats, key=lambda x: x.saturation_rate, reverse=True)


def get_staff_ranking(db: Session, limit: int = 10) -> List[schemas.StaffRankingItem]:
    staff_list = get_staff_list(db)
    rankings = []

    for staff in staff_list:
        session_count = db.query(Assignment).filter(
            Assignment.staff_id == staff.id
        ).count()

        rankings.append(schemas.StaffRankingItem(
            staff_id=staff.id,
            staff_name=staff.name,
            staff_type=staff.staff_type.value,
            total_service_hours=staff.total_service_hours,
            star_rating=staff.star_rating,
            review_count=staff.review_count,
            session_count=session_count
        ))

    return sorted(rankings, key=lambda x: (x.star_rating, x.total_service_hours), reverse=True)[:limit]


def create_change_request(db: Session, change_in: schemas.ChangeRequestCreate) -> Tuple[Optional[ChangeRequest], List[str]]:
    session = get_session(db, change_in.session_id)
    if not session:
        return None, ["场次不存在"]

    if session.status == SessionStatus.COMPLETED:
        return None, ["已完成的场次不能申请变更"]

    pending_request = db.query(ChangeRequest).filter(
        ChangeRequest.session_id == change_in.session_id,
        ChangeRequest.status.in_([ChangeStatus.PENDING, ChangeStatus.APPROVED])
    ).first()
    if pending_request:
        return None, ["该场次已有待处理或已通过的变更申请"]

    db_change = ChangeRequest(
        session_id=change_in.session_id,
        requester=change_in.requester,
        change_type=change_in.change_type,
        old_start_time=session.start_time,
        old_end_time=session.end_time,
        old_audience_count=session.audience_count,
        old_guides_needed=session.guides_needed,
        new_start_time=change_in.new_start_time,
        new_end_time=change_in.new_end_time,
        new_audience_count=change_in.new_audience_count,
        new_guides_needed=change_in.new_guides_needed,
        reason=change_in.reason,
        status=ChangeStatus.PENDING
    )
    db.add(db_change)
    db.flush()

    create_change_history(db, schemas.ChangeHistoryCreate(
        session_id=change_in.session_id,
        operator=change_in.requester,
        action="提交变更申请",
        change_request_id=db_change.id,
        change_type=change_in.change_type,
        description=f"提交{change_in.change_type.value}申请，原因：{change_in.reason or '未填写'}"
    ))

    db.commit()
    db.refresh(db_change)
    return db_change, []


def get_change_request(db: Session, change_id: int) -> Optional[ChangeRequest]:
    return db.query(ChangeRequest).options(
        joinedload(ChangeRequest.session),
        joinedload(ChangeRequest.conflicts),
        joinedload(ChangeRequest.reschedule_suggestions)
    ).filter(ChangeRequest.id == change_id).first()


def get_change_request_list(db: Session, skip: int = 0, limit: int = 100,
                            session_id: Optional[int] = None,
                            status: Optional[ChangeStatus] = None,
                            change_type: Optional[ChangeType] = None) -> List[ChangeRequest]:
    query = db.query(ChangeRequest).options(
        joinedload(ChangeRequest.session)
    )
    if session_id:
        query = query.filter(ChangeRequest.session_id == session_id)
    if status:
        query = query.filter(ChangeRequest.status == status)
    if change_type:
        query = query.filter(ChangeRequest.change_type == change_type)
    return query.order_by(ChangeRequest.created_at.desc()).offset(skip).limit(limit).all()


def review_change_request(db: Session, change_id: int,
                          review_in: schemas.ChangeRequestReview) -> Tuple[Optional[ChangeRequest], List[str]]:
    change = get_change_request(db, change_id)
    if not change:
        return None, ["变更申请不存在"]

    if change.status != ChangeStatus.PENDING:
        return None, [f"当前状态为{change.status.value}，无法审核"]

    change.status = review_in.status
    change.reviewer = review_in.reviewer
    change.review_comment = review_in.review_comment
    change.reviewed_at = func.now()

    action = "审核通过" if review_in.status == ChangeStatus.APPROVED else "审核拒绝"
    create_change_history(db, schemas.ChangeHistoryCreate(
        session_id=change.session_id,
        operator=review_in.reviewer,
        action=action,
        change_request_id=change_id,
        change_type=change.change_type,
        description=f"{action}变更申请，审核意见：{review_in.review_comment or '未填写'}"
    ))

    if review_in.status == ChangeStatus.APPROVED:
        conflicts, suggestions = check_conflicts_and_generate_suggestions(db, change)
        if conflicts:
            for conflict in conflicts:
                db.add(conflict)
            for suggestion in suggestions:
                db.add(suggestion)

    db.commit()
    db.refresh(change)
    return change, []


def check_conflicts_and_generate_suggestions(db: Session, change: ChangeRequest) -> Tuple[List[SessionConflict], List[RescheduleSuggestion]]:
    conflicts = []
    suggestions = []

    session = change.session
    if not session:
        return conflicts, suggestions

    new_start = change.new_start_time or session.start_time
    new_end = change.new_end_time or session.end_time
    new_guides_needed = change.new_guides_needed or session.guides_needed

    for assignment in session.assignments:
        if change.new_start_time or change.new_end_time:
            if not is_staff_available(db, assignment.staff_id, new_start, new_end, session.id):
                staff = get_staff(db, assignment.staff_id)
                conflict = SessionConflict(
                    change_request_id=change.id,
                    conflict_type=ConflictType.TIME_OVERLAP,
                    staff_id=assignment.staff_id,
                    assignment_id=assignment.id,
                    message=f"人员 {staff.name if staff else assignment.staff_id} 在新时间段 {new_start} - {new_end} 有其他安排",
                    detail=f"原时间段：{session.start_time} - {session.end_time}，新时间段：{new_start} - {new_end}"
                )
                conflicts.append(conflict)

                replacement = find_replacement_staff(db, session, new_start, new_end, assignment.role)
                if replacement:
                    suggestion = RescheduleSuggestion(
                        change_request_id=change.id,
                        conflict_id=None,
                        staff_id=assignment.staff_id,
                        suggested_staff_id=replacement.id,
                        action="更换人员",
                        priority=1,
                        reason=f"原人员有时间冲突，建议更换为 {replacement.name}（星级：{replacement.star_rating}）"
                    )
                    suggestions.append(suggestion)

    current_guides = sum(1 for a in session.assignments if a.role == AssignmentRole.GUIDE)
    if new_guides_needed > current_guides:
        shortage = new_guides_needed - current_guides
        conflict = SessionConflict(
            change_request_id=change.id,
            conflict_type=ConflictType.STAFF_SHORTAGE,
            message=f"讲解员不足：需求 {new_guides_needed} 人，当前仅 {current_guides} 人，缺口 {shortage} 人",
            detail=f"原需求：{session.guides_needed} 人，新需求：{new_guides_needed} 人"
        )
        conflicts.append(conflict)

        recommended = get_recommended_staff(db, session.id, AssignmentRole.GUIDE, limit=shortage * 2)
        available = [r for r in recommended if r.is_available]
        for rec in available[:shortage]:
            suggestion = RescheduleSuggestion(
                change_request_id=change.id,
                conflict_id=None,
                suggested_staff_id=rec.staff_id,
                action="补充人员",
                priority=2,
                reason=f"需补充讲解员，推荐 {rec.staff_name}（匹配度评分：{rec.score}）"
            )
            suggestions.append(suggestion)

    for i, conflict in enumerate(conflicts):
        for suggestion in suggestions:
            if suggestion.conflict_id is None and i < len(conflicts):
                suggestion.conflict_id = None

    return conflicts, suggestions


def find_replacement_staff(db: Session, session: Session, start_time: datetime,
                           end_time: datetime, role: AssignmentRole) -> Optional[Staff]:
    recommendations = get_recommended_staff(db, session.id, role, limit=20)
    current_staff_ids = [a.staff_id for a in session.assignments]

    for rec in recommendations:
        if rec.staff_id in current_staff_ids:
            continue
        if rec.is_available and is_staff_available(db, rec.staff_id, start_time, end_time, session.id):
            return get_staff(db, rec.staff_id)
    return None


def execute_change_request(db: Session, change_id: int, operator: str) -> schemas.ChangeExecuteResult:
    change = get_change_request(db, change_id)
    if not change:
        return schemas.ChangeExecuteResult(
            success=False,
            message="变更申请不存在",
            errors=["变更申请不存在"]
        )

    if change.status not in [ChangeStatus.APPROVED, ChangeStatus.EXECUTED]:
        return schemas.ChangeExecuteResult(
            success=False,
            message="变更申请未通过审核",
            errors=[f"当前状态为{change.status.value}，无法执行"]
        )

    session = change.session
    if not session:
        return schemas.ChangeExecuteResult(
            success=False,
            message="关联场次不存在",
            errors=["关联场次不存在"]
        )

    errors = []
    applied_suggestions = 0

    old_values = {
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat(),
        "audience_count": session.audience_count,
        "guides_needed": session.guides_needed
    }

    if change.new_start_time:
        session.start_time = change.new_start_time
    if change.new_end_time:
        session.end_time = change.new_end_time
    if change.new_audience_count is not None:
        session.audience_count = change.new_audience_count
    if change.new_guides_needed is not None:
        session.guides_needed = change.new_guides_needed

    pending_conflicts = [c for c in change.conflicts if c.status == RescheduleStatus.PENDING]
    for conflict in pending_conflicts:
        if conflict.conflict_type == ConflictType.TIME_OVERLAP and conflict.assignment_id:
            assignment = db.query(Assignment).filter(Assignment.id == conflict.assignment_id).first()
            if assignment:
                suggestion = next(
                    (s for s in change.reschedule_suggestions
                     if s.staff_id == conflict.staff_id and s.action == "更换人员" and not s.is_applied),
                    None
                )
                if suggestion and suggestion.suggested_staff_id:
                    new_assignment, errs = create_assignment(db, session.id, schemas.AssignmentCreate(
                        staff_id=suggestion.suggested_staff_id,
                        role=assignment.role,
                        is_primary=assignment.is_primary
                    ))
                    if new_assignment:
                        db.delete(assignment)
                        suggestion.is_applied = True
                        suggestion.applied_at = func.now()
                        conflict.status = RescheduleStatus.RESOLVED
                        conflict.resolved_at = func.now()
                        applied_suggestions += 1
                    else:
                        errors.extend(errs)
                        conflict.status = RescheduleStatus.UNRESOLVED
                else:
                    conflict.status = RescheduleStatus.UNRESOLVED
                    errors.append(f"人员冲突未解决：{conflict.message}")

        elif conflict.conflict_type == ConflictType.STAFF_SHORTAGE:
            suggestions_to_apply = [
                s for s in change.reschedule_suggestions
                if s.action == "补充人员" and not s.is_applied
            ]
            for suggestion in suggestions_to_apply:
                if suggestion.suggested_staff_id:
                    new_assignment, errs = create_assignment(db, session.id, schemas.AssignmentCreate(
                        staff_id=suggestion.suggested_staff_id,
                        role=AssignmentRole.GUIDE
                    ))
                    if new_assignment:
                        suggestion.is_applied = True
                        suggestion.applied_at = func.now()
                        applied_suggestions += 1
                    else:
                        errors.extend(errs)

            current_guides = sum(1 for a in session.assignments if a.role == AssignmentRole.GUIDE)
            if current_guides >= session.guides_needed:
                conflict.status = RescheduleStatus.RESOLVED
                conflict.resolved_at = func.now()
            else:
                conflict.status = RescheduleStatus.UNRESOLVED

    if not is_session_fully_staffed(db, session.id):
        session.status = SessionStatus.DRAFT
        errors.append("人员配置仍不足，已自动将状态改回草稿")
    else:
        session.status = SessionStatus.SCHEDULED

    change.status = ChangeStatus.EXECUTED

    new_values = {
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat(),
        "audience_count": session.audience_count,
        "guides_needed": session.guides_needed
    }

    create_change_history(db, schemas.ChangeHistoryCreate(
        session_id=session.id,
        operator=operator,
        action="执行变更",
        change_request_id=change_id,
        change_type=change.change_type,
        old_values=str(old_values),
        new_values=str(new_values),
        description=f"执行{change.change_type.value}，应用了{applied_suggestions}条重排建议"
    ))

    remaining_conflicts = len([c for c in change.conflicts if c.status != RescheduleStatus.RESOLVED])

    # 改期执行后，检查冻结内容版本是否仍覆盖新时间
    if change.new_start_time or change.new_end_time:
        if refresh_confirmation_after_reschedule(db, session):
            errors.append("改期后原内容版本不再覆盖新时间，场次内容需重新确认")

    db.commit()
    db.refresh(change)

    success = remaining_conflicts == 0 and len(errors) == 0
    message = f"变更执行完成，应用{applied_suggestions}条建议" if success else f"变更部分完成，仍有{remaining_conflicts}个冲突待解决"

    return schemas.ChangeExecuteResult(
        success=success,
        message=message,
        applied_suggestions=applied_suggestions,
        remaining_conflicts=remaining_conflicts,
        errors=errors
    )


def apply_suggestion(db: Session, suggestion_id: int, operator: str) -> Tuple[bool, List[str]]:
    suggestion = db.query(RescheduleSuggestion).filter(RescheduleSuggestion.id == suggestion_id).first()
    if not suggestion:
        return False, ["建议不存在"]

    if suggestion.is_applied:
        return False, ["该建议已应用"]

    change = suggestion.change_request
    session = change.session if change else None
    if not session:
        return False, ["关联场次不存在"]

    errors = []

    if suggestion.action == "更换人员" and suggestion.staff_id and suggestion.suggested_staff_id:
        old_assignment = db.query(Assignment).filter(
            Assignment.session_id == session.id,
            Assignment.staff_id == suggestion.staff_id
        ).first()
        if old_assignment:
            new_assignment, errs = create_assignment(db, session.id, schemas.AssignmentCreate(
                staff_id=suggestion.suggested_staff_id,
                role=old_assignment.role,
                is_primary=old_assignment.is_primary
            ))
            if new_assignment:
                db.delete(old_assignment)
                suggestion.is_applied = True
                suggestion.applied_at = func.now()

                if suggestion.conflict_id:
                    conflict = db.query(SessionConflict).filter(SessionConflict.id == suggestion.conflict_id).first()
                    if conflict:
                        conflict.status = RescheduleStatus.RESOLVED
                        conflict.resolved_at = func.now()

                create_change_history(db, schemas.ChangeHistoryCreate(
                    session_id=session.id,
                    operator=operator,
                    action="应用重排建议",
                    change_request_id=change.id,
                    description=f"更换人员：{suggestion.reason}"
                ))
            else:
                errors.extend(errs)
        else:
            errors.append("找不到原排班记录")

    elif suggestion.action == "补充人员" and suggestion.suggested_staff_id:
        new_assignment, errs = create_assignment(db, session.id, schemas.AssignmentCreate(
            staff_id=suggestion.suggested_staff_id,
            role=AssignmentRole.GUIDE
        ))
        if new_assignment:
            suggestion.is_applied = True
            suggestion.applied_at = func.now()

            if suggestion.conflict_id:
                conflict = db.query(SessionConflict).filter(SessionConflict.id == suggestion.conflict_id).first()
                if conflict and is_session_fully_staffed(db, session.id):
                    conflict.status = RescheduleStatus.RESOLVED
                    conflict.resolved_at = func.now()

            create_change_history(db, schemas.ChangeHistoryCreate(
                session_id=session.id,
                operator=operator,
                action="应用重排建议",
                change_request_id=change.id,
                description=f"补充人员：{suggestion.reason}"
            ))
        else:
            errors.extend(errs)

    if is_session_fully_staffed(db, session.id) and session.status == SessionStatus.DRAFT:
        session.status = SessionStatus.SCHEDULED

    if not errors:
        db.commit()
        db.refresh(suggestion)
        return True, []
    else:
        db.rollback()
        return False, errors


def create_change_history(db: Session, history_in: schemas.ChangeHistoryCreate) -> ChangeHistory:
    db_history = ChangeHistory(
        change_request_id=history_in.change_request_id,
        session_id=history_in.session_id,
        operator=history_in.operator,
        action=history_in.action,
        old_values=history_in.old_values,
        new_values=history_in.new_values,
        change_type=history_in.change_type,
        description=history_in.description
    )
    db.add(db_history)
    db.flush()
    return db_history


def get_change_history_list(db: Session, skip: int = 0, limit: int = 100,
                            session_id: Optional[int] = None,
                            change_request_id: Optional[int] = None) -> List[ChangeHistory]:
    query = db.query(ChangeHistory).options(
        joinedload(ChangeHistory.session)
    )
    if session_id:
        query = query.filter(ChangeHistory.session_id == session_id)
    if change_request_id:
        query = query.filter(ChangeHistory.change_request_id == change_request_id)
    return query.order_by(ChangeHistory.created_at.desc()).offset(skip).limit(limit).all()


def get_conflict_list(db: Session, skip: int = 0, limit: int = 100,
                      change_request_id: Optional[int] = None,
                      status: Optional[RescheduleStatus] = None) -> List[SessionConflict]:
    query = db.query(SessionConflict).options(
        joinedload(SessionConflict.staff)
    )
    if change_request_id:
        query = query.filter(SessionConflict.change_request_id == change_request_id)
    if status:
        query = query.filter(SessionConflict.status == status)
    return query.order_by(SessionConflict.created_at.desc()).offset(skip).limit(limit).all()


def get_suggestion_list(db: Session, skip: int = 0, limit: int = 100,
                        change_request_id: Optional[int] = None,
                        is_applied: Optional[bool] = None) -> List[RescheduleSuggestion]:
    query = db.query(RescheduleSuggestion).options(
        joinedload(RescheduleSuggestion.staff),
        joinedload(RescheduleSuggestion.suggested_staff)
    )
    if change_request_id:
        query = query.filter(RescheduleSuggestion.change_request_id == change_request_id)
    if is_applied is not None:
        query = query.filter(RescheduleSuggestion.is_applied == is_applied)
    return query.order_by(RescheduleSuggestion.priority, RescheduleSuggestion.created_at).offset(skip).limit(limit).all()


def get_session_change_stats(db: Session, session_id: Optional[int] = None,
                             skip: int = 0, limit: int = 100) -> List[schemas.SessionChangeStats]:
    query = db.query(
        Session.id,
        Session.title,
        func.count(ChangeRequest.id).label("change_count"),
        func.sum(func.IIF(ChangeRequest.change_type.in_([ChangeType.TIME, ChangeType.BOTH]), 1, 0)).label("time_change_count"),
        func.sum(func.IIF(ChangeRequest.change_type.in_([ChangeType.COUNT, ChangeType.BOTH]), 1, 0)).label("count_change_count"),
        func.max(ChangeRequest.updated_at).label("last_changed_at")
    ).outerjoin(ChangeRequest, Session.id == ChangeRequest.session_id).group_by(Session.id, Session.title)

    if session_id:
        query = query.filter(Session.id == session_id)

    results = query.order_by(func.count(ChangeRequest.id).desc()).offset(skip).limit(limit).all()

    return [
        schemas.SessionChangeStats(
            session_id=r.id,
            session_title=r.title,
            change_count=r.change_count or 0,
            time_change_count=r.time_change_count or 0,
            count_change_count=r.count_change_count or 0,
            last_changed_at=r.last_changed_at
        )
        for r in results
    ]


def get_change_frequency_stats(db: Session, period: str = "month",
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None) -> List[schemas.ChangeFrequencyStats]:
    if not start_date:
        start_date = datetime.now() - timedelta(days=90)
    if not end_date:
        end_date = datetime.now()

    period_format = {
        "day": "%Y-%m-%d",
        "week": "%Y-%W",
        "month": "%Y-%m"
    }.get(period, "%Y-%m")

    results = db.query(
        func.strftime(period_format, ChangeRequest.created_at).label("period"),
        func.count(ChangeRequest.id).label("total_changes"),
        func.sum(func.IIF(ChangeRequest.change_type == ChangeType.TIME, 1, 0)).label("time_changes"),
        func.sum(func.IIF(ChangeRequest.change_type == ChangeType.COUNT, 1, 0)).label("count_changes"),
        func.sum(func.IIF(ChangeRequest.change_type == ChangeType.BOTH, 1, 0)).label("both_changes"),
        func.sum(func.IIF(ChangeRequest.status == ChangeStatus.APPROVED, 1, 0)).label("approved_count"),
        func.sum(func.IIF(ChangeRequest.status == ChangeStatus.REJECTED, 1, 0)).label("rejected_count"),
        func.avg(func.julianday(ChangeRequest.reviewed_at) - func.julianday(ChangeRequest.created_at)).label("avg_resolution_days")
    ).filter(
        ChangeRequest.created_at >= start_date,
        ChangeRequest.created_at <= end_date
    ).group_by(func.strftime(period_format, ChangeRequest.created_at)).order_by("period").all()

    stats = []
    for r in results:
        avg_hours = (r.avg_resolution_days or 0) * 24
        stats.append(schemas.ChangeFrequencyStats(
            period=r.period,
            total_changes=r.total_changes or 0,
            time_changes=r.time_changes or 0,
            count_changes=r.count_changes or 0,
            both_changes=r.both_changes or 0,
            approved_count=r.approved_count or 0,
            rejected_count=r.rejected_count or 0,
            avg_resolution_time_hours=round(avg_hours, 2)
        ))

    return stats


def get_level_badge(db: Session, badge_id: int) -> Optional[LevelBadge]:
    return db.query(LevelBadge).filter(LevelBadge.id == badge_id).first()


def get_level_badge_by_level(db: Session, level: int) -> Optional[LevelBadge]:
    return db.query(LevelBadge).filter(LevelBadge.level == level, LevelBadge.is_active == True).first()


def get_level_badge_list(db: Session, is_active: Optional[bool] = None) -> List[LevelBadge]:
    query = db.query(LevelBadge).order_by(LevelBadge.level)
    if is_active is not None:
        query = query.filter(LevelBadge.is_active == is_active)
    return query.all()


def create_level_badge(db: Session, badge_in: schemas.LevelBadgeCreate) -> LevelBadge:
    db_badge = LevelBadge(**badge_in.model_dump())
    db.add(db_badge)
    db.commit()
    db.refresh(db_badge)
    return db_badge


def update_level_badge(db: Session, badge_id: int, badge_in: schemas.LevelBadgeUpdate) -> Optional[LevelBadge]:
    db_badge = get_level_badge(db, badge_id)
    if not db_badge:
        return None
    update_data = badge_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_badge, field, value)
    db.commit()
    db.refresh(db_badge)
    return db_badge


def get_level_badge_by_points(db: Session, points: int) -> Optional[LevelBadge]:
    return db.query(LevelBadge).filter(
        LevelBadge.is_active == True,
        LevelBadge.min_points <= points,
        or_(LevelBadge.max_points.is_(None), LevelBadge.max_points >= points)
    ).order_by(LevelBadge.level.desc()).first()


def calculate_service_points(duration_hours: float, rating: int) -> int:
    base_points = int(duration_hours * 10)
    rating_bonus = (rating - 3) * 5
    return max(0, base_points + max(0, rating_bonus))


def add_points(db: Session, staff_id: int, points: int, source_type: PointSourceType,
               session_id: Optional[int] = None, review_id: Optional[int] = None,
               description: Optional[str] = None) -> schemas.PointChangeResult:
    staff = get_staff(db, staff_id)
    if not staff:
        return schemas.PointChangeResult(
            success=False,
            staff_id=staff_id,
            points_added=0,
            new_balance=0,
            message="人员不存在"
        )

    old_balance = staff.total_points or 0
    new_balance = old_balance + points
    old_level = staff.current_level or 1

    level_badge = get_level_badge_by_points(db, new_balance)
    new_level = level_badge.level if level_badge else 1
    level_up = new_level > old_level

    db_point = PointRecord(
        staff_id=staff_id,
        session_id=session_id,
        review_id=review_id,
        level_badge_id=level_badge.id if level_badge else None,
        source_type=source_type,
        points=points,
        balance_after=new_balance,
        description=description
    )
    db.add(db_point)

    staff.total_points = new_balance
    staff.current_level = new_level

    new_badge = None
    if level_up and level_badge:
        staff.current_badge_id = level_badge.id

        db.query(StaffBadge).filter(
            StaffBadge.staff_id == staff_id,
            StaffBadge.is_current == True
        ).update({StaffBadge.is_current: False})

        db_staff_badge = StaffBadge(
            staff_id=staff_id,
            level_badge_id=level_badge.id,
            is_current=True
        )
        db.add(db_staff_badge)

        new_badge = schemas.LevelBadge(
            id=level_badge.id,
            level=level_badge.level,
            name=level_badge.name,
            badge_name=level_badge.badge_name,
            min_points=level_badge.min_points,
            max_points=level_badge.max_points,
            description=level_badge.description,
            icon=level_badge.icon,
            is_active=level_badge.is_active,
            created_at=level_badge.created_at
        )

    db.commit()
    db.refresh(staff)

    message = f"成功增加 {points} 积分，当前积分：{new_balance}"
    if level_up:
        message += f"，恭喜升级到 {level_badge.badge_name}！"

    return schemas.PointChangeResult(
        success=True,
        staff_id=staff_id,
        points_added=points,
        new_balance=new_balance,
        level_up=level_up,
        new_level=new_level if level_up else None,
        new_badge=new_badge,
        message=message
    )


def get_point_records(db: Session, staff_id: Optional[int] = None,
                      session_id: Optional[int] = None,
                      start_date: Optional[datetime] = None,
                      end_date: Optional[datetime] = None,
                      skip: int = 0, limit: int = 100) -> List[PointRecord]:
    query = db.query(PointRecord).options(
        joinedload(PointRecord.session),
        joinedload(PointRecord.level_badge)
    )
    if staff_id:
        query = query.filter(PointRecord.staff_id == staff_id)
    if session_id:
        query = query.filter(PointRecord.session_id == session_id)
    if start_date:
        query = query.filter(PointRecord.created_at >= start_date)
    if end_date:
        query = query.filter(PointRecord.created_at <= end_date)
    return query.order_by(PointRecord.created_at.desc()).offset(skip).limit(limit).all()


def get_staff_badges(db: Session, staff_id: int) -> List[StaffBadge]:
    return db.query(StaffBadge).options(
        joinedload(StaffBadge.level_badge)
    ).filter(StaffBadge.staff_id == staff_id).order_by(StaffBadge.earned_at.desc()).all()


def calculate_positive_review_rate(db: Session, staff_id: int,
                                   start_date: datetime, end_date: datetime) -> float:
    reviews = db.query(Review).join(Session).join(Assignment).filter(
        Assignment.staff_id == staff_id,
        Assignment.session_id == Session.id,
        Review.session_id == Session.id,
        Session.status == SessionStatus.COMPLETED,
        Session.end_time >= start_date,
        Session.end_time <= end_date
    ).all()

    if not reviews:
        return 0.0

    positive_count = sum(1 for r in reviews if r.rating >= 4)
    return round(positive_count / len(reviews), 4)


def calculate_monthly_points(db: Session, staff_id: int,
                             year: int, month: int) -> Tuple[int, int]:
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

    records = db.query(PointRecord).filter(
        PointRecord.staff_id == staff_id,
        PointRecord.created_at >= start_date,
        PointRecord.created_at <= end_date,
        PointRecord.source_type != PointSourceType.DEDUCTION
    ).all()

    total_points = sum(r.points for r in records)
    session_count = len(set(r.session_id for r in records if r.session_id))

    return total_points, session_count


def settle_monthly_ranking(db: Session, year: int, month: int,
                           top_n: int = 3) -> schemas.MonthlySettleResult:
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

    existing = db.query(MonthlyRanking).filter(
        MonthlyRanking.year == year,
        MonthlyRanking.month == month
    ).first()
    if existing:
        return schemas.MonthlySettleResult(
            success=False,
            year=year,
            month=month,
            total_staff=0,
            message=f"{year}年{month}月榜单已结算"
        )

    db.query(Staff).filter(
        Staff.is_excellent == True,
        Staff.excellent_until <= datetime.now()
    ).update({Staff.is_excellent: False, Staff.excellent_until: None})

    staff_list = get_staff_list(db, staff_type=StaffType.GUIDE)
    ranking_data = []

    for staff in staff_list:
        monthly_points, session_count = calculate_monthly_points(db, staff.id, year, month)
        if monthly_points == 0 and session_count == 0:
            continue

        positive_rate = calculate_positive_review_rate(db, staff.id, start_date, end_date)
        level_badge = get_level_badge_by_level(db, staff.current_level)

        ranking_data.append({
            "staff_id": staff.id,
            "total_points": monthly_points,
            "positive_review_rate": positive_rate,
            "session_count": session_count,
            "level_badge_id": level_badge.id if level_badge else None
        })

    ranking_data.sort(key=lambda x: (x["total_points"], x["positive_review_rate"]), reverse=True)

    excellent_staff = []
    excellent_until = datetime(year, month + 2, 1) if month < 12 else datetime(year + 1, 2, 1)

    for idx, data in enumerate(ranking_data):
        rank = idx + 1
        is_excellent = rank <= top_n

        db_ranking = MonthlyRanking(
            staff_id=data["staff_id"],
            year=year,
            month=month,
            rank=rank,
            total_points=data["total_points"],
            positive_review_rate=data["positive_review_rate"],
            session_count=data["session_count"],
            is_excellent=is_excellent,
            level_badge_id=data["level_badge_id"]
        )
        db.add(db_ranking)

        if is_excellent:
            excellent_staff.append(data["staff_id"])
            staff = get_staff(db, data["staff_id"])
            if staff:
                staff.is_excellent = True
                staff.excellent_until = excellent_until

    db.commit()

    return schemas.MonthlySettleResult(
        success=True,
        year=year,
        month=month,
        total_staff=len(ranking_data),
        excellent_staff=excellent_staff,
        message=f"已完成{year}年{month}月榜单结算，共{len(ranking_data)}人上榜，{len(excellent_staff)}人被评为优秀讲解员"
    )


def get_monthly_ranking(db: Session, year: int, month: int) -> List[MonthlyRanking]:
    return db.query(MonthlyRanking).options(
        joinedload(MonthlyRanking.staff),
        joinedload(MonthlyRanking.level_badge)
    ).filter(
        MonthlyRanking.year == year,
        MonthlyRanking.month == month
    ).order_by(MonthlyRanking.rank).all()


def get_recommended_staff(db: Session, session_id: int, role: AssignmentRole,
                          limit: int = 10) -> List[schemas.StaffRecommendation]:
    session = get_session(db, session_id)
    if not session:
        return []

    staff_type = StaffType.LECTURER if role == AssignmentRole.LECTURER else StaffType.GUIDE

    qualified_staff = db.query(Staff).options(
        joinedload(Staff.themes),
        joinedload(Staff.venues)
    ).filter(
        Staff.staff_type == staff_type,
        Staff.is_active == True,
        Staff.themes.any(StaffTheme.theme_id == session.theme_id),
        Staff.venues.any(and_(
            StaffVenue.venue_id == session.venue_id,
            StaffVenue.is_certified == True
        ))
    ).all()

    recommendations = []
    for staff in qualified_staff:
        is_available = is_staff_available(db, staff.id, session.start_time, session.end_time, session_id)
        theme_proficiency = next(
            (st.proficiency_level for st in staff.themes if st.theme_id == session.theme_id),
            3
        )
        venue_certified = next(
            (sv.is_certified for sv in staff.venues if sv.venue_id == session.venue_id),
            False
        )

        score = (staff.star_rating * 2) + (theme_proficiency * 0.5) + (staff.current_level * 0.3)
        if is_available:
            score += 3
        if venue_certified:
            score += 1
        if staff.is_excellent:
            score += 5

        recommendations.append(schemas.StaffRecommendation(
            staff_id=staff.id,
            staff_name=staff.name,
            star_rating=staff.star_rating,
            proficiency_level=theme_proficiency,
            is_certified=venue_certified,
            is_available=is_available,
            score=round(score, 2)
        ))

    recommendations.sort(key=lambda x: x.score, reverse=True)
    return recommendations[:limit]


def update_staff_rating_and_points(db: Session, staff_id: int, session: Session):
    reviews = db.query(Review).join(Session).join(Assignment).filter(
        Assignment.staff_id == staff_id,
        Assignment.session_id == Session.id,
        Review.session_id == Session.id
    ).all()

    if not reviews:
        return

    total_rating = sum(r.rating for r in reviews)
    avg_rating = total_rating / len(reviews)

    staff = get_staff(db, staff_id)
    if staff:
        staff.star_rating = round(avg_rating, 1)
        staff.review_count = len(reviews)
        db.commit()


def create_review(db: Session, review_in: schemas.ReviewCreate) -> Review:
    db_review = Review(**review_in.model_dump())
    db.add(db_review)
    db.flush()

    session = db.query(Session).filter(Session.id == review_in.session_id).first()
    if session:
        duration_hours = (session.end_time - session.start_time).total_seconds() / 3600
        assignments = db.query(Assignment).filter(Assignment.session_id == review_in.session_id).all()
        for assignment in assignments:
            staff = get_staff(db, assignment.staff_id)
            if staff and session.status == SessionStatus.COMPLETED:
                staff.total_service_hours += duration_hours
                db.flush()

                service_points = calculate_service_points(duration_hours, review_in.rating)
                if service_points > 0:
                    add_points(
                        db,
                        staff_id=assignment.staff_id,
                        points=service_points,
                        source_type=PointSourceType.SERVICE,
                        session_id=review_in.session_id,
                        review_id=db_review.id,
                        description=f"完成「{session.title}」讲解服务，时长{duration_hours:.1f}小时，评分{review_in.rating}星"
                    )

            update_staff_rating_and_points(db, assignment.staff_id, session)

        if session.status != SessionStatus.COMPLETED:
            session.status = SessionStatus.COMPLETED

    db.commit()
    db.refresh(db_review)
    return db_review


def get_point_trend(db: Session, start_date: Optional[datetime] = None,
                    end_date: Optional[datetime] = None,
                    period: str = "day") -> List[schemas.PointTrendItem]:
    if not start_date:
        start_date = datetime.now() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now()

    period_format = {
        "day": "%Y-%m-%d",
        "week": "%Y-%W",
        "month": "%Y-%m"
    }.get(period, "%Y-%m-%d")

    results = db.query(
        func.strftime(period_format, PointRecord.created_at).label("date"),
        func.sum(PointRecord.points).label("points"),
        func.count(func.distinct(PointRecord.staff_id)).label("staff_count")
    ).filter(
        PointRecord.created_at >= start_date,
        PointRecord.created_at <= end_date,
        PointRecord.source_type != PointSourceType.DEDUCTION
    ).group_by(func.strftime(period_format, PointRecord.created_at)).order_by("date").all()

    return [
        schemas.PointTrendItem(
            date=r.date,
            points=r.points or 0,
            staff_count=r.staff_count or 0
        )
        for r in results
    ]


def get_level_distribution(db: Session) -> List[schemas.LevelDistributionItem]:
    badges = get_level_badge_list(db, is_active=True)
    total_staff = db.query(Staff).filter(
        Staff.is_active == True,
        Staff.staff_type == StaffType.GUIDE
    ).count()

    distribution = []
    for badge in badges:
        staff_count = db.query(Staff).filter(
            Staff.is_active == True,
            Staff.staff_type == StaffType.GUIDE,
            Staff.current_level == badge.level
        ).count()

        percentage = round(staff_count / total_staff * 100, 2) if total_staff > 0 else 0

        distribution.append(schemas.LevelDistributionItem(
            level=badge.level,
            level_name=badge.name,
            badge_name=badge.badge_name,
            staff_count=staff_count,
            percentage=percentage
        ))

    return distribution


def get_staff_point_details(db: Session, year: Optional[int] = None,
                            month: Optional[int] = None,
                            limit: int = 100) -> List[schemas.StaffPointDetail]:
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month

    staff_list = get_staff_list(db, staff_type=StaffType.GUIDE)
    details = []

    for staff in staff_list:
        session_count = db.query(Assignment).filter(
            Assignment.staff_id == staff.id
        ).count()

        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)

        positive_rate = calculate_positive_review_rate(db, staff.id, start_date, end_date)
        monthly_points, _ = calculate_monthly_points(db, staff.id, year, month)

        level_badge = get_level_badge_by_level(db, staff.current_level)

        details.append(schemas.StaffPointDetail(
            staff_id=staff.id,
            staff_name=staff.name,
            staff_type=staff.staff_type.value,
            total_service_hours=staff.total_service_hours,
            star_rating=staff.star_rating,
            review_count=staff.review_count,
            session_count=session_count,
            total_points=staff.total_points or 0,
            current_level=staff.current_level or 1,
            current_badge_name=level_badge.badge_name if level_badge else None,
            is_excellent=staff.is_excellent or False,
            positive_review_rate=positive_rate,
            monthly_points=monthly_points
        ))

    details.sort(key=lambda x: (x.monthly_points, x.positive_review_rate), reverse=True)
    return details[:limit]


def adjust_staff_points(db: Session, staff_id: int, points: int,
                        source_type: PointSourceType,
                        description: str) -> schemas.PointChangeResult:
    if points >= 0:
        return add_points(db, staff_id, points, source_type, description=description)
    else:
        return add_points(db, staff_id, points, PointSourceType.DEDUCTION, description=description)


# ---------------------------------------------------------------------------
# 主题内容版本化：版本发布、场次冻结确认、紧急勘误链、版本撤回、讲解员替班
# ---------------------------------------------------------------------------

import hashlib
import json as _json

from app.models import (
    ThemeContentVersion, ContentVersionItem, SessionContentConfirmation,
    ContentErratum, ErratumAcknowledgement, GuideSubstitution,
    ContentVersionStatus, ErratumStatus, ContentConfirmationStatus,
    SubstitutionStatus,
)


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    """统一去掉时区，避免 SQLite 中 naive/aware 时间比较报错。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _segment_hash(segment_key: str, title: str, body: str) -> str:
    payload = _json.dumps(
        {"segment_key": segment_key, "title": title, "body": body},
        ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_checklist(items: List[ContentVersionItem]) -> Tuple[list, str, str]:
    """由版本清单项构造冻结快照：结构化清单、规范化 JSON、整体校验值。"""
    data = [
        {
            "item_id": item.id,
            "segment_key": item.segment_key,
            "title": item.title,
            "body": item.body,
            "is_required": item.is_required,
            "content_hash": item.content_hash,
            "sort_order": item.sort_order,
        }
        for item in sorted(items, key=lambda x: (x.sort_order, x.id))
    ]
    text = _json.dumps(data, ensure_ascii=False, sort_keys=True)
    overall = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return data, text, overall


def _load_checklist(frozen_json: str) -> list:
    try:
        return _json.loads(frozen_json)
    except (ValueError, TypeError):
        return []


def get_content_version(db: Session, version_id: int) -> Optional[ThemeContentVersion]:
    return db.query(ThemeContentVersion).options(
        joinedload(ThemeContentVersion.items),
        joinedload(ThemeContentVersion.theme),
        joinedload(ThemeContentVersion.errata),
    ).filter(ThemeContentVersion.id == version_id).first()


def list_content_versions(db: Session, theme_id: int,
                          status: Optional[ContentVersionStatus] = None) -> List[ThemeContentVersion]:
    query = db.query(ThemeContentVersion).options(
        joinedload(ThemeContentVersion.items)
    ).filter(ThemeContentVersion.theme_id == theme_id)
    if status:
        query = query.filter(ThemeContentVersion.status == status)
    return query.order_by(ThemeContentVersion.version_number.desc()).all()


def _next_version_number(db: Session, theme_id: int) -> int:
    last = db.query(func.max(ThemeContentVersion.version_number)).filter(
        ThemeContentVersion.theme_id == theme_id
    ).scalar()
    return (last or 0) + 1


def create_content_version(db: Session, theme_id: int,
                           version_in: schemas.ContentVersionCreate
                           ) -> Tuple[Optional[ThemeContentVersion], List[str]]:
    theme = get_theme(db, theme_id)
    if not theme:
        return None, ["主题不存在"]
    if version_in.age_min > version_in.age_max:
        return None, ["适用年龄下限不能大于上限"]
    if version_in.effective_to and _naive(version_in.effective_to) <= _naive(version_in.effective_from):
        return None, ["生效结束时间必须晚于生效开始时间"]

    version = ThemeContentVersion(
        theme_id=theme_id,
        version_number=_next_version_number(db, theme_id),
        status=ContentVersionStatus.DRAFT,
        title=version_in.title,
        age_min=version_in.age_min,
        age_max=version_in.age_max,
        content_text=version_in.content_text,
        required_segments="[]",
        sensitivity_notes=version_in.sensitivity_notes,
        effective_from=version_in.effective_from,
        effective_to=version_in.effective_to,
        created_by=version_in.created_by,
    )
    db.add(version)
    db.flush()

    keys = set()
    for seg in version_in.required_segments:
        if seg.segment_key in keys:
            db.rollback()
            return None, [f"段落标识重复：{seg.segment_key}"]
        keys.add(seg.segment_key)
        db.add(ContentVersionItem(
            version_id=version.id,
            segment_key=seg.segment_key,
            title=seg.title,
            body=seg.body,
            is_required=seg.is_required,
            content_hash=_segment_hash(seg.segment_key, seg.title, seg.body),
            sort_order=seg.sort_order,
        ))
    version.required_segments = _json.dumps(sorted(keys), ensure_ascii=False)

    db.commit()
    db.refresh(version)
    return get_content_version(db, version.id), []


def update_content_version(db: Session, version_id: int,
                           version_in: schemas.ContentVersionUpdate
                           ) -> Tuple[Optional[ThemeContentVersion], List[str]]:
    version = get_content_version(db, version_id)
    if not version:
        return None, ["内容版本不存在"]
    if version.status != ContentVersionStatus.DRAFT:
        return None, [f"版本当前为{version.status.value}状态，内容已冻结，不能修改；请发布新版本或提交勘误"]

    data = version_in.model_dump(exclude_unset=True)
    if "required_segments" in data:
        segments = data.pop("required_segments")
    else:
        segments = None

    for field, value in data.items():
        setattr(version, field, value)

    age_min = version.age_min
    age_max = version.age_max
    if age_min > age_max:
        db.rollback()
        return None, ["适用年龄下限不能大于上限"]
    eff_from = _naive(version.effective_from)
    eff_to = _naive(version.effective_to)
    if eff_to and eff_to <= eff_from:
        db.rollback()
        return None, ["生效结束时间必须晚于生效开始时间"]

    if segments is not None:
        db.query(ContentVersionItem).filter(
            ContentVersionItem.version_id == version_id
        ).delete()
        keys = set()
        for seg in segments:
            if seg["segment_key"] in keys:
                db.rollback()
                return None, [f"段落标识重复：{seg['segment_key']}"]
            keys.add(seg["segment_key"])
            db.add(ContentVersionItem(
                version_id=version_id,
                segment_key=seg["segment_key"],
                title=seg["title"],
                body=seg["body"],
                is_required=seg["is_required"],
                content_hash=_segment_hash(seg["segment_key"], seg["title"], seg["body"]),
                sort_order=seg["sort_order"],
            ))
        version.required_segments = _json.dumps(sorted(keys), ensure_ascii=False)

    db.commit()
    return get_content_version(db, version_id), []


def publish_content_version(db: Session, version_id: int
                            ) -> Tuple[Optional[ThemeContentVersion], List[str]]:
    version = get_content_version(db, version_id)
    if not version:
        return None, ["内容版本不存在"]
    if version.status != ContentVersionStatus.DRAFT:
        return None, [f"仅草稿版本可发布，当前为{version.status.value}状态"]
    required = [i for i in version.items if i.is_required]
    if not required:
        return None, ["发布前至少需要一个必讲段落"]
    if not version.content_text or not version.content_text.strip():
        return None, ["讲解词正文不能为空"]

    version.status = ContentVersionStatus.PUBLISHED
    version.published_at = func.now()
    db.commit()
    return get_content_version(db, version_id), []


def _version_covers(version: ThemeContentVersion, at: Optional[datetime] = None) -> bool:
    """版本在指定时刻（默认现在）是否处于已发布且生效的区间内。"""
    if version.status != ContentVersionStatus.PUBLISHED:
        return False
    moment = _naive(at) or datetime.now()
    if _naive(version.effective_from) > moment:
        return False
    if version.effective_to and _naive(version.effective_to) < moment:
        return False
    return True


def get_current_content_version(db: Session, theme_id: int,
                                at: Optional[datetime] = None) -> Optional[ThemeContentVersion]:
    """主题当前可用于新场次确认的内容版本（生效区间内、版本号最新）。"""
    versions = db.query(ThemeContentVersion).options(
        joinedload(ThemeContentVersion.items)
    ).filter(ThemeContentVersion.theme_id == theme_id).all()
    covering = [v for v in versions if _version_covers(v, at)]
    if not covering:
        return None
    return max(covering, key=lambda v: v.version_number)


def withdraw_content_version(db: Session, version_id: int, reason: str,
                             operator: str) -> Tuple[Optional[ThemeContentVersion], int, List[str]]:
    """撤回已发布版本。

    引用该版本且尚未开始的场次进入“待重新确认”；已结束/已取消场次的
    冻结证据不受影响。返回 (版本, 受影响待确认场次数, 错误)。
    """
    version = get_content_version(db, version_id)
    if not version:
        return None, 0, ["内容版本不存在"]
    if version.status != ContentVersionStatus.PUBLISHED:
        return None, 0, [f"仅已发布版本可撤回，当前为{version.status.value}状态"]

    version.status = ContentVersionStatus.WITHDRAWN
    version.withdrawn_at = func.now()
    version.withdraw_reason = reason

    affected = 0
    confirmations = db.query(SessionContentConfirmation).options(
        joinedload(SessionContentConfirmation.session)
    ).filter(
        SessionContentConfirmation.content_version_id == version_id,
        SessionContentConfirmation.status.in_([
            ContentConfirmationStatus.CONFIRMED,
            ContentConfirmationStatus.PENDING_RECONFIRM,
        ])
    ).all()
    now = datetime.now()
    for conf in confirmations:
        sess = conf.session
        if sess and sess.status not in (SessionStatus.COMPLETED, SessionStatus.CANCELLED) \
                and _naive(sess.start_time) > now:
            if conf.status != ContentConfirmationStatus.PENDING_RECONFIRM:
                conf.status = ContentConfirmationStatus.PENDING_RECONFIRM
                conf.reconfirm_reason = f"内容版本 v{version.version_number} 已被馆方撤回（{operator}：{reason}）"
                affected += 1

    db.commit()
    return get_content_version(db, version_id), affected, []


# ---- 紧急勘误 ----

def create_erratum(db: Session, version_id: int, erratum_in: schemas.ErratumCreate
                   ) -> Tuple[Optional[ContentErratum], int, List[str]]:
    """对已发布版本追加紧急勘误，并要求未开始场次重新确认。

    勘误只追加、不改写原始版本与任何历史快照。返回 (勘误, 待重新确认场次数, 错误)。
    """
    version = get_content_version(db, version_id)
    if not version:
        return None, 0, ["内容版本不存在"]
    if version.status not in (ContentVersionStatus.PUBLISHED, ContentVersionStatus.WITHDRAWN):
        return None, 0, ["仅已发布（含已撤回留痕）的版本可追加勘误"]

    if erratum_in.target_item_id is not None:
        item = db.query(ContentVersionItem).filter(
            ContentVersionItem.id == erratum_in.target_item_id,
            ContentVersionItem.version_id == version_id
        ).first()
        if not item:
            return None, 0, ["勘误目标段落不存在或不属于该版本"]

    superseded = None
    if erratum_in.supersedes_erratum_id is not None:
        superseded = db.query(ContentErratum).filter(
            ContentErratum.id == erratum_in.supersedes_erratum_id,
            ContentErratum.content_version_id == version_id
        ).first()
        if not superseded:
            return None, 0, ["被替代的勘误不存在或不属于该版本"]

    last_no = db.query(func.max(ContentErratum.erratum_no)).filter(
        ContentErratum.content_version_id == version_id
    ).scalar()
    erratum = ContentErratum(
        content_version_id=version_id,
        erratum_no=(last_no or 0) + 1,
        target_item_id=erratum_in.target_item_id,
        severity=erratum_in.severity,
        old_text=erratum_in.old_text,
        new_text=erratum_in.new_text,
        reason=erratum_in.reason,
        status=ErratumStatus.ISSUED,
        issued_by=erratum_in.issued_by,
        supersedes_erratum_id=erratum_in.supersedes_erratum_id,
    )
    db.add(erratum)
    if superseded is not None:
        superseded.status = ErratumStatus.SUPERSEDED
    db.flush()

    affected = 0
    if erratum_in.require_reconfirm:
        confirmations = db.query(SessionContentConfirmation).options(
            joinedload(SessionContentConfirmation.session)
        ).filter(
            SessionContentConfirmation.content_version_id == version_id,
            SessionContentConfirmation.status.in_([
                ContentConfirmationStatus.CONFIRMED,
                ContentConfirmationStatus.PENDING_RECONFIRM,
            ])
        ).all()
        now = datetime.now()
        for conf in confirmations:
            sess = conf.session
            if not sess or sess.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
                continue
            if _naive(sess.start_time) <= now:
                continue
            exists = db.query(ErratumAcknowledgement).filter(
                ErratumAcknowledgement.erratum_id == erratum.id,
                ErratumAcknowledgement.confirmation_id == conf.id
            ).first()
            if not exists:
                db.add(ErratumAcknowledgement(
                    erratum_id=erratum.id,
                    confirmation_id=conf.id,
                ))
            if conf.status == ContentConfirmationStatus.CONFIRMED:
                conf.status = ContentConfirmationStatus.PENDING_RECONFIRM
                reason = f"紧急勘误 #{erratum.erratum_no}（{erratum.severity}）要求重新确认内容版本"
                conf.reconfirm_reason = reason
                affected += 1

    db.commit()
    db.refresh(erratum)
    return erratum, affected, []


def list_errata(db: Session, version_id: int,
                status: Optional[ErratumStatus] = None) -> List[ContentErratum]:
    query = db.query(ContentErratum).filter(ContentErratum.content_version_id == version_id)
    if status:
        query = query.filter(ContentErratum.status == status)
    return query.order_by(ContentErratum.erratum_no).all()


# ---- 场次内容确认（冻结证据） ----

def get_session_confirmation(db: Session, session_id: int,
                             only_active: bool = True
                             ) -> Optional[SessionContentConfirmation]:
    query = db.query(SessionContentConfirmation).options(
        joinedload(SessionContentConfirmation.session),
        joinedload(SessionContentConfirmation.version).joinedload(ThemeContentVersion.items),
    ).filter(SessionContentConfirmation.session_id == session_id)
    if only_active:
        query = query.filter(SessionContentConfirmation.status !=
                             ContentConfirmationStatus.SUPERSEDED)
    return query.order_by(SessionContentConfirmation.id.desc()).first()


def list_session_confirmations(db: Session, session_id: int) -> List[SessionContentConfirmation]:
    return db.query(SessionContentConfirmation).options(
        joinedload(SessionContentConfirmation.version)
    ).filter(SessionContentConfirmation.session_id == session_id
    ).order_by(SessionContentConfirmation.id.desc()).all()


def _freeze_confirmation(db: Session, session: Session, version: ThemeContentVersion,
                         confirmed_by: Optional[str], reason: Optional[str] = None
                         ) -> SessionContentConfirmation:
    _, checklist_json, overall_hash = _build_checklist(version.items)
    conf = SessionContentConfirmation(
        session_id=session.id,
        content_version_id=version.id,
        status=ContentConfirmationStatus.CONFIRMED,
        frozen_age_min=version.age_min,
        frozen_age_max=version.age_max,
        frozen_checklist=checklist_json,
        content_hash=overall_hash,
        confirmed_by=confirmed_by,
        reconfirm_reason=reason,
    )
    db.add(conf)
    db.flush()
    return conf


def confirm_session_content(db: Session, session_id: int,
                            confirmed_by: Optional[str] = None,
                            version_id: Optional[int] = None
                            ) -> Tuple[Optional[SessionContentConfirmation], List[str]]:
    """学校确认内容：冻结一份可核验的内容清单。

    已存在未终结的确认时必须走重新确认流程；已结束场次不允许再确认。
    """
    session = get_session(db, session_id)
    if not session:
        return None, ["场次不存在"]
    if session.status == SessionStatus.COMPLETED:
        return None, ["已结束场次不能再确认或变更内容，冻结证据已归档"]

    existing = get_session_confirmation(db, session_id)
    if existing:
        return None, [f"场次已确认内容版本 v{existing.version.version_number}，"
                      f"当前状态为{existing.status.value}，请走重新确认接口"]

    if version_id is not None:
        version = get_content_version(db, version_id)
        if not version or version.theme_id != session.theme_id:
            return None, ["指定的内容版本不存在或不属于该场次主题"]
        if version.status != ContentVersionStatus.PUBLISHED:
            return None, [f"内容版本当前为{version.status.value}状态，不能用于确认"]
    else:
        version = get_current_content_version(db, session.theme_id,
                                              at=_naive(session.start_time))
        if not version:
            return None, ["该主题当前没有生效的内容版本，无法确认"]

    conf = _freeze_confirmation(db, session, version, confirmed_by)
    db.commit()
    db.refresh(conf)
    return get_session_confirmation(db, session_id, only_active=False), []


def reconfirm_session_content(db: Session, session_id: int, operator: str,
                              target_version_id: Optional[int] = None,
                              reason: Optional[str] = None
                              ) -> Tuple[Optional[SessionContentConfirmation], List[str]]:
    """学校接受（重新确认）一个内容版本。

    旧确认转为“已被新版本替代”并保留冻结证据；新确认冻结新版本清单。
    已结束场次一律拒绝，确保历史证据不被改写。
    """
    session = get_session(db, session_id)
    if not session:
        return None, ["场次不存在"]
    if session.status == SessionStatus.COMPLETED:
        return None, ["已结束场次不能重新确认，历史冻结证据不可改写"]

    old = get_session_confirmation(db, session_id)
    if not old:
        return None, ["场次尚无内容确认，请先调用确认接口"]

    if target_version_id is not None:
        new_version = get_content_version(db, target_version_id)
        if not new_version or new_version.theme_id != session.theme_id:
            return None, ["目标内容版本不存在或不属于该场次主题"]
    else:
        new_version = get_current_content_version(db, session.theme_id,
                                                  at=_naive(session.start_time))
    if not new_version:
        return None, ["该主题当前没有可用的内容版本"]
    if new_version.status != ContentVersionStatus.PUBLISHED:
        return None, [f"目标版本当前为{new_version.status.value}状态，不能用于确认"]
    if new_version.id == old.content_version_id and \
            old.status == ContentConfirmationStatus.CONFIRMED:
        return None, [f"场次已确认版本 v{new_version.version_number}，无需重新确认"]

    new_conf = _freeze_confirmation(
        db, session, new_version, operator,
        reason or f"由版本 v{old.version.version_number} 重新确认至 v{new_version.version_number}"
    )

    old.status = ContentConfirmationStatus.SUPERSEDED
    old.superseded_by_id = new_conf.id
    old.school_response_at = func.now()
    # 关闭旧确认上未处理的勘误送达，保证勘误链有确定结局
    for ack in old.errata_acknowledgements:
        if ack.acknowledged_at is None:
            ack.acknowledged_at = func.now()
            ack.acknowledged_by = operator
            ack.note = f"已重新确认内容版本 v{new_version.version_number}"

    db.commit()
    return get_session_confirmation(db, session_id), []


def reject_new_version(db: Session, session_id: int, rejected_by: str,
                       reason: Optional[str] = None
                       ) -> Tuple[Optional[SessionContentConfirmation], List[str]]:
    """学校拒绝新版本：场次仍锁定在原冻结版本，状态转为“学校拒绝新版本”。"""
    session = get_session(db, session_id)
    if not session:
        return None, ["场次不存在"]
    if session.status == SessionStatus.COMPLETED:
        return None, ["已结束场次的内容确认状态不能变更"]

    conf = get_session_confirmation(db, session_id)
    if not conf:
        return None, ["场次尚无内容确认"]
    if conf.status != ContentConfirmationStatus.PENDING_RECONFIRM:
        return None, [f"仅“待重新确认”状态可拒绝新版本，当前为{conf.status.value}状态"]

    conf.status = ContentConfirmationStatus.SCHOOL_REJECTED
    conf.school_response_at = func.now()
    conf.reconfirm_reason = (conf.reconfirm_reason or "") + \
        f"；学校{rejected_by}拒绝重新确认" + (f"：{reason}" if reason else "")
    db.commit()
    db.refresh(conf)
    return conf, []


def retain_confirmed_version(db: Session, session_id: int, operator: str
                             ) -> Tuple[Optional[SessionContentConfirmation], List[str]]:
    """学校拒绝新版本后，馆方确认仍按原冻结版本执行，状态恢复“已确认”。"""
    conf = get_session_confirmation(db, session_id)
    if not conf:
        return None, ["场次尚无内容确认"]
    if conf.status != ContentConfirmationStatus.SCHOOL_REJECTED:
        return None, [f"仅“学校拒绝新版本”状态可恢复确认，当前为{conf.status.value}状态"]
    # 若锁定版本已撤回，则不能恢复，必须改确认其他版本
    version = get_content_version(db, conf.content_version_id)
    if not version or version.status != ContentVersionStatus.PUBLISHED:
        return None, ["原冻结版本已撤回，不能继续沿用，请重新确认其他版本"]
    conf.status = ContentConfirmationStatus.CONFIRMED
    conf.reconfirm_reason = (conf.reconfirm_reason or "") + f"；{operator} 核定仍按原版本执行"
    db.commit()
    db.refresh(conf)
    return conf, []


def acknowledge_erratum(db: Session, session_id: int, erratum_id: int,
                        acknowledged_by: str, note: Optional[str] = None
                        ) -> Tuple[Optional[ErratumAcknowledgement], List[str]]:
    """学校/馆方知悉某条勘误（仅记录知悉，不改写冻结证据）。"""
    conf = get_session_confirmation(db, session_id)
    if not conf:
        return None, ["场次尚无内容确认"]
    erratum = db.query(ContentErratum).filter(ContentErratum.id == erratum_id).first()
    if not erratum or erratum.content_version_id != conf.content_version_id:
        return None, ["勘误不存在或不属于该场次冻结的内容版本"]

    ack = db.query(ErratumAcknowledgement).filter(
        ErratumAcknowledgement.erratum_id == erratum_id,
        ErratumAcknowledgement.confirmation_id == conf.id
    ).first()
    if not ack:
        ack = ErratumAcknowledgement(
            erratum_id=erratum_id,
            confirmation_id=conf.id,
        )
        db.add(ack)
    ack.acknowledged_at = func.now()
    ack.acknowledged_by = acknowledged_by
    ack.note = note
    db.commit()
    db.refresh(ack)
    return ack, []


def get_erratum_chain(db: Session, confirmation: SessionContentConfirmation) -> List[dict]:
    """还原某次冻结确认实际被送达的勘误链及本场次的知悉情况。

    只包含已送达该确认的勘误（版本上存在但未送达该场次的不计入，
    尤其已结束场次在结束后新发的勘误不得附着为其证据的一部分）。
    """
    acks = {a.erratum_id: a for a in confirmation.errata_acknowledgements}
    if not acks:
        return []
    errata = db.query(ContentErratum).filter(
        ContentErratum.content_version_id == confirmation.content_version_id,
        ContentErratum.id.in_(list(acks.keys()))
    ).order_by(ContentErratum.erratum_no).all()
    # 反向找出“被哪条勘误替代”（替代勘误本身可能未送达，仍需给出链条指向）
    all_version_errata = db.query(ContentErratum).filter(
        ContentErratum.content_version_id == confirmation.content_version_id
    ).all()
    superseded_by = {
        e.supersedes_erratum_id: e.id
        for e in all_version_errata if e.supersedes_erratum_id is not None
    }
    chain = []
    for erratum in errata:
        ack = acks.get(erratum.id)
        chain.append({
            "erratum": erratum,
            "superseded_by_id": superseded_by.get(erratum.id),
            "delivered_at": ack.delivered_at if ack else None,
            "acknowledged_at": ack.acknowledged_at if ack else None,
            "acknowledged_by": ack.acknowledged_by if ack else None,
            "note": ack.note if ack else None,
            "status": erratum.status.value,
        })
    return chain


def verify_frozen_checklist(db: Session, confirmation_id: int) -> Tuple[bool, List[str]]:
    """核验冻结快照是否被篡改：快照整体自证 + 逐条段落校验值。

    快照在确认时独立固化，不依赖版本当前状态，因此历史版本被撤回、
    被新版本替代都不影响该证据的自证。
    """
    conf = db.query(SessionContentConfirmation).filter(
        SessionContentConfirmation.id == confirmation_id
    ).first()
    if not conf:
        return False, ["确认记录不存在"]
    frozen = _load_checklist(conf.frozen_checklist)
    errors = []
    # 快照整体自证：用快照内 JSON 重算校验值
    self_text = _json.dumps(frozen, ensure_ascii=False, sort_keys=True)
    self_hash = hashlib.sha256(self_text.encode("utf-8")).hexdigest()
    if self_hash != conf.content_hash:
        errors.append("冻结快照整体校验值不匹配，快照可能被篡改")
    for entry in frozen:
        if _segment_hash(entry["segment_key"], entry["title"], entry["body"]) != entry["content_hash"]:
            errors.append(f"段落 {entry.get('segment_key')} 的逐条校验值不匹配")
    return not errors, errors


def refresh_confirmation_after_reschedule(db: Session, session: Session) -> bool:
    """场次改期后校验冻结版本是否仍覆盖新时间，不覆盖则要求重新确认。

    返回是否将场次置为“待重新确认”。
    """
    conf = get_session_confirmation(db, session.id)
    if not conf or conf.status != ContentConfirmationStatus.CONFIRMED:
        return False
    if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
        return False
    version = get_content_version(db, conf.content_version_id)
    new_start = _naive(session.start_time)
    covers = bool(version) and version.status == ContentVersionStatus.PUBLISHED and \
        _naive(version.effective_from) <= new_start and \
        (version.effective_to is None or _naive(version.effective_to) >= new_start)
    if not covers:
        conf.status = ContentConfirmationStatus.PENDING_RECONFIRM
        vno = version.version_number if version else conf.content_version_id
        conf.reconfirm_reason = f"场次改期至 {new_start:%Y-%m-%d %H:%M}，原内容版本 v{vno} 不再覆盖该时间，需重新确认"
        return True
    return False


# ---- 讲解员临时替换 ----

def list_substitutions(db: Session, session_id: Optional[int] = None
                       ) -> List[GuideSubstitution]:
    query = db.query(GuideSubstitution).options(
        joinedload(GuideSubstitution.original_staff),
        joinedload(GuideSubstitution.substitute_staff),
    )
    if session_id is not None:
        query = query.filter(GuideSubstitution.session_id == session_id)
    return query.order_by(GuideSubstitution.requested_at.desc()).all()


def get_substitution(db: Session, substitution_id: int) -> Optional[GuideSubstitution]:
    return db.query(GuideSubstitution).options(
        joinedload(GuideSubstitution.original_staff),
        joinedload(GuideSubstitution.substitute_staff),
        joinedload(GuideSubstitution.assignment),
    ).filter(GuideSubstitution.id == substitution_id).first()


def request_substitution(db: Session, session_id: int,
                         sub_in: schemas.SubstitutionCreate
                         ) -> Tuple[Optional[GuideSubstitution], List[str]]:
    """登记讲解员临时替换需求（待替班）。不改动现有排班与内容冻结证据。"""
    session = get_session(db, session_id)
    if not session:
        return None, ["场次不存在"]
    if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
        return None, [f"{session.status.value}场次不能登记替班"]

    assignment = db.query(Assignment).filter(
        Assignment.id == sub_in.assignment_id,
        Assignment.session_id == session_id
    ).first()
    if not assignment:
        return None, ["排班记录不存在或不属于该场次"]

    active = db.query(GuideSubstitution).filter(
        GuideSubstitution.assignment_id == assignment.id,
        GuideSubstitution.status.in_([SubstitutionStatus.REQUESTED,
                                      SubstitutionStatus.SUBSTITUTED])
    ).first()
    if active:
        return None, [f"该排班已有进行中的替班记录（状态：{active.status.value}），请先闭环"]

    sub = GuideSubstitution(
        session_id=session_id,
        assignment_id=assignment.id,
        original_staff_id=assignment.staff_id,
        substitute_staff_id=sub_in.substitute_staff_id,
        role=assignment.role,
        reason=sub_in.reason,
        status=SubstitutionStatus.REQUESTED,
        requested_by=sub_in.requested_by,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return get_substitution(db, sub.id), []


def _assignment_to(db: Session, assignment: Assignment, staff_id: int) -> List[str]:
    """把某条排班改派给另一名人员，返回资格/冲突错误。"""
    session = assignment.session
    qualified, errs = is_staff_qualified(db, staff_id, session.theme_id,
                                         session.venue_id, assignment.role)
    if not qualified:
        return errs
    if not is_staff_available(db, staff_id, session.start_time, session.end_time, session.id):
        staff = get_staff(db, staff_id)
        return [f"替班人员 {staff.name if staff else staff_id} 在该时间段已有安排"]
    assignment.staff_id = staff_id
    return []


def substitution_arrive(db: Session, substitution_id: int, substitute_staff_id: int,
                        operator: str) -> Tuple[Optional[GuideSubstitution], List[str]]:
    """替班讲解员到岗：校验资格与时间后改派排班，状态置“替班已到岗”。"""
    sub = get_substitution(db, substitution_id)
    if not sub:
        return None, ["替班记录不存在"]
    if sub.status != SubstitutionStatus.REQUESTED:
        return None, [f"仅待替班记录可报到岗，当前为{sub.status.value}状态"]
    if substitute_staff_id == sub.original_staff_id:
        return None, ["替班人员不能与原讲解员相同"]

    errs = _assignment_to(db, sub.assignment, substitute_staff_id)
    if errs:
        return None, errs

    sub.substitute_staff_id = substitute_staff_id
    sub.status = SubstitutionStatus.SUBSTITUTED
    sub.substituted_at = func.now()
    sub.operator = operator
    db.commit()
    return get_substitution(db, substitution_id), []


def substitution_restore(db: Session, substitution_id: int, operator: str
                         ) -> Tuple[Optional[GuideSubstitution], List[str]]:
    """原讲解员回归：排班改回原人员，状态置“原讲解员已回归”。"""
    sub = get_substitution(db, substitution_id)
    if not sub:
        return None, ["替班记录不存在"]
    if sub.status != SubstitutionStatus.SUBSTITUTED:
        return None, [f"仅替班已到岗记录可回归，当前为{sub.status.value}状态"]

    errs = _assignment_to(db, sub.assignment, sub.original_staff_id)
    if errs:
        return None, errs

    sub.assignment.staff_id = sub.original_staff_id
    sub.status = SubstitutionStatus.RESTORED
    sub.restored_at = func.now()
    sub.operator = operator
    db.commit()
    return get_substitution(db, substitution_id), []


def substitution_cancel(db: Session, substitution_id: int, operator: str
                        ) -> Tuple[Optional[GuideSubstitution], List[str]]:
    """取消尚未到岗的替班需求。"""
    sub = get_substitution(db, substitution_id)
    if not sub:
        return None, ["替班记录不存在"]
    if sub.status != SubstitutionStatus.REQUESTED:
        return None, [f"仅待替班记录可取消，当前为{sub.status.value}状态"]
    sub.status = SubstitutionStatus.CANCELLED
    sub.cancelled_at = func.now()
    sub.operator = operator
    db.commit()
    return get_substitution(db, substitution_id), []
