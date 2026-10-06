from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

from app.models import (
    StaffType, SessionType, SessionStatus,
    AssignmentRole, AudienceType, WarningType,
    ChangeType, ChangeStatus, ConflictType, RescheduleStatus,
    PointSourceType, VersionStatus, ErrataSeverity, ErrataStatus,
    FreezeScheduleState, SchoolResponse, ErrataAckStatus,
)


class StaffThemeBase(BaseModel):
    theme_id: int
    proficiency_level: int = 3


class StaffThemeCreate(StaffThemeBase):
    pass


class StaffTheme(StaffThemeBase):
    id: int
    theme_name: str

    class Config:
        from_attributes = True


class StaffVenueBase(BaseModel):
    venue_id: int
    is_certified: bool = True


class StaffVenueCreate(StaffVenueBase):
    pass


class StaffVenue(StaffVenueBase):
    id: int
    venue_name: str

    class Config:
        from_attributes = True


class StaffBase(BaseModel):
    name: str
    staff_type: StaffType
    phone: Optional[str] = None
    email: Optional[str] = None


class StaffCreate(StaffBase):
    themes: List[StaffThemeCreate] = []
    venues: List[StaffVenueCreate] = []


class StaffUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    themes: Optional[List[StaffThemeCreate]] = None
    venues: Optional[List[StaffVenueCreate]] = None


class Staff(StaffBase):
    id: int
    total_service_hours: float
    star_rating: float
    review_count: int
    is_active: bool
    total_points: int
    current_level: int
    current_badge_id: Optional[int] = None
    is_excellent: bool
    excellent_until: Optional[datetime] = None
    themes: List[StaffTheme] = []
    venues: List[StaffVenue] = []
    created_at: datetime

    class Config:
        from_attributes = True


class ThemeBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None


class ThemeCreate(ThemeBase):
    pass


class ThemeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None


class Theme(ThemeBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class VenueBase(BaseModel):
    name: str
    venue_type: str
    capacity: Optional[int] = None
    location: Optional[str] = None


class VenueCreate(VenueBase):
    pass


class VenueUpdate(BaseModel):
    name: Optional[str] = None
    venue_type: Optional[str] = None
    capacity: Optional[int] = None
    location: Optional[str] = None


class Venue(VenueBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SchoolBase(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None


class SchoolCreate(SchoolBase):
    pass


class SchoolUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    phone: Optional[str] = None


class School(SchoolBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class AssignmentBase(BaseModel):
    staff_id: int
    role: AssignmentRole
    is_primary: bool = False


class AssignmentCreate(AssignmentBase):
    pass


class Assignment(AssignmentBase):
    id: int
    staff_name: str
    staff_type: str
    star_rating: float
    created_at: datetime

    class Config:
        from_attributes = True


class SessionBase(BaseModel):
    title: str
    theme_id: int
    venue_id: int
    session_type: SessionType
    start_time: datetime
    end_time: datetime
    audience_type: AudienceType
    audience_count: int = 0
    school_id: Optional[int] = None
    guides_needed: int = 0
    needs_lecturer: bool = False
    description: Optional[str] = None


class SessionCreate(SessionBase):
    pass


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    theme_id: Optional[int] = None
    venue_id: Optional[int] = None
    session_type: Optional[SessionType] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    audience_type: Optional[AudienceType] = None
    audience_count: Optional[int] = None
    school_id: Optional[int] = None
    guides_needed: Optional[int] = None
    needs_lecturer: Optional[bool] = None
    description: Optional[str] = None
    status: Optional[SessionStatus] = None


class Session(SessionBase):
    id: int
    status: SessionStatus
    theme_name: str
    venue_name: str
    school_name: Optional[str] = None
    assignments: List[Assignment] = []
    is_fully_staffed: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionWithDetails(Session):
    pass


class ReviewBase(BaseModel):
    session_id: int
    reviewer_name: Optional[str] = None
    reviewer_type: Optional[str] = None
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None


class ReviewCreate(ReviewBase):
    pass


class Review(ReviewBase):
    id: int
    session_title: str
    created_at: datetime

    class Config:
        from_attributes = True


class WarningBase(BaseModel):
    theme_id: Optional[int] = None
    warning_type: WarningType
    message: str


class WarningCreate(WarningBase):
    pass


class Warning(WarningBase):
    id: int
    resolved: bool
    theme_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AssignmentValidationResult(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


class ThemeSessionStats(BaseModel):
    theme_id: int
    theme_name: str
    session_count: int
    guide_count: int


class StaffSaturationStats(BaseModel):
    staff_id: int
    staff_name: str
    staff_type: str
    assigned_hours: float
    available_hours: float
    saturation_rate: float


class StaffRankingItem(BaseModel):
    staff_id: int
    staff_name: str
    staff_type: str
    total_service_hours: float
    star_rating: float
    review_count: int
    session_count: int


class StaffRecommendation(BaseModel):
    staff_id: int
    staff_name: str
    star_rating: float
    proficiency_level: int
    is_certified: bool
    is_available: bool
    score: float


class BulkAssignmentResponse(BaseModel):
    success: bool
    message: str
    assigned_staff: List[int] = []
    errors: List[str] = []


class ChangeRequestBase(BaseModel):
    session_id: int
    requester: str
    change_type: ChangeType
    new_start_time: Optional[datetime] = None
    new_end_time: Optional[datetime] = None
    new_audience_count: Optional[int] = None
    new_guides_needed: Optional[int] = None
    reason: Optional[str] = None


class ChangeRequestCreate(ChangeRequestBase):
    pass


class ChangeRequestReview(BaseModel):
    status: ChangeStatus
    reviewer: str
    review_comment: Optional[str] = None


class ChangeRequest(ChangeRequestBase):
    id: int
    old_start_time: Optional[datetime] = None
    old_end_time: Optional[datetime] = None
    old_audience_count: Optional[int] = None
    old_guides_needed: Optional[int] = None
    status: ChangeStatus
    reviewer: Optional[str] = None
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    session_title: Optional[str] = None
    conflict_count: int = 0
    suggestion_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChangeRequestWithDetails(ChangeRequest):
    conflicts: List["SessionConflict"] = []
    suggestions: List["RescheduleSuggestion"] = []


class SessionConflictBase(BaseModel):
    conflict_type: ConflictType
    message: str
    detail: Optional[str] = None


class SessionConflictCreate(SessionConflictBase):
    change_request_id: int
    staff_id: Optional[int] = None
    assignment_id: Optional[int] = None


class SessionConflict(SessionConflictBase):
    id: int
    change_request_id: int
    staff_id: Optional[int] = None
    staff_name: Optional[str] = None
    assignment_id: Optional[int] = None
    status: RescheduleStatus
    resolved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RescheduleSuggestionBase(BaseModel):
    action: str
    priority: int = 5
    reason: Optional[str] = None


class RescheduleSuggestionCreate(RescheduleSuggestionBase):
    change_request_id: int
    conflict_id: Optional[int] = None
    staff_id: Optional[int] = None
    suggested_staff_id: Optional[int] = None


class RescheduleSuggestion(RescheduleSuggestionBase):
    id: int
    change_request_id: int
    conflict_id: Optional[int] = None
    staff_id: Optional[int] = None
    staff_name: Optional[str] = None
    suggested_staff_id: Optional[int] = None
    suggested_staff_name: Optional[str] = None
    is_applied: bool
    applied_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChangeHistoryBase(BaseModel):
    session_id: int
    operator: str
    action: str
    description: Optional[str] = None


class ChangeHistoryCreate(ChangeHistoryBase):
    change_request_id: Optional[int] = None
    old_values: Optional[str] = None
    new_values: Optional[str] = None
    change_type: Optional[ChangeType] = None


class ChangeHistory(ChangeHistoryBase):
    id: int
    change_request_id: Optional[int] = None
    old_values: Optional[str] = None
    new_values: Optional[str] = None
    change_type: Optional[ChangeType] = None
    session_title: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConflictCheckResult(BaseModel):
    has_conflicts: bool
    conflicts: List[SessionConflict] = []
    suggestions: List[RescheduleSuggestion] = []
    summary: str


class ChangeExecuteResult(BaseModel):
    success: bool
    message: str
    applied_suggestions: int = 0
    remaining_conflicts: int = 0
    errors: List[str] = []


class SessionChangeStats(BaseModel):
    session_id: int
    session_title: str
    change_count: int
    time_change_count: int
    count_change_count: int
    last_changed_at: Optional[datetime] = None


class ChangeFrequencyStats(BaseModel):
    period: str
    total_changes: int
    time_changes: int
    count_changes: int
    both_changes: int
    approved_count: int
    rejected_count: int
    avg_resolution_time_hours: float


ChangeRequestWithDetails.model_rebuild()


class LevelBadgeBase(BaseModel):
    level: int
    name: str
    badge_name: str
    min_points: int
    max_points: Optional[int] = None
    description: Optional[str] = None
    icon: Optional[str] = None


class LevelBadgeCreate(LevelBadgeBase):
    pass


class LevelBadgeUpdate(BaseModel):
    name: Optional[str] = None
    badge_name: Optional[str] = None
    min_points: Optional[int] = None
    max_points: Optional[int] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    is_active: Optional[bool] = None


class LevelBadge(LevelBadgeBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PointRecordBase(BaseModel):
    staff_id: int
    source_type: PointSourceType
    points: int
    description: Optional[str] = None


class PointRecordCreate(PointRecordBase):
    session_id: Optional[int] = None
    review_id: Optional[int] = None


class PointRecord(PointRecordBase):
    id: int
    session_id: Optional[int] = None
    review_id: Optional[int] = None
    level_badge_id: Optional[int] = None
    balance_after: int
    session_title: Optional[str] = None
    level_badge_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class StaffBadgeBase(BaseModel):
    staff_id: int
    level_badge_id: int


class StaffBadge(StaffBadgeBase):
    id: int
    earned_at: datetime
    is_current: bool
    level_badge_name: str
    level: int
    icon: Optional[str] = None

    class Config:
        from_attributes = True


class MonthlyRankingBase(BaseModel):
    staff_id: int
    year: int
    month: int
    rank: int
    total_points: int
    positive_review_rate: float
    session_count: int
    is_excellent: bool = False


class MonthlyRanking(MonthlyRankingBase):
    id: int
    staff_name: str
    level_badge_id: Optional[int] = None
    level_badge_name: Optional[str] = None
    settled_at: datetime

    class Config:
        from_attributes = True


class StaffWithDetails(Staff):
    total_points: int
    current_level: int
    current_badge_name: Optional[str] = None
    current_badge_icon: Optional[str] = None
    is_excellent: bool
    excellent_until: Optional[datetime] = None
    badges: List[StaffBadge] = []


class PointChangeResult(BaseModel):
    success: bool
    staff_id: int
    points_added: int
    new_balance: int
    level_up: bool = False
    new_level: Optional[int] = None
    new_badge: Optional[LevelBadge] = None
    message: str


class MonthlySettleResult(BaseModel):
    success: bool
    year: int
    month: int
    total_staff: int
    excellent_staff: List[int] = []
    message: str


class PointTrendItem(BaseModel):
    date: str
    points: int
    staff_count: int


class LevelDistributionItem(BaseModel):
    level: int
    level_name: str
    badge_name: str
    staff_count: int
    percentage: float


class StaffPointDetail(StaffRankingItem):
    total_points: int
    current_level: int
    current_badge_name: Optional[str] = None
    is_excellent: bool
    positive_review_rate: float
    monthly_points: int = 0


# ============ 讲解词版本、冻结清单与勘误 ============


class ContentSectionBase(BaseModel):
    title: str
    body: str
    is_required: bool = True


class ContentSectionCreate(ContentSectionBase):
    section_no: Optional[int] = None


class ContentSection(ContentSectionBase):
    id: int
    section_no: int

    class Config:
        from_attributes = True


class ContentVersionBase(BaseModel):
    min_age: int = Field(ge=0, le=120)
    max_age: int = Field(ge=0, le=120)
    effective_from: datetime
    effective_to: datetime
    change_note: Optional[str] = None


class ContentVersionCreate(ContentVersionBase):
    sections: List[ContentSectionCreate]
    created_by: Optional[str] = None


class ContentVersionDraftUpdate(BaseModel):
    """更新草稿（已发布/已撤回版本不可修改，保证证据不可变）"""
    min_age: Optional[int] = Field(None, ge=0, le=120)
    max_age: Optional[int] = Field(None, ge=0, le=120)
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    change_note: Optional[str] = None
    sections: Optional[List[ContentSectionCreate]] = None


class ContentVersionPublish(BaseModel):
    operator: str


class ContentVersionWithdraw(BaseModel):
    operator: str
    reason: str


class ContentVersionSummary(BaseModel):
    id: int
    theme_id: int
    theme_name: str
    version_no: int
    status: VersionStatus
    min_age: int
    max_age: int
    effective_from: datetime
    effective_to: datetime
    content_hash: Optional[str] = None
    change_note: Optional[str] = None
    created_by: Optional[str] = None
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None
    withdrawn_by: Optional[str] = None
    withdraw_reason: Optional[str] = None
    withdrawn_at: Optional[datetime] = None
    section_count: int = 0
    required_section_count: int = 0
    active_errata_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class ContentVersionDetail(ContentVersionSummary):
    sections: List[ContentSection] = []


class ErratumCreate(BaseModel):
    section_id: Optional[int] = None
    title: str
    old_text: Optional[str] = None
    new_text: str
    reason: Optional[str] = None
    severity: ErrataSeverity = ErrataSeverity.NORMAL
    issued_by: Optional[str] = None


class Erratum(BaseModel):
    id: int
    theme_version_id: int
    erratum_no: int
    section_id: Optional[int] = None
    section_title: Optional[str] = None
    title: str
    old_text: Optional[str] = None
    new_text: str
    reason: Optional[str] = None
    severity: ErrataSeverity
    status: ErrataStatus
    supersedes_id: Optional[int] = None
    issued_by: Optional[str] = None
    issued_at: datetime

    class Config:
        from_attributes = True


class FreezeCreate(BaseModel):
    """场次确认：冻结当时发布版本的内容清单"""
    audience_age: Optional[int] = Field(None, ge=0, le=120)
    confirmed_by: Optional[str] = None


class RescheduleRequest(BaseModel):
    """场次改期申请：进入"改期待审核"，审核通过后才改变场次时间"""
    new_start_time: datetime
    new_end_time: datetime
    reason: Optional[str] = None
    requester: str


class RescheduleReview(BaseModel):
    approved: bool
    reviewer: str
    comment: Optional[str] = None


class NewVersionDecision(BaseModel):
    """学校对新版本的回应：接受则冻结新版本，拒绝则保留原冻结"""
    accepted: bool
    responder: str
    note: Optional[str] = None


class ErrataDecision(BaseModel):
    """场次对勘误的回应"""
    apply: bool
    responder: str
    note: Optional[str] = None


class FreezeSectionItem(BaseModel):
    section_no: int
    title: str
    body: str
    is_required: bool
    # 该段落叠加的勘误（按勘误链排序，最后一条生效勘误为准）
    erratas: List[Erratum] = []


class ErrataAckItem(BaseModel):
    id: int
    erratum_id: int
    erratum_title: str
    severity: ErrataSeverity
    status: ErrataAckStatus
    decided_by: Optional[str] = None
    decided_at: Optional[datetime] = None
    note: Optional[str] = None
    created_at: datetime


class SessionFreeze(BaseModel):
    id: int
    session_id: int
    session_title: str
    theme_id: int
    theme_name: str
    theme_version_id: int
    version_no: int
    audience_age: Optional[int] = None
    is_current: bool
    content_hash: str
    schedule_state: FreezeScheduleState
    school_confirmed: bool
    confirmed_by: Optional[str] = None
    frozen_at: datetime
    target_version_id: Optional[int] = None
    target_version_no: Optional[int] = None
    school_response: SchoolResponse
    responded_at: Optional[datetime] = None
    response_note: Optional[str] = None
    pending_start_time: Optional[datetime] = None
    pending_end_time: Optional[datetime] = None
    reschedule_reason: Optional[str] = None
    requested_by: Optional[str] = None
    reschedule_reviewed_by: Optional[str] = None
    reschedule_reviewed_at: Optional[datetime] = None
    snapshot: Optional[dict] = None
    sections: List[FreezeSectionItem] = []
    erratum_acks: List[ErrataAckItem] = []


class FreezeReplay(BaseModel):
    """按场次还原：冻结清单 + 后续勘误链"""
    freeze: SessionFreeze
    errata_chain: List[Erratum] = []
    pending_erratas: List[Erratum] = []
    effective_sections: List[FreezeSectionItem] = []


class StaffReplacementCreate(BaseModel):
    new_staff_id: int
    old_staff_id: Optional[int] = None
    reason: Optional[str] = None
    operator: str


class StaffReplacementRecord(BaseModel):
    id: int
    session_id: int
    old_staff_id: int
    old_staff_name: str
    new_staff_id: int
    new_staff_name: str
    old_assignment_id: Optional[int] = None
    role: AssignmentRole
    reason: Optional[str] = None
    operator: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
