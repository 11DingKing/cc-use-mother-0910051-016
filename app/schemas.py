from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum

from app.models import (
    StaffType, SessionType, SessionStatus,
    AssignmentRole, AudienceType, WarningType,
    ChangeType, ChangeStatus, ConflictType, RescheduleStatus,
    PointSourceType, ContentVersionStatus, ErratumStatus,
    ContentConfirmationStatus, SubstitutionStatus
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


# ---------------------------------------------------------------------------
# 主题内容版本化
# ---------------------------------------------------------------------------

class ContentSegmentInput(BaseModel):
    """发布版本时提交的必讲段落清单项"""
    segment_key: str
    title: str
    body: str
    is_required: bool = True
    sort_order: int = 0


class ContentSegment(ContentSegmentInput):
    id: int
    content_hash: str

    class Config:
        from_attributes = True


class ContentVersionCreate(BaseModel):
    age_min: int = Field(ge=0, le=120)
    age_max: int = Field(ge=0, le=120)
    title: Optional[str] = None
    content_text: str
    required_segments: List[ContentSegmentInput] = []
    sensitivity_notes: Optional[str] = None
    effective_from: datetime
    effective_to: Optional[datetime] = None
    created_by: Optional[str] = None


class ContentVersionUpdate(BaseModel):
    """仅草稿版本可修改；已发布版本内容冻结，拒绝任何内容字段修改"""
    age_min: Optional[int] = Field(None, ge=0, le=120)
    age_max: Optional[int] = Field(None, ge=0, le=120)
    title: Optional[str] = None
    content_text: Optional[str] = None
    required_segments: Optional[List[ContentSegmentInput]] = None
    sensitivity_notes: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None


class ContentVersion(BaseModel):
    id: int
    theme_id: int
    version_number: int
    status: ContentVersionStatus
    title: Optional[str] = None
    age_min: int
    age_max: int
    content_text: str
    required_segments: List[ContentSegment] = []
    sensitivity_notes: Optional[str] = None
    effective_from: datetime
    effective_to: Optional[datetime] = None
    published_at: Optional[datetime] = None
    withdrawn_at: Optional[datetime] = None
    withdraw_reason: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ContentVersionWithdraw(BaseModel):
    reason: str
    operator: str


class ContentVersionWithdrawResult(ContentVersion):
    affected_pending_sessions: int = 0


class ErratumCreate(BaseModel):
    target_item_id: Optional[int] = None
    severity: str = "一般"
    old_text: Optional[str] = None
    new_text: str
    reason: Optional[str] = None
    issued_by: Optional[str] = None
    supersedes_erratum_id: Optional[int] = None
    # 是否要求引用该版本且未开始的场次重新确认
    require_reconfirm: bool = True


class Erratum(BaseModel):
    id: int
    content_version_id: int
    erratum_no: int
    target_item_id: Optional[int] = None
    severity: str
    old_text: Optional[str] = None
    new_text: str
    reason: Optional[str] = None
    status: ErratumStatus
    issued_by: Optional[str] = None
    issued_at: datetime
    supersedes_erratum_id: Optional[int] = None

    class Config:
        from_attributes = True


class ErratumChainView(Erratum):
    """勘误链条目：勘误本体 + 本场次的送达/知悉情况 + 链条指向（扁平结构）"""
    superseded_by_id: Optional[int] = None
    delivered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    note: Optional[str] = None


class ContentConfirmRequest(BaseModel):
    confirmed_by: Optional[str] = None


class ReconfirmRequest(BaseModel):
    operator: str
    # 指定重新确认所依据的内容版本；不传则使用主题当前生效版本
    target_version_id: Optional[int] = None
    reason: Optional[str] = None


class SchoolRejectRequest(BaseModel):
    rejected_by: str
    reason: Optional[str] = None


class ErratumAckRequest(BaseModel):
    acknowledged_by: str
    note: Optional[str] = None


class FrozenChecklistItem(BaseModel):
    item_id: int
    segment_key: str
    title: str
    body: str
    is_required: bool
    content_hash: str
    sort_order: int


class ContentConfirmation(BaseModel):
    id: int
    session_id: int
    content_version_id: int
    version_number: int
    status: ContentConfirmationStatus
    frozen_age_min: int
    frozen_age_max: int
    content_hash: str
    confirmed_by: Optional[str] = None
    confirmed_at: datetime
    reconfirm_reason: Optional[str] = None
    school_response_at: Optional[datetime] = None
    superseded_by_id: Optional[int] = None
    checklist: List[FrozenChecklistItem] = []
    errata_chain: List[ErratumChainView] = []

    class Config:
        from_attributes = True


class SessionContentStatus(BaseModel):
    """场次内容状态总览：当前绑定/冻结版本与后续勘误链"""
    session_id: int
    session_title: str
    session_status: SessionStatus
    theme_id: int
    current_confirmation_id: Optional[int] = None
    content_version_id: Optional[int] = None
    version_number: Optional[int] = None
    confirmation_status: Optional[ContentConfirmationStatus] = None
    content_hash: Optional[str] = None
    has_pending_errata: bool = False
    pending_errata_count: int = 0
    current_available_version_id: Optional[int] = None
    current_available_version_number: Optional[int] = None
    needs_reconfirm: bool = False
    frozen: Optional[ContentConfirmation] = None


class AvailableContentVersion(BaseModel):
    """当前可用于新场次确认的内容版本"""
    theme_id: int
    theme_name: str
    version_id: int
    version_number: int
    title: Optional[str] = None
    age_min: int
    age_max: int
    effective_from: datetime
    effective_to: Optional[datetime] = None
    sensitivity_notes: Optional[str] = None
    open_errata_count: int = 0
    segment_count: int = 0


class SubstitutionCreate(BaseModel):
    assignment_id: int
    substitute_staff_id: Optional[int] = None
    reason: Optional[str] = None
    requested_by: Optional[str] = None


class SubstitutionArrive(BaseModel):
    substitute_staff_id: int
    operator: str


class SubstitutionAction(BaseModel):
    operator: str


class GuideSubstitutionOut(BaseModel):
    id: int
    session_id: int
    assignment_id: int
    original_staff_id: int
    original_staff_name: str
    substitute_staff_id: Optional[int] = None
    substitute_staff_name: Optional[str] = None
    role: AssignmentRole
    reason: Optional[str] = None
    status: SubstitutionStatus
    requested_by: Optional[str] = None
    requested_at: datetime
    substituted_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    class Config:
        from_attributes = True
