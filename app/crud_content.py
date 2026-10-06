"""讲解词版本发布、场次内容冻结、勘误链与人员替换的核心逻辑。

证据原则：
- 版本一经发布即不可修改，只能发布新版本或撤回；
- 场次确认时生成不可变快照（只追加新冻结行，旧行保留）；
- 紧急勘误追加在版本上形成勘误链，已结束场次不再产生待办，证据不改写。
"""
import hashlib
import json
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app import schemas
from app.models import (
    Theme, Session, Assignment, Staff,
    ContentVersion, ContentSection, ContentErratum,
    SessionContentFreeze, SessionErrataAck, StaffReplacement,
    VersionStatus, ErrataSeverity, ErrataStatus,
    FreezeScheduleState, SchoolResponse, ErrataAckStatus,
    SessionStatus, AssignmentRole,
)


# ------------------------------ 工具函数 ------------------------------

def _as_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """库内既有时间均为 naive（SQLite 不加时区），统一去掉 tzinfo 以便比较。"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str)


def compute_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _section_payload(section: ContentSection) -> dict:
    return {
        "section_no": section.section_no,
        "title": section.title,
        "body": section.body,
        "is_required": section.is_required,
    }


def _version_content_payload(version: ContentVersion) -> dict:
    return {
        "theme_id": version.theme_id,
        "version_no": version.version_no,
        "min_age": version.min_age,
        "max_age": version.max_age,
        "effective_from": _as_naive(version.effective_from).isoformat() if version.effective_from else None,
        "effective_to": _as_naive(version.effective_to).isoformat() if version.effective_to else None,
        "sections": [_section_payload(s) for s in sorted(version.sections, key=lambda x: x.section_no)],
    }


def _compute_version_hash(version: ContentVersion) -> str:
    return compute_hash(_version_content_payload(version))


def build_snapshot(version: ContentVersion, audience_age: Optional[int]) -> dict:
    """学校确认时看到的内容清单（之后不再变化）。"""
    theme = version.theme
    return {
        "theme": {"id": theme.id, "name": theme.name} if theme else {"id": version.theme_id},
        "version": {
            "id": version.id,
            "version_no": version.version_no,
            "min_age": version.min_age,
            "max_age": version.max_age,
            "effective_from": _as_naive(version.effective_from).isoformat() if version.effective_from else None,
            "effective_to": _as_naive(version.effective_to).isoformat() if version.effective_to else None,
            "content_hash": version.content_hash,
        },
        "audience_age": audience_age,
        "sections": [_section_payload(s) for s in sorted(version.sections, key=lambda x: x.section_no)],
        "frozen_at": datetime.utcnow().isoformat(),
    }


def parse_snapshot(freeze: SessionContentFreeze) -> dict:
    try:
        return json.loads(freeze.frozen_snapshot)
    except (TypeError, ValueError):
        return {}


def verify_freeze_hash(freeze: SessionContentFreeze) -> bool:
    """重新计算快照哈希，核验冻结证据未被篡改。"""
    try:
        payload = json.loads(freeze.frozen_snapshot)
    except (TypeError, ValueError):
        return False
    return compute_hash(payload) == freeze.content_hash


# ------------------------------ 版本管理 ------------------------------

def get_version(db: Session, version_id: int) -> Optional[ContentVersion]:
    return db.query(ContentVersion).options(
        joinedload(ContentVersion.theme),
        joinedload(ContentVersion.sections),
        joinedload(ContentVersion.erratas),
    ).filter(ContentVersion.id == version_id).first()


def list_versions(db: Session, theme_id: Optional[int] = None,
                  status: Optional[VersionStatus] = None,
                  effective_at: Optional[datetime] = None,
                  audience_age: Optional[int] = None) -> List[ContentVersion]:
    query = db.query(ContentVersion).options(
        joinedload(ContentVersion.theme),
        joinedload(ContentVersion.sections),
        joinedload(ContentVersion.erratas),
    )
    if theme_id is not None:
        query = query.filter(ContentVersion.theme_id == theme_id)
    if status is not None:
        query = query.filter(ContentVersion.status == status)
    if effective_at is not None:
        effective_at = _as_naive(effective_at)
        query = query.filter(ContentVersion.effective_from <= effective_at,
                             ContentVersion.effective_to >= effective_at)
    if audience_age is not None:
        query = query.filter(ContentVersion.min_age <= audience_age,
                             ContentVersion.max_age >= audience_age)
    return query.order_by(ContentVersion.theme_id, ContentVersion.version_no.desc()).all()


def get_current_version(db: Session, theme_id: int,
                        at: Optional[datetime] = None) -> Optional[ContentVersion]:
    """某主题当前可用版本：指定时刻处于生效区间内、最新发布的版本。"""
    at = _as_naive(at) or datetime.utcnow()
    versions = db.query(ContentVersion).options(
        joinedload(ContentVersion.theme),
        joinedload(ContentVersion.sections),
        joinedload(ContentVersion.erratas),
    ).filter(
        ContentVersion.theme_id == theme_id,
        ContentVersion.status == VersionStatus.PUBLISHED,
        ContentVersion.effective_from <= at,
        ContentVersion.effective_to >= at,
    ).order_by(ContentVersion.version_no.desc()).all()
    return versions[0] if versions else None


def _next_version_no(db: Session, theme_id: int) -> int:
    last = db.query(ContentVersion).filter(
        ContentVersion.theme_id == theme_id
    ).order_by(ContentVersion.version_no.desc()).first()
    return (last.version_no + 1) if last else 1


def create_version(db: Session, theme_id: int,
                   data: schemas.ContentVersionCreate,
                   operator: Optional[str] = None) -> Tuple[Optional[ContentVersion], List[str]]:
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        return None, ["主题不存在"]

    effective_from = _as_naive(data.effective_from)
    effective_to = _as_naive(data.effective_to)
    if effective_from >= effective_to:
        return None, ["生效区间不合法：生效开始必须早于生效结束"]
    if data.min_age > data.max_age:
        return None, ["适用年龄不合法：下限不能大于上限"]
    if not data.sections:
        return None, ["至少需要一个讲解段落"]
    if not any(s.is_required for s in data.sections):
        return None, ["必须包含至少一个必讲段落"]

    version = ContentVersion(
        theme_id=theme_id,
        version_no=_next_version_no(db, theme_id),
        status=VersionStatus.DRAFT,
        min_age=data.min_age,
        max_age=data.max_age,
        effective_from=effective_from,
        effective_to=effective_to,
        change_note=data.change_note,
        created_by=operator,
    )
    for idx, section_in in enumerate(data.sections, start=1):
        version.sections.append(ContentSection(
            section_no=section_in.section_no or idx,
            title=section_in.title,
            body=section_in.body,
            is_required=section_in.is_required,
        ))
    version.sections.sort(key=lambda s: s.section_no)

    db.add(version)
    db.flush()
    version.content_hash = _compute_version_hash(version)
    db.commit()
    db.refresh(version)
    return version, []


def update_draft(db: Session, version_id: int,
                 data: schemas.ContentVersionDraftUpdate
                 ) -> Tuple[Optional[ContentVersion], List[str]]:
    version = get_version(db, version_id)
    if not version:
        return None, ["版本不存在"]
    if version.status != VersionStatus.DRAFT:
        return None, [f"版本当前为{version.status.value}状态，不可修改；请新建版本"]

    payload = data.model_dump(exclude_unset=True)
    sections_data = payload.pop("sections", None)

    min_age = payload.get("min_age", version.min_age)
    max_age = payload.get("max_age", version.max_age)
    effective_from = _as_naive(payload.get("effective_from", version.effective_from))
    effective_to = _as_naive(payload.get("effective_to", version.effective_to))
    if min_age > max_age:
        return None, ["适用年龄不合法：下限不能大于上限"]
    if effective_from >= effective_to:
        return None, ["生效区间不合法：生效开始必须早于生效结束"]

    for field in ("min_age", "max_age", "change_note"):
        if field in payload:
            setattr(version, field, payload[field])
    if "effective_from" in payload:
        version.effective_from = effective_from
    if "effective_to" in payload:
        version.effective_to = effective_to

    if sections_data is not None:
        if not sections_data:
            return None, ["至少需要一个讲解段落"]
        if not any(s["is_required"] for s in sections_data):
            return None, ["必须包含至少一个必讲段落"]
        db.query(ContentSection).filter(ContentSection.version_id == version.id).delete()
        db.flush()
        for idx, s in enumerate(sections_data, start=1):
            db.add(ContentSection(
                version_id=version.id,
                section_no=s.get("section_no") or idx,
                title=s["title"],
                body=s["body"],
                is_required=s["is_required"],
            ))
        db.flush()

    version.content_hash = _compute_version_hash(version)
    db.commit()
    db.refresh(version)
    return version, []


def publish_version(db: Session, version_id: int, operator: str
                    ) -> Tuple[Optional[ContentVersion], List[str]]:
    version = get_version(db, version_id)
    if not version:
        return None, ["版本不存在"]
    if version.status != VersionStatus.DRAFT:
        return None, [f"仅草稿版本可发布，当前为{version.status.value}"]
    if not version.sections:
        return None, ["版本没有任何段落，无法发布"]

    version.status = VersionStatus.PUBLISHED
    version.published_by = operator
    version.published_at = datetime.utcnow()
    db.flush()

    # 通知使用该主题、尚未开始且冻结在旧版本上的场次：有新版本待学校确认
    pending_freezes = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session)
    ).filter(
        SessionContentFreeze.is_current.is_(True),
        SessionContentFreeze.theme_id == version.theme_id,
        SessionContentFreeze.theme_version_id != version.id,
    ).all()
    for freeze in pending_freezes:
        sess = freeze.session
        if not sess or sess.status == SessionStatus.COMPLETED or sess.status == SessionStatus.CANCELLED:
            continue
        if _as_naive(sess.start_time) and not _version_covers(version, _as_naive(sess.start_time),
                                                              freeze.audience_age):
            continue
        freeze.target_version_id = version.id
        freeze.school_response = SchoolResponse.PENDING
        freeze.responded_at = None
        freeze.response_note = None
        _recompute_freeze_state(freeze)

    db.commit()
    db.refresh(version)
    return version, []


def _version_covers(version: ContentVersion, at: datetime,
                    audience_age: Optional[int]) -> bool:
    if not (_as_naive(version.effective_from) <= at <= _as_naive(version.effective_to)):
        return False
    if audience_age is not None and not (version.min_age <= audience_age <= version.max_age):
        return False
    return True


def withdraw_version(db: Session, version_id: int, operator: str, reason: str
                     ) -> Tuple[Optional[ContentVersion], List[str]]:
    """撤回版本：已结束场次的证据不动；未开始场次进入"版本撤回待重新确认"。"""
    version = get_version(db, version_id)
    if not version:
        return None, ["版本不存在"]
    if version.status != VersionStatus.PUBLISHED:
        return None, [f"仅已发布版本可撤回，当前为{version.status.value}"]
    if not reason or not reason.strip():
        return None, ["撤回原因必填"]

    version.status = VersionStatus.WITHDRAWN
    version.withdrawn_by = operator
    version.withdraw_reason = reason
    version.withdrawn_at = datetime.utcnow()

    # 其他冻结若正把该版本当作"待确认的新版本"，撤回后改指向其他可替代版本
    waiting_freezes = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session)
    ).filter(
        SessionContentFreeze.is_current.is_(True),
        SessionContentFreeze.target_version_id == version.id,
        SessionContentFreeze.school_response == SchoolResponse.PENDING,
        SessionContentFreeze.theme_version_id != version.id,
    ).all()
    for freeze in waiting_freezes:
        sess = freeze.session
        alt = None
        if sess and sess.status not in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
            alt = _latest_published_sibling(
                db, version,
                at=_as_naive(sess.start_time) or datetime.utcnow(),
                audience_age=freeze.audience_age,
            )
            # 不把自己刚撤回的版本指回；且不能指向当前冻结版本（无更新意义）
            if alt and alt.id == freeze.theme_version_id:
                alt = None
        freeze.target_version_id = alt.id if alt else None
        if alt is None:
            freeze.school_response = SchoolResponse.ACCEPTED
        _recompute_freeze_state(freeze)

    current_freezes = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session)
    ).filter(
        SessionContentFreeze.is_current.is_(True),
        SessionContentFreeze.theme_version_id == version.id,
    ).all()
    for freeze in current_freezes:
        sess = freeze.session
        if not sess or sess.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
            continue
        replacement = _latest_published_sibling(
            db, version,
            at=_as_naive(sess.start_time) or datetime.utcnow(),
            audience_age=freeze.audience_age,
        )
        # 撤回是强制动作：无论是否有替代版本，未开始场次都必须重新处理
        freeze.target_version_id = replacement.id if replacement else None
        freeze.school_response = SchoolResponse.PENDING
        freeze.responded_at = None
        freeze.response_note = None
        _recompute_freeze_state(freeze)

    db.commit()
    db.refresh(version)
    return version, []


def _latest_published_sibling(db: Session, version: ContentVersion,
                              at: datetime,
                              audience_age: Optional[int]) -> Optional[ContentVersion]:
    candidates = db.query(ContentVersion).filter(
        ContentVersion.theme_id == version.theme_id,
        ContentVersion.status == VersionStatus.PUBLISHED,
        ContentVersion.id != version.id,
        ContentVersion.effective_from <= at,
        ContentVersion.effective_to >= at,
    ).order_by(ContentVersion.version_no.desc()).all()
    for candidate in candidates:
        if audience_age is None or (candidate.min_age <= audience_age <= candidate.max_age):
            return candidate
    return candidates[0] if candidates else None


# ------------------------------ 勘误链 ------------------------------

def list_erratas(db: Session, version_id: int,
                 status: Optional[ErrataStatus] = None) -> List[ContentErratum]:
    query = db.query(ContentErratum).options(
        joinedload(ContentErratum.section)
    ).filter(ContentErratum.theme_version_id == version_id)
    if status is not None:
        query = query.filter(ContentErratum.status == status)
    return query.order_by(ContentErratum.erratum_no).all()


def issue_erratum(db: Session, version_id: int,
                  data: schemas.ErratumCreate) -> Tuple[Optional[ContentErratum], List[str]]:
    """发布紧急勘误。同段落上一条生效勘误自动转为"已被取代"，形成勘误链。

    已结束场次：勘误仍挂在版本上（可审计），但不产生待回应；
    未开始场次：生成待回应记录并进入"勘误待回应"。
    """
    version = get_version(db, version_id)
    if not version:
        return None, ["版本不存在"]
    if version.status != VersionStatus.PUBLISHED:
        return None, ["仅已发布版本可发布勘误；草稿请直接修改，已撤回版本请重新确认新版本"]
    if not data.new_text or not data.new_text.strip():
        return None, ["勘误正文不能为空"]

    section = None
    if data.section_id is not None:
        section = db.query(ContentSection).filter(
            ContentSection.id == data.section_id,
            ContentSection.version_id == version.id,
        ).first()
        if not section:
            return None, ["段落不存在或不属于该版本"]

    erratum = ContentErratum(
        theme_version_id=version.id,
        erratum_no=db.query(ContentErratum).filter(
            ContentErratum.theme_version_id == version.id
        ).count() + 1,
        section_id=section.id if section else None,
        title=data.title,
        old_text=data.old_text,
        new_text=data.new_text,
        reason=data.reason,
        severity=data.severity,
        status=ErrataStatus.ACTIVE,
        issued_by=data.issued_by,
    )

    # 同段旧勘误被新勘误取代
    if section is not None:
        previous = db.query(ContentErratum).filter(
            ContentErratum.theme_version_id == version.id,
            ContentErratum.section_id == section.id,
            ContentErratum.status == ErrataStatus.ACTIVE,
        ).order_by(ContentErratum.erratum_no.desc()).first()
        if previous:
            previous.status = ErrataStatus.SUPERSEDED
            erratum.supersedes_id = previous.id
            # 旧勘误上尚未回应的场次待办直接指向新勘误（见下方批量处理）

    db.add(erratum)
    db.flush()

    current_freezes = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session)
    ).filter(
        SessionContentFreeze.is_current.is_(True),
        SessionContentFreeze.theme_version_id == version.id,
    ).all()
    for freeze in current_freezes:
        sess = freeze.session
        if not sess:
            continue
        terminal = sess.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED)
        if terminal:
            continue  # 已结束/已取消：不产生待办，证据不改写

        # 同段旧勘误若仍待回应，转为"不适用"（被新勘误取代）
        if erratum.supersedes_id is not None:
            old_pending = db.query(SessionErrataAck).filter(
                SessionErrataAck.freeze_id == freeze.id,
                SessionErrataAck.erratum_id == erratum.supersedes_id,
                SessionErrataAck.status == ErrataAckStatus.PENDING,
            ).first()
            if old_pending:
                old_pending.status = ErrataAckStatus.IRRELEVANT
                old_pending.note = "已被更新的勘误取代"

        exists = db.query(SessionErrataAck).filter(
            SessionErrataAck.freeze_id == freeze.id,
            SessionErrataAck.erratum_id == erratum.id,
        ).first()
        if not exists:
            db.add(SessionErrataAck(
                freeze_id=freeze.id,
                erratum_id=erratum.id,
                status=ErrataAckStatus.PENDING,
            ))
        db.flush()
        _recompute_freeze_state(freeze)

    db.commit()
    db.refresh(erratum)
    return erratum, []


# ------------------------------ 场次冻结 ------------------------------

def _sync_lock(freeze: SessionContentFreeze, db: Session) -> SessionContentFreeze:
    """场次一旦已完成/已取消，冻结证据立即锁定（状态读取时同步一次）。"""
    sess = freeze.session
    if sess and sess.status == SessionStatus.COMPLETED and \
            freeze.schedule_state != FreezeScheduleState.COMPLETED_LOCKED:
        freeze.schedule_state = FreezeScheduleState.COMPLETED_LOCKED
        db.commit()
        db.refresh(freeze)
    return freeze


def get_current_freeze(db: Session, session_id: int) -> Optional[SessionContentFreeze]:
    freeze = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session),
        joinedload(SessionContentFreeze.theme),
        joinedload(SessionContentFreeze.content_version),
        joinedload(SessionContentFreeze.target_version),
    ).filter(
        SessionContentFreeze.session_id == session_id,
        SessionContentFreeze.is_current.is_(True),
    ).order_by(SessionContentFreeze.id.desc()).first()
    return _sync_lock(freeze, db) if freeze else None


def list_freezes(db: Session, session_id: int) -> List[SessionContentFreeze]:
    freezes = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session),
        joinedload(SessionContentFreeze.theme),
        joinedload(SessionContentFreeze.content_version),
        joinedload(SessionContentFreeze.target_version),
    ).filter(
        SessionContentFreeze.session_id == session_id,
    ).order_by(SessionContentFreeze.id.desc()).all()
    return [_sync_lock(f, db) for f in freezes]


def get_freeze(db: Session, freeze_id: int) -> Optional[SessionContentFreeze]:
    freeze = db.query(SessionContentFreeze).options(
        joinedload(SessionContentFreeze.session),
        joinedload(SessionContentFreeze.theme),
        joinedload(SessionContentFreeze.content_version),
        joinedload(SessionContentFreeze.target_version),
    ).filter(SessionContentFreeze.id == freeze_id).first()
    return _sync_lock(freeze, db) if freeze else None


def confirm_session_content(db: Session, session_id: int,
                            data: schemas.FreezeCreate
                            ) -> Tuple[Optional[SessionContentFreeze], List[str]]:
    """学校确认场次：冻结当时发布版本的内容清单（含适用年龄、必讲段落）。"""
    sess = db.query(Session).filter(Session.id == session_id).first()
    if not sess:
        return None, ["场次不存在"]
    if sess.status == SessionStatus.COMPLETED:
        return None, ["场次已结束，证据已锁定，不能重新确认内容"]
    if sess.status == SessionStatus.CANCELLED:
        return None, ["场次已取消，不能确认内容"]

    version = get_current_version(db, sess.theme_id, at=sess.start_time)
    if not version:
        return None, ["该主题在场次开始时刻没有处于生效区间的已发布版本，无法确认"]

    if data.audience_age is not None and not (version.min_age <= data.audience_age <= version.max_age):
        return None, [
            f"版本 v{version.version_no} 适用年龄为 {version.min_age}-{version.max_age} 岁，"
            f"与本次受众年龄 {data.audience_age} 岁不符"
        ]

    # 旧冻结行保留为历史证据，仅取消 current 标记
    db.query(SessionContentFreeze).filter(
        SessionContentFreeze.session_id == session_id,
        SessionContentFreeze.is_current.is_(True),
    ).update({"is_current": False})

    snapshot = build_snapshot(version, data.audience_age)
    freeze = SessionContentFreeze(
        session_id=session_id,
        theme_id=sess.theme_id,
        theme_version_id=version.id,
        audience_age=data.audience_age,
        is_current=True,
        frozen_snapshot=json.dumps(snapshot, ensure_ascii=False, default=str),
        content_hash=compute_hash(snapshot),
        schedule_state=FreezeScheduleState.CONFIRMED,
        school_confirmed=True,
        confirmed_by=data.confirmed_by,
        school_response=SchoolResponse.ACCEPTED,
    )
    db.add(freeze)
    db.flush()

    # 若版本上已有生效勘误，未开始场次同样需要逐条回应
    for erratum in list_erratas(db, version.id, status=ErrataStatus.ACTIVE):
        db.add(SessionErrataAck(
            freeze_id=freeze.id, erratum_id=erratum.id,
            status=ErrataAckStatus.PENDING,
        ))
    db.flush()
    _recompute_freeze_state(freeze)

    db.commit()
    db.refresh(freeze)
    return freeze, []


def _recompute_freeze_state(freeze: SessionContentFreeze) -> FreezeScheduleState:
    """根据场次状态、改期/新版本待办与勘误待回应，推导唯一确定状态。"""
    sess = freeze.session
    if sess and sess.status == SessionStatus.COMPLETED:
        freeze.schedule_state = FreezeScheduleState.COMPLETED_LOCKED
        return freeze.schedule_state

    if freeze.pending_start_time is not None:
        freeze.schedule_state = FreezeScheduleState.RESCHEDULED_PENDING
        return freeze.schedule_state

    # 冻结所依据的版本被撤回是强制状态：替代版本接受前一直待重新确认
    frozen_withdrawn = (
        freeze.content_version is not None
        and freeze.content_version.status == VersionStatus.WITHDRAWN
    )
    if frozen_withdrawn:
        freeze.schedule_state = FreezeScheduleState.VERSION_WITHDRAWN_PENDING
        return freeze.schedule_state

    if freeze.school_response == SchoolResponse.PENDING and freeze.target_version_id is not None:
        freeze.schedule_state = FreezeScheduleState.UPDATE_PENDING
        return freeze.schedule_state

    if freeze.school_response == SchoolResponse.DECLINED and freeze.target_version_id is not None:
        freeze.schedule_state = FreezeScheduleState.UPDATE_DECLINED
        return freeze.schedule_state

    pending_ack = any(a.status == ErrataAckStatus.PENDING for a in freeze.erratum_acks)
    if pending_ack:
        freeze.schedule_state = FreezeScheduleState.ERRATA_PENDING
        return freeze.schedule_state

    freeze.schedule_state = FreezeScheduleState.CONFIRMED
    return freeze.schedule_state


# ------------------------------ 改期 ------------------------------

def request_reschedule(db: Session, freeze_id: int,
                       data: schemas.RescheduleRequest
                       ) -> Tuple[Optional[SessionContentFreeze], List[str]]:
    freeze = get_freeze(db, freeze_id)
    if not freeze:
        return None, ["冻结记录不存在"]
    if not freeze.is_current:
        return None, ["该冻结清单已被新的确认取代，不能在历史记录上操作"]
    sess = freeze.session
    if not sess:
        return None, ["关联场次不存在"]
    if sess.status == SessionStatus.COMPLETED:
        return None, ["场次已结束，不能改期"]
    if sess.status == SessionStatus.CANCELLED:
        return None, ["场次已取消，不能改期"]

    new_start = _as_naive(data.new_start_time)
    new_end = _as_naive(data.new_end_time)
    if new_start >= new_end:
        return None, ["改期时间不合法：开始时间必须早于结束时间"]

    freeze.pending_start_time = new_start
    freeze.pending_end_time = new_end
    freeze.reschedule_reason = data.reason
    freeze.requested_by = data.requester
    freeze.reschedule_reviewed_by = None
    freeze.reschedule_reviewed_at = None
    _recompute_freeze_state(freeze)
    db.commit()
    db.refresh(freeze)
    return freeze, []


def review_reschedule(db: Session, freeze_id: int,
                      data: schemas.RescheduleReview
                      ) -> Tuple[Optional[SessionContentFreeze], List[str]]:
    freeze = get_freeze(db, freeze_id)
    if not freeze:
        return None, ["冻结记录不存在"]
    if not freeze.is_current:
        return None, ["该冻结清单已被新的确认取代，不能在历史记录上操作"]
    if freeze.pending_start_time is None:
        return None, ["该场次没有待审核的改期申请"]

    sess = freeze.session
    if data.approved:
        if sess.status == SessionStatus.COMPLETED:
            return None, ["场次已结束，不能审核改期"]
        new_start = freeze.pending_start_time

        # 新时间必须仍被冻结版本覆盖，否则要改指向当前可用版本供学校重新确认
        frozen_version = freeze.content_version
        covers = frozen_version and _version_covers(
            frozen_version, _as_naive(new_start), freeze.audience_age
        )
        if not covers:
            alt = get_current_version(db, freeze.theme_id, at=new_start)
            if not alt:
                return None, ["改期后的时间没有处于生效区间的内容版本，请先发布新版本或调整改期时间"]
            sess.start_time = freeze.pending_start_time
            sess.end_time = freeze.pending_end_time
            freeze.target_version_id = alt.id
            freeze.school_response = SchoolResponse.PENDING
            freeze.responded_at = None
            freeze.response_note = None
        else:
            sess.start_time = freeze.pending_start_time
            sess.end_time = freeze.pending_end_time

    freeze.pending_start_time = None
    freeze.pending_end_time = None
    freeze.reschedule_reviewed_by = data.reviewer
    freeze.reschedule_reviewed_at = datetime.utcnow()
    if not data.approved:
        freeze.reschedule_reason = (freeze.reschedule_reason or "") + f"（审核未通过：{data.comment or ''}）"
    _recompute_freeze_state(freeze)
    db.commit()
    db.refresh(freeze)
    return freeze, []


# ------------------------------ 学校对新版本的决定 ------------------------------

def decide_new_version(db: Session, freeze_id: int,
                       data: schemas.NewVersionDecision
                       ) -> Tuple[Optional[SessionContentFreeze], List[str]]:
    freeze = get_freeze(db, freeze_id)
    if not freeze:
        return None, ["冻结记录不存在"]
    if not freeze.is_current:
        return None, ["该冻结清单已被新的确认取代，不能在历史记录上操作"]
    sess = freeze.session
    if not sess:
        return None, ["关联场次不存在"]
    if sess.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
        return None, ["场次已结束或取消，不能再确认新版本"]
    if freeze.school_response != SchoolResponse.PENDING or not freeze.target_version_id:
        return None, ["当前没有待学校回应的新版本"]

    target = get_version(db, freeze.target_version_id)
    if not target or target.status != VersionStatus.PUBLISHED:
        return None, ["目标版本不可用（未发布或已撤回）"]

    freeze.school_response = SchoolResponse.ACCEPTED if data.accepted else SchoolResponse.DECLINED
    freeze.responded_at = datetime.utcnow()
    freeze.response_note = data.note

    if data.accepted:
        # 接受：旧冻结行留痕，按目标版本冻结一份新的当前清单
        freeze.is_current = False
        db.flush()

        snapshot = build_snapshot(target, freeze.audience_age)
        new_freeze = SessionContentFreeze(
            session_id=sess.id,
            theme_id=target.theme_id,
            theme_version_id=target.id,
            audience_age=freeze.audience_age,
            is_current=True,
            frozen_snapshot=json.dumps(snapshot, ensure_ascii=False, default=str),
            content_hash=compute_hash(snapshot),
            schedule_state=FreezeScheduleState.CONFIRMED,
            school_confirmed=True,
            confirmed_by=data.responder,
            school_response=SchoolResponse.ACCEPTED,
        )
        db.add(new_freeze)
        db.flush()
        for erratum in list_erratas(db, target.id, status=ErrataStatus.ACTIVE):
            db.add(SessionErrataAck(
                freeze_id=new_freeze.id, erratum_id=erratum.id,
                status=ErrataAckStatus.PENDING,
            ))
        db.flush()
        _recompute_freeze_state(new_freeze)
        db.commit()
        db.refresh(new_freeze)
        return new_freeze, []

    _recompute_freeze_state(freeze)
    db.commit()
    db.refresh(freeze)
    return freeze, []


# ------------------------------ 勘误回应 ------------------------------

def decide_erratum(db: Session, freeze_id: int, erratum_id: int,
                   data: schemas.ErrataDecision
                   ) -> Tuple[Optional[SessionErrataAck], List[str]]:
    freeze = get_freeze(db, freeze_id)
    if not freeze:
        return None, ["冻结记录不存在"]
    if not freeze.is_current:
        return None, ["该冻结清单已被新的确认取代，不能在历史记录上操作"]
    sess = freeze.session
    if sess and sess.status == SessionStatus.COMPLETED:
        return None, ["场次已结束，勘误证据已锁定，不能更改回应"]
    if sess and sess.status == SessionStatus.CANCELLED:
        return None, ["场次已取消，不能回应勘误"]

    ack = db.query(SessionErrataAck).filter(
        SessionErrataAck.freeze_id == freeze_id,
        SessionErrataAck.erratum_id == erratum_id,
    ).first()
    if not ack:
        return None, ["该勘误不适用于本场次或已被取代"]
    if ack.status != ErrataAckStatus.PENDING:
        return None, [f"该勘误已回应（{ack.status.value}），不能重复操作"]

    ack.status = ErrataAckStatus.APPLIED if data.apply else ErrataAckStatus.DECLINED
    ack.decided_by = data.responder
    ack.decided_at = datetime.utcnow()
    ack.note = data.note
    db.flush()
    _recompute_freeze_state(freeze)
    db.commit()
    db.refresh(ack)
    return ack, []


# ------------------------------ 按场次还原 ------------------------------

def replay_freeze(db: Session, freeze: SessionContentFreeze) -> dict:
    """还原冻结清单以及后续勘误链，输出当前讲解时实际生效的段落。"""
    snapshot = parse_snapshot(freeze)
    version = freeze.content_version

    acks = db.query(SessionErrataAck).options(
        joinedload(SessionErrataAck.erratum).joinedload(ContentErratum.section)
    ).filter(SessionErrataAck.freeze_id == freeze.id).all()
    ack_by_erratum = {a.erratum_id: a for a in acks}

    chain = []
    if version:
        chain = db.query(ContentErratum).options(
            joinedload(ContentErratum.section)
        ).filter(
            ContentErratum.theme_version_id == version.id
        ).order_by(ContentErratum.erratum_no).all()

    is_ended = bool(
        freeze.session and freeze.session.status == SessionStatus.COMPLETED
    )

    pending = []
    if not is_ended:
        pending = [e for e in chain
                   if e.id in ack_by_erratum and ack_by_erratum[e.id].status == ErrataAckStatus.PENDING]

    # section_no -> 最后一条"本场接受"的生效勘误（待回应的仅在未结束场次视为将生效）
    applied_by_section = {}
    applied_global = []
    for erratum in chain:
        ack = ack_by_erratum.get(erratum.id)
        if ack is None:
            continue
        if ack.status == ErrataAckStatus.APPLIED:
            applies = True
        elif ack.status == ErrataAckStatus.PENDING and not is_ended:
            applies = True
        else:
            applies = False
        if not applies:
            continue
        if erratum.section_id is not None and erratum.section:
            applied_by_section[erratum.section.section_no] = erratum
        else:
            applied_global.append(erratum)

    effective_sections = []
    section_nos = {s["section_no"] for s in snapshot.get("sections", [])}
    for item in snapshot.get("sections", []):
        erratum = applied_by_section.get(item["section_no"])
        entry = dict(item)
        entry_erratas = []
        if erratum:
            entry["body"] = erratum.new_text
            entry_erratas = [e for e in chain
                             if e.section_id == erratum.section_id
                             and e.id in ack_by_erratum]
        effective_sections.append({
            "section_no": entry["section_no"],
            "title": entry["title"],
            "body": entry["body"],
            "is_required": entry["is_required"],
            "erratas": entry_erratas,
        })

    # 整段新增类勘误（未关联段落）追加在末尾
    for erratum in applied_global:
        if erratum.section_id is None:
            effective_sections.append({
                "section_no": None,
                "title": erratum.title,
                "body": erratum.new_text,
                "is_required": True,
                "erratas": [erratum],
            })

    return {
        "snapshot": snapshot,
        "errata_chain": chain,
        "pending_erratas": pending,
        "effective_sections": effective_sections,
        "hash_verified": verify_freeze_hash(freeze),
        "section_nos": sorted(n for n in section_nos if n is not None),
    }


# ------------------------------ 讲解员临时替换 ------------------------------

def list_replacements(db: Session, session_id: int) -> List[StaffReplacement]:
    return db.query(StaffReplacement).options(
        joinedload(StaffReplacement.old_staff),
        joinedload(StaffReplacement.new_staff),
    ).filter(
        StaffReplacement.session_id == session_id
    ).order_by(StaffReplacement.id.desc()).all()


def replace_staff(db: Session, session_id: int, old_staff_id: Optional[int],
                  new_staff_id: int, operator: str,
                  reason: Optional[str]) -> Tuple[Optional[StaffReplacement], List[str]]:
    """临时替换讲解员/讲师：只追加替换记录，内容冻结证据不受影响。"""
    from app import crud

    sess = db.query(Session).filter(Session.id == session_id).first()
    if not sess:
        return None, ["场次不存在"]
    if sess.status == SessionStatus.COMPLETED:
        return None, ["场次已结束，不能临时替换人员"]
    if sess.status == SessionStatus.CANCELLED:
        return None, ["场次已取消，不能替换人员"]

    new_staff = db.query(Staff).filter(Staff.id == new_staff_id).first()
    if not new_staff:
        return None, ["新人员不存在"]
    if not new_staff.is_active:
        return None, ["新人员已停用"]

    assignment_query = db.query(Assignment).filter(Assignment.session_id == session_id)
    if old_staff_id is not None:
        assignment_query = assignment_query.filter(Assignment.staff_id == old_staff_id)
    old_assignment = assignment_query.order_by(Assignment.is_primary.desc(), Assignment.id.asc()).first()
    if not old_assignment:
        return None, ["找不到被替换人员的排班记录"]
    if old_assignment.staff_id == new_staff_id:
        return None, ["新人员与被替换人员相同"]

    role = old_assignment.role

    # 资格与时间校验
    validation = crud.validate_assignment(db, session_id, new_staff_id, role)
    if not validation.valid:
        return None, validation.errors

    record = StaffReplacement(
        session_id=session_id,
        old_staff_id=old_assignment.staff_id,
        new_staff_id=new_staff_id,
        old_assignment_id=old_assignment.id,
        role=role,
        reason=reason,
        operator=operator,
    )
    db.add(record)
    new_assignment = Assignment(
        session_id=session_id,
        staff_id=new_staff_id,
        role=role,
        is_primary=old_assignment.is_primary,
    )
    db.add(new_assignment)
    db.flush()
    db.delete(old_assignment)
    db.commit()
    db.refresh(record)
    return record, []
