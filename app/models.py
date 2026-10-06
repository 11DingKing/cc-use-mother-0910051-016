from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum, Text, UniqueConstraint
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


class ContentVersionStatus(str, enum.Enum):
    DRAFT = "草稿"
    PUBLISHED = "已发布"
    WITHDRAWN = "已撤回"


class ErratumStatus(str, enum.Enum):
    ISSUED = "已发布"
    ACKNOWLEDGED = "已知悉"
    SUPERSEDED = "已被替代"


class ContentConfirmationStatus(str, enum.Enum):
    CONFIRMED = "已确认"
    PENDING_RECONFIRM = "待重新确认"
    SCHOOL_REJECTED = "学校拒绝新版本"
    SUPERSEDED = "已被新版本替代"


class SubstitutionStatus(str, enum.Enum):
    REQUESTED = "待替班"
    SUBSTITUTED = "替班已到岗"
    RESTORED = "原讲解员已回归"
    CANCELLED = "已取消"


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
    content_versions = relationship("ThemeContentVersion", back_populates="theme",
                                    cascade="all, delete-orphan")


class ThemeContentVersion(Base):
    """主题讲解词内容版本

    讲解词以“版本”为单位发布，而不是直接覆盖主题描述。每个版本固化
    适用年龄、必讲段落和生效区间，一经发布其内容即冻结，只能通过新版本
    或紧急勘误来修正，保证历史场次引用的内容可追溯、可核验。
    """
    __tablename__ = "theme_content_versions"

    id = Column(Integer, primary_key=True, index=True)
    theme_id = Column(Integer, ForeignKey("themes.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    status = Column(Enum(ContentVersionStatus), default=ContentVersionStatus.DRAFT, nullable=False)
    title = Column(String(200))
    age_min = Column(Integer, nullable=False)
    age_max = Column(Integer, nullable=False)
    content_text = Column(Text, nullable=False)
    required_segments = Column(Text, nullable=False)
    sensitivity_notes = Column(Text)
    effective_from = Column(DateTime(timezone=True), nullable=False)
    effective_to = Column(DateTime(timezone=True))
    published_at = Column(DateTime(timezone=True))
    withdrawn_at = Column(DateTime(timezone=True))
    withdraw_reason = Column(Text)
    created_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("theme_id", "version_number", name="uq_theme_version_number"),
    )

    theme = relationship("Theme", back_populates="content_versions")
    items = relationship("ContentVersionItem", back_populates="version",
                         cascade="all, delete-orphan")
    confirmations = relationship("SessionContentConfirmation", back_populates="version")
    errata = relationship("ContentErratum", back_populates="version",
                          cascade="all, delete-orphan")


class ContentVersionItem(Base):
    """版本内的可核验内容清单项（必讲段落的逐条固化）

    每条清单计算 content_hash；场次确认时复制一份到冻结快照，
    事后可逐条比对，证明历史场次实际确认了哪些内容。
    """
    __tablename__ = "content_version_items"

    id = Column(Integer, primary_key=True, index=True)
    version_id = Column(Integer, ForeignKey("theme_content_versions.id"), nullable=False)
    segment_key = Column(String(100), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    is_required = Column(Boolean, default=True)
    content_hash = Column(String(64), nullable=False)
    sort_order = Column(Integer, default=0)

    version = relationship("ThemeContentVersion", back_populates="items")


class SessionContentConfirmation(Base):
    """场次内容确认（学校确认时冻结的内容清单）

    场次与某个内容版本绑定后即冻结一份快照（清单 JSON + 整体校验值）。
    后续主题发布新版本或勘误不会改写该快照，只能通过重新确认建立新的
    确认记录。已结束场次的快照作为永久证据，任何接口都不得改写。
    """
    __tablename__ = "session_content_confirmations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    content_version_id = Column(Integer, ForeignKey("theme_content_versions.id"), nullable=False)
    status = Column(Enum(ContentConfirmationStatus),
                    default=ContentConfirmationStatus.CONFIRMED, nullable=False)
    frozen_age_min = Column(Integer, nullable=False)
    frozen_age_max = Column(Integer, nullable=False)
    frozen_checklist = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)
    confirmed_by = Column(String(100))
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())
    reconfirm_reason = Column(Text)
    school_response_at = Column(DateTime(timezone=True))
    superseded_by_id = Column(Integer, ForeignKey("session_content_confirmations.id"))

    session = relationship("Session", back_populates="content_confirmations")
    version = relationship("ThemeContentVersion", back_populates="confirmations")
    errata_acknowledgements = relationship("ErratumAcknowledgement", back_populates="confirmation",
                                           cascade="all, delete-orphan")
    superseded_by = relationship("SessionContentConfirmation",
                                 foreign_keys=[superseded_by_id])


class ContentErratum(Base):
    """内容版本紧急勘误

    勘误附加在已发布版本之上，形成可追溯的勘误链。它只追加、不修改
    原始版本与历史快照；未开始场次可被要求据此重新确认，已结束场次的
    证据不受影响。勘误本身也可被后续勘误替代（勘误链）。
    """
    __tablename__ = "content_errata"

    id = Column(Integer, primary_key=True, index=True)
    content_version_id = Column(Integer, ForeignKey("theme_content_versions.id"), nullable=False)
    erratum_no = Column(Integer, nullable=False)
    target_item_id = Column(Integer, ForeignKey("content_version_items.id"))
    severity = Column(String(20), default="一般")
    old_text = Column(Text)
    new_text = Column(Text, nullable=False)
    reason = Column(Text)
    status = Column(Enum(ErratumStatus), default=ErratumStatus.ISSUED, nullable=False)
    issued_by = Column(String(100))
    issued_at = Column(DateTime(timezone=True), server_default=func.now())
    supersedes_erratum_id = Column(Integer, ForeignKey("content_errata.id"))

    __table_args__ = (
        UniqueConstraint("content_version_id", "erratum_no", name="uq_version_erratum_no"),
    )

    version = relationship("ThemeContentVersion", back_populates="errata",
                           foreign_keys=[content_version_id])
    target_item = relationship("ContentVersionItem")
    supersedes = relationship("ContentErratum",
                              foreign_keys=[supersedes_erratum_id])
    acknowledgements = relationship("ErratumAcknowledgement", back_populates="erratum",
                                    cascade="all, delete-orphan")


class ErratumAcknowledgement(Base):
    """场次确认快照对某条勘误的知悉/处理记录

    记录某场次冻结清单“后续勘误链”的处理情况：已送达、已知悉或已随
    重新确认并入新快照。该表只追加，保证勘误链对历史场次完整可查。
    """
    __tablename__ = "erratum_acknowledgements"

    id = Column(Integer, primary_key=True, index=True)
    erratum_id = Column(Integer, ForeignKey("content_errata.id"), nullable=False)
    confirmation_id = Column(Integer, ForeignKey("session_content_confirmations.id"), nullable=False)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(100))
    note = Column(Text)

    __table_args__ = (
        UniqueConstraint("erratum_id", "confirmation_id", name="uq_erratum_confirmation"),
    )

    erratum = relationship("ContentErratum", back_populates="acknowledgements")
    confirmation = relationship("SessionContentConfirmation",
                                back_populates="errata_acknowledgements")


class GuideSubstitution(Base):
    """讲解员临时替换记录

    讲解员临时不能到场时，以“替班”形式登记确定状态：待替班、替班已到岗、
    原讲解员已回归、已取消。替班不改写场次的内容冻结证据，只追加人员变动
    留痕，便于事后还原“某时段由谁讲解”。
    """
    __tablename__ = "guide_substitutions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    original_staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    substitute_staff_id = Column(Integer, ForeignKey("staff.id"))
    role = Column(Enum(AssignmentRole), nullable=False)
    reason = Column(Text)
    status = Column(Enum(SubstitutionStatus), default=SubstitutionStatus.REQUESTED, nullable=False)
    requested_by = Column(String(100))
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    substituted_at = Column(DateTime(timezone=True))
    restored_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))
    operator = Column(String(100))

    session = relationship("Session", back_populates="guide_substitutions")
    assignment = relationship("Assignment")
    original_staff = relationship("Staff", foreign_keys=[original_staff_id])
    substitute_staff = relationship("Staff", foreign_keys=[substitute_staff_id])


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
    content_confirmations = relationship("SessionContentConfirmation", back_populates="session",
                                         cascade="all, delete-orphan")
    guide_substitutions = relationship("GuideSubstitution", back_populates="session",
                                       cascade="all, delete-orphan")


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
