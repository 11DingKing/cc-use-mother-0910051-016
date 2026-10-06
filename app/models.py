from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class StaffType(str, enum.Enum):
    GUIDE = "讲解员"
    LECTURER = "讲师"


class SessionType(str, enum.Enum):
    RESEARCH = "研学实践"
    LECTURE = "专题讲座"


class SessionStatus(str, enum.Enum):
    DRAFT = "草稿"
    SCHEDULED = "已排定"
    COMPLETED = "已完成"
    CANCELLED = "已取消"


class AssignmentRole(str, enum.Enum):
    GUIDE = "讲解员"
    LECTURER = "主讲"


class AudienceType(str, enum.Enum):
    SCHOOL = "学校"
    PUBLIC = "公众"


class WarningType(str, enum.Enum):
    STAFF_SHORTAGE = "人员不足"
    OVERLOAD = "人员过载"


class ChangeType(str, enum.Enum):
    TIME = "时间变更"
    COUNT = "人数变更"
    BOTH = "时间和人数变更"
    OTHER = "其他变更"


class ChangeStatus(str, enum.Enum):
    PENDING = "待审核"
    APPROVED = "已通过"
    REJECTED = "已拒绝"
    EXECUTED = "已执行"
    CANCELLED = "已取消"


class ConflictType(str, enum.Enum):
    TIME_OVERLAP = "时间冲突"
    STAFF_SHORTAGE = "人员不足"
    QUALIFICATION = "资质不符"


class RescheduleStatus(str, enum.Enum):
    PENDING = "待处理"
    IN_PROGRESS = "处理中"
    RESOLVED = "已解决"
    UNRESOLVED = "未解决"


class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    staff_type = Column(Enum(StaffType), nullable=False)
    phone = Column(String(20))
    email = Column(String(100))
    total_service_hours = Column(Float, default=0.0)
    star_rating = Column(Float, default=3.0)
    review_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    total_points = Column(Integer, default=0)
    current_level = Column(Integer, default=1)
    current_badge_id = Column(Integer, ForeignKey("level_badges.id"))
    is_excellent = Column(Boolean, default=False)
    excellent_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    themes = relationship("StaffTheme", back_populates="staff", cascade="all, delete-orphan")
    venues = relationship("StaffVenue", back_populates="staff", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="staff")
    point_records = relationship("PointRecord", back_populates="staff", cascade="all, delete-orphan")
    monthly_rankings = relationship("MonthlyRanking", back_populates="staff", cascade="all, delete-orphan")
    badges = relationship("StaffBadge", back_populates="staff", cascade="all, delete-orphan")
    current_badge = relationship("LevelBadge", foreign_keys=[current_badge_id])


class Theme(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    category = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    staff_themes = relationship("StaffTheme", back_populates="theme")
    sessions = relationship("Session", back_populates="theme")
    warnings = relationship("Warning", back_populates="theme")


class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    venue_type = Column(String(50), nullable=False)
    capacity = Column(Integer)
    location = Column(String(200))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    staff_venues = relationship("StaffVenue", back_populates="venue")
    sessions = relationship("Session", back_populates="venue")


class StaffTheme(Base):
    __tablename__ = "staff_themes"

    id = Column(Integer, primary_key=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    proficiency_level = Column(Integer, default=3)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    staff = relationship("Staff", back_populates="themes")
    theme = relationship("Theme", back_populates="staff_themes")


class StaffVenue(Base):
    __tablename__ = "staff_venues"

    id = Column(Integer, primary_key=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    is_certified = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    staff = relationship("Staff", back_populates="venues")
    venue = relationship("Venue", back_populates="staff_venues")


class School(Base):
    __tablename__ = "schools"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    contact_person = Column(String(50))
    phone = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    sessions = relationship("Session", back_populates="school")


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    session_type = Column(Enum(SessionType), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    audience_type = Column(Enum(AudienceType), nullable=False)
    audience_count = Column(Integer, default=0)
    school_id = Column(Integer, ForeignKey("schools.id"))
    guides_needed = Column(Integer, default=0)
    needs_lecturer = Column(Boolean, default=False)
    status = Column(Enum(SessionStatus), default=SessionStatus.DRAFT)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    theme = relationship("Theme", back_populates="sessions")
    venue = relationship("Venue", back_populates="sessions")
    school = relationship("School", back_populates="sessions")
    assignments = relationship("Assignment", back_populates="session", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="session", cascade="all, delete-orphan")
    change_requests = relationship("ChangeRequest", back_populates="session", cascade="all, delete-orphan")
    change_histories = relationship("ChangeHistory", back_populates="session", cascade="all, delete-orphan")


class Assignment(Base):
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    role = Column(Enum(AssignmentRole), nullable=False)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="assignments")
    staff = relationship("Staff", back_populates="assignments")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    reviewer_name = Column(String(100))
    reviewer_type = Column(String(50))
    rating = Column(Integer, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="reviews")


class Warning(Base):
    __tablename__ = "warnings"

    id = Column(Integer, primary_key=True, index=True)
    theme_id = Column(Integer, ForeignKey("themes.id"))
    warning_type = Column(Enum(WarningType), nullable=False)
    message = Column(Text, nullable=False)
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    theme = relationship("Theme", back_populates="warnings")


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    requester = Column(String(100), nullable=False)
    change_type = Column(Enum(ChangeType), nullable=False)
    old_start_time = Column(DateTime)
    old_end_time = Column(DateTime)
    old_audience_count = Column(Integer)
    old_guides_needed = Column(Integer)
    new_start_time = Column(DateTime)
    new_end_time = Column(DateTime)
    new_audience_count = Column(Integer)
    new_guides_needed = Column(Integer)
    reason = Column(Text)
    status = Column(Enum(ChangeStatus), default=ChangeStatus.PENDING)
    reviewer = Column(String(100))
    review_comment = Column(Text)
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("Session", back_populates="change_requests")
    conflicts = relationship("SessionConflict", back_populates="change_request", cascade="all, delete-orphan")
    reschedule_suggestions = relationship("RescheduleSuggestion", back_populates="change_request", cascade="all, delete-orphan")
    change_histories = relationship("ChangeHistory", back_populates="change_request", cascade="all, delete-orphan")


class ChangeHistory(Base):
    __tablename__ = "change_histories"

    id = Column(Integer, primary_key=True, index=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id"))
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    operator = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    old_values = Column(Text)
    new_values = Column(Text)
    change_type = Column(Enum(ChangeType))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", back_populates="change_histories")
    change_request = relationship("ChangeRequest", back_populates="change_histories")


class SessionConflict(Base):
    __tablename__ = "session_conflicts"

    id = Column(Integer, primary_key=True, index=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id"), nullable=False)
    conflict_type = Column(Enum(ConflictType), nullable=False)
    staff_id = Column(Integer, ForeignKey("staff.id"))
    assignment_id = Column(Integer, ForeignKey("assignments.id"))
    message = Column(Text, nullable=False)
    detail = Column(Text)
    status = Column(Enum(RescheduleStatus), default=RescheduleStatus.PENDING)
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    change_request = relationship("ChangeRequest", back_populates="conflicts")
    staff = relationship("Staff")
    assignment = relationship("Assignment")


class RescheduleSuggestion(Base):
    __tablename__ = "reschedule_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    change_request_id = Column(Integer, ForeignKey("change_requests.id"), nullable=False)
    conflict_id = Column(Integer, ForeignKey("session_conflicts.id"))
    staff_id = Column(Integer, ForeignKey("staff.id"))
    suggested_staff_id = Column(Integer, ForeignKey("staff.id"))
    action = Column(String(50), nullable=False)
    priority = Column(Integer, default=5)
    reason = Column(Text)
    is_applied = Column(Boolean, default=False)
    applied_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    change_request = relationship("ChangeRequest", back_populates="reschedule_suggestions")
    conflict = relationship("SessionConflict")
    staff = relationship("Staff", foreign_keys=[staff_id])
    suggested_staff = relationship("Staff", foreign_keys=[suggested_staff_id])


class PointSourceType(str, enum.Enum):
    SERVICE = "服务积分"
    RATING = "评价奖励"
    BONUS = "额外奖励"
    DEDUCTION = "积分扣除"


class LevelBadge(Base):
    __tablename__ = "level_badges"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(Integer, unique=True, nullable=False)
    name = Column(String(50), nullable=False)
    badge_name = Column(String(100), nullable=False)
    min_points = Column(Integer, nullable=False)
    max_points = Column(Integer)
    description = Column(Text)
    icon = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    point_records = relationship("PointRecord", back_populates="level_badge")
    monthly_rankings = relationship("MonthlyRanking", back_populates="level_badge")


class PointRecord(Base):
    __tablename__ = "point_records"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    review_id = Column(Integer, ForeignKey("reviews.id"))
    level_badge_id = Column(Integer, ForeignKey("level_badges.id"))
    source_type = Column(Enum(PointSourceType), nullable=False)
    points = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    staff = relationship("Staff", back_populates="point_records")
    session = relationship("Session")
    review = relationship("Review")
    level_badge = relationship("LevelBadge", back_populates="point_records")


class MonthlyRanking(Base):
    __tablename__ = "monthly_rankings"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    rank = Column(Integer, nullable=False)
    total_points = Column(Integer, nullable=False)
    positive_review_rate = Column(Float, nullable=False)
    session_count = Column(Integer, nullable=False)
    is_excellent = Column(Boolean, default=False)
    level_badge_id = Column(Integer, ForeignKey("level_badges.id"))
    settled_at = Column(DateTime(timezone=True), server_default=func.now())

    staff = relationship("Staff", back_populates="monthly_rankings")
    level_badge = relationship("LevelBadge", back_populates="monthly_rankings")


class StaffBadge(Base):
    __tablename__ = "staff_badges"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    level_badge_id = Column(Integer, ForeignKey("level_badges.id"), nullable=False)
    earned_at = Column(DateTime(timezone=True), server_default=func.now())
    is_current = Column(Boolean, default=True)

    staff = relationship("Staff", back_populates="badges")
    level_badge = relationship("LevelBadge")


class VersionStatus(str, enum.Enum):
    DRAFT = "草稿"
    PUBLISHED = "已发布"
    WITHDRAWN = "已撤回"


class ErrataSeverity(str, enum.Enum):
    LOW = "文字微调"
    NORMAL = "常规勘误"
    CRITICAL = "紧急勘误"


class ErrataStatus(str, enum.Enum):
    ACTIVE = "生效中"
    SUPERSEDED = "已被取代"


class FreezeScheduleState(str, enum.Enum):
    CONFIRMED = "已确认"
    RESCHEDULED_PENDING = "改期待审核"
    VERSION_WITHDRAWN_PENDING = "版本撤回待重新确认"
    UPDATE_PENDING = "新版本待确认"
    UPDATE_DECLINED = "学校拒绝新版本"
    ERRATA_PENDING = "勘误待回应"
    COMPLETED_LOCKED = "已结束证据锁定"


class SchoolResponse(str, enum.Enum):
    PENDING = "待回应"
    ACCEPTED = "接受"
    DECLINED = "拒绝"


class ErrataAckStatus(str, enum.Enum):
    PENDING = "待回应"
    APPLIED = "已应用"
    DECLINED = "已拒绝"
    IRRELEVANT = "不适用"


class ContentVersion(Base):
    """主题讲解词版本：以发布形式存在，带适用年龄、必讲段落和生效区间"""
    __tablename__ = "content_versions"

    id = Column(Integer, primary_key=True, index=True)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    version_no = Column(Integer, nullable=False)
    status = Column(Enum(VersionStatus), nullable=False, default=VersionStatus.DRAFT)
    min_age = Column(Integer, nullable=False)
    max_age = Column(Integer, nullable=False)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_to = Column(DateTime(timezone=True), nullable=False)
    content_hash = Column(String(64))
    change_note = Column(Text)
    created_by = Column(String(100))
    published_by = Column(String(100))
    published_at = Column(DateTime(timezone=True))
    withdrawn_by = Column(String(100))
    withdraw_reason = Column(Text)
    withdrawn_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    theme = relationship("Theme")
    sections = relationship("ContentSection", back_populates="version",
                            cascade="all, delete-orphan",
                            order_by="ContentSection.section_no")
    erratas = relationship("ContentErratum", back_populates="version",
                           cascade="all, delete-orphan",
                           order_by="ContentErratum.erratum_no")
    freezes = relationship("SessionContentFreeze", back_populates="content_version",
                           foreign_keys="SessionContentFreeze.theme_version_id")


class ContentSection(Base):
    """版本内的讲解段落，is_required 标记必讲段落"""
    __tablename__ = "content_sections"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("content_versions.id"), nullable=False)
    section_no = Column(Integer, nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    is_required = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    version = relationship("ContentVersion", back_populates="sections")


class ContentErratum(Base):
    """紧急勘误：挂在已发布版本上，同段新勘误取代旧勘误，形成勘误链"""
    __tablename__ = "content_erratas"

    id = Column(Integer, primary_key=True, index=True)
    theme_version_id = Column(Integer, ForeignKey("content_versions.id"), nullable=False)
    erratum_no = Column(Integer, nullable=False)
    section_id = Column(Integer, ForeignKey("content_sections.id"))
    title = Column(String(200), nullable=False)
    old_text = Column(Text)
    new_text = Column(Text, nullable=False)
    reason = Column(Text)
    severity = Column(Enum(ErrataSeverity), nullable=False, default=ErrataSeverity.NORMAL)
    status = Column(Enum(ErrataStatus), nullable=False, default=ErrataStatus.ACTIVE)
    supersedes_id = Column(Integer, ForeignKey("content_erratas.id"))
    issued_by = Column(String(100))
    issued_at = Column(DateTime(timezone=True), server_default=func.now())

    version = relationship("ContentVersion", back_populates="erratas", foreign_keys=[theme_version_id])
    section = relationship("ContentSection")
    supersedes = relationship("ContentErratum", remote_side=[id], foreign_keys=[supersedes_id])
    acks = relationship("SessionErrataAck", back_populates="erratum",
                        cascade="all, delete-orphan")


class SessionContentFreeze(Base):
    """场次确认时冻结的可核验内容清单（快照+哈希），只追加不改写"""
    __tablename__ = "session_content_freezes"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    theme_version_id = Column(Integer, ForeignKey("content_versions.id"), nullable=False)
    audience_age = Column(Integer)
    is_current = Column(Boolean, nullable=False, default=True)
    frozen_snapshot = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    schedule_state = Column(Enum(FreezeScheduleState), nullable=False,
                            default=FreezeScheduleState.CONFIRMED)
    school_confirmed = Column(Boolean, nullable=False, default=True)
    confirmed_by = Column(String(100))
    frozen_at = Column(DateTime(timezone=True), server_default=func.now())

    # 新版本确认流程
    target_version_id = Column(Integer, ForeignKey("content_versions.id"))
    school_response = Column(Enum(SchoolResponse), default=SchoolResponse.PENDING)
    responded_at = Column(DateTime(timezone=True))
    response_note = Column(Text)

    # 改期申请（审核通过前不改动场次时间）
    pending_start_time = Column(DateTime(timezone=True))
    pending_end_time = Column(DateTime(timezone=True))
    reschedule_reason = Column(Text)
    requested_by = Column(String(100))
    reschedule_reviewed_by = Column(String(100))
    reschedule_reviewed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    session = relationship("Session", foreign_keys=[session_id])
    theme = relationship("Theme")
    content_version = relationship("ContentVersion", foreign_keys=[theme_version_id],
                                   back_populates="freezes")
    target_version = relationship("ContentVersion", foreign_keys=[target_version_id])
    erratum_acks = relationship("SessionErrataAck", back_populates="freeze",
                                cascade="all, delete-orphan")


class SessionErrataAck(Base):
    """场次对某条勘误的回应记录：未开始场次可应用/拒绝，已结束场次不生成"""
    __tablename__ = "session_errata_acks"

    id = Column(Integer, primary_key=True, index=True)
    freeze_id = Column(Integer, ForeignKey("session_content_freezes.id"), nullable=False)
    erratum_id = Column(Integer, ForeignKey("content_erratas.id"), nullable=False)
    status = Column(Enum(ErrataAckStatus), nullable=False, default=ErrataAckStatus.PENDING)
    decided_by = Column(String(100))
    decided_at = Column(DateTime(timezone=True))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    freeze = relationship("SessionContentFreeze", back_populates="erratum_acks")
    erratum = relationship("ContentErratum", back_populates="acks")


class StaffReplacement(Base):
    """讲解员/讲师临时替换记录（只追加），不影响内容冻结证据"""
    __tablename__ = "staff_replacements"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    old_staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    new_staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    old_assignment_id = Column(Integer)
    role = Column(Enum(AssignmentRole), nullable=False)
    reason = Column(Text)
    operator = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("Session", foreign_keys=[session_id])
    old_staff = relationship("Staff", foreign_keys=[old_staff_id])
    new_staff = relationship("Staff", foreign_keys=[new_staff_id])
