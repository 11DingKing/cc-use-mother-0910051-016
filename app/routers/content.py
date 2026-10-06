"""讲解词版本、场次冻结清单、勘误链与临时替换接口。"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import schemas, crud_content
from app.models import (
    ContentVersion, ContentErratum,
    VersionStatus, ErrataStatus,
)

router = APIRouter(tags=["讲解词版本与场次内容"])


# ------------------------------ 转换函数 ------------------------------

def _erratum_to_schema(erratum: ContentErratum) -> schemas.Erratum:
    return schemas.Erratum(
        id=erratum.id,
        theme_version_id=erratum.theme_version_id,
        erratum_no=erratum.erratum_no,
        section_id=erratum.section_id,
        section_title=erratum.section.title if erratum.section else None,
        title=erratum.title,
        old_text=erratum.old_text,
        new_text=erratum.new_text,
        reason=erratum.reason,
        severity=erratum.severity,
        status=erratum.status,
        supersedes_id=erratum.supersedes_id,
        issued_by=erratum.issued_by,
        issued_at=erratum.issued_at,
    )


def _version_to_schema(db: Session, version: ContentVersion,
                       detail: bool = False) -> schemas.ContentVersionSummary:
    sections = sorted(version.sections, key=lambda s: s.section_no)
    active_erratas = [e for e in version.erratas if e.status == ErrataStatus.ACTIVE]
    base = dict(
        id=version.id,
        theme_id=version.theme_id,
        theme_name=version.theme.name if version.theme else "",
        version_no=version.version_no,
        status=version.status,
        min_age=version.min_age,
        max_age=version.max_age,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        content_hash=version.content_hash,
        change_note=version.change_note,
        created_by=version.created_by,
        published_by=version.published_by,
        published_at=version.published_at,
        withdrawn_by=version.withdrawn_by,
        withdraw_reason=version.withdraw_reason,
        withdrawn_at=version.withdrawn_at,
        section_count=len(sections),
        required_section_count=sum(1 for s in sections if s.is_required),
        active_errata_count=len(active_erratas),
        created_at=version.created_at,
    )
    if not detail:
        return schemas.ContentVersionSummary(**base)
    base["sections"] = [
        schemas.ContentSection(
            id=s.id, section_no=s.section_no, title=s.title,
            body=s.body, is_required=s.is_required,
        ) for s in sections
    ]
    return schemas.ContentVersionDetail(**base)


def _freeze_to_schema(db: Session, freeze, replay: Optional[dict] = None) -> schemas.SessionFreeze:
    if replay is None:
        replay = crud_content.replay_freeze(db, freeze)

    ack_items = []
    acks = sorted(freeze.erratum_acks, key=lambda a: a.id)
    for ack in acks:
        ack_items.append(schemas.ErrataAckItem(
            id=ack.id,
            erratum_id=ack.erratum_id,
            erratum_title=ack.erratum.title if ack.erratum else "",
            severity=ack.erratum.severity if ack.erratum else None,
            status=ack.status,
            decided_by=ack.decided_by,
            decided_at=ack.decided_at,
            note=ack.note,
            created_at=ack.created_at,
        ))

    return schemas.SessionFreeze(
        id=freeze.id,
        session_id=freeze.session_id,
        session_title=freeze.session.title if freeze.session else "",
        theme_id=freeze.theme_id,
        theme_name=freeze.theme.name if freeze.theme else "",
        theme_version_id=freeze.theme_version_id,
        version_no=freeze.content_version.version_no if freeze.content_version else 0,
        audience_age=freeze.audience_age,
        is_current=freeze.is_current,
        content_hash=freeze.content_hash,
        schedule_state=freeze.schedule_state,
        school_confirmed=freeze.school_confirmed,
        confirmed_by=freeze.confirmed_by,
        frozen_at=freeze.frozen_at,
        target_version_id=freeze.target_version_id,
        target_version_no=freeze.target_version.version_no if freeze.target_version else None,
        school_response=freeze.school_response,
        responded_at=freeze.responded_at,
        response_note=freeze.response_note,
        pending_start_time=freeze.pending_start_time,
        pending_end_time=freeze.pending_end_time,
        reschedule_reason=freeze.reschedule_reason,
        requested_by=freeze.requested_by,
        reschedule_reviewed_by=freeze.reschedule_reviewed_by,
        reschedule_reviewed_at=freeze.reschedule_reviewed_at,
        snapshot=replay["snapshot"],
        sections=[
            schemas.FreezeSectionItem(
                section_no=s["section_no"], title=s["title"], body=s["body"],
                is_required=s["is_required"],
                erratas=[_erratum_to_schema(e) for e in s.get("erratas", [])],
            ) for s in replay["effective_sections"]
        ],
        erratum_acks=ack_items,
    )


def _raise(errors: List[str], status_code: int = 400):
    raise HTTPException(status_code=status_code, detail={"errors": errors})


# ------------------------------ 当前可用内容 ------------------------------

@router.get("/api/themes/{theme_id}/current-version",
            response_model=schemas.ContentVersionDetail)
def get_current_version(
    theme_id: int,
    at: Optional[str] = Query(None, description="指定时刻（ISO 时间），默认当前"),
    db: Session = Depends(get_db),
):
    """展示主题在指定时刻当前可用的已发布版本（含生效区间、适用年龄、必讲段落）。"""
    from datetime import datetime
    at_dt = datetime.fromisoformat(at) if at else None
    version = crud_content.get_current_version(db, theme_id, at=at_dt)
    if not version:
        raise HTTPException(status_code=404, detail="当前没有处于生效区间的已发布版本")
    return _version_to_schema(db, version, detail=True)


# ------------------------------ 版本发布 ------------------------------

@router.get("/api/themes/{theme_id}/versions",
            response_model=List[schemas.ContentVersionSummary])
def list_theme_versions(
    theme_id: int,
    status: Optional[VersionStatus] = Query(None, description="版本状态"),
    effective_at: Optional[str] = Query(None, description="按生效时刻过滤"),
    audience_age: Optional[int] = Query(None, description="按受众年龄过滤"),
    db: Session = Depends(get_db),
):
    """获取主题的版本列表（草稿/已发布/已撤回均可追溯）。"""
    from datetime import datetime
    at_dt = datetime.fromisoformat(effective_at) if effective_at else None
    versions = crud_content.list_versions(
        db, theme_id=theme_id, status=status,
        effective_at=at_dt, audience_age=audience_age,
    )
    return [_version_to_schema(db, v) for v in versions]


@router.post("/api/themes/{theme_id}/versions",
             response_model=schemas.ContentVersionDetail, status_code=201)
def create_version(
    theme_id: int,
    data: schemas.ContentVersionCreate,
    db: Session = Depends(get_db),
):
    """以版本形式创建讲解词草稿（含适用年龄、必讲段落、生效区间），不影响线上内容。"""
    version, errors = crud_content.create_version(db, theme_id, data, operator=data.created_by)
    if not version:
        _raise(errors, 404 if "主题不存在" in errors else 400)
    return _version_to_schema(db, version, detail=True)


@router.get("/api/versions/{version_id}",
            response_model=schemas.ContentVersionDetail)
def get_version(version_id: int, db: Session = Depends(get_db)):
    """获取版本详情（含全部段落）。"""
    version = crud_content.get_version(db, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")
    return _version_to_schema(db, version, detail=True)


@router.put("/api/versions/{version_id}",
            response_model=schemas.ContentVersionDetail)
def update_draft_version(
    version_id: int,
    data: schemas.ContentVersionDraftUpdate,
    db: Session = Depends(get_db),
):
    """仅草稿可改；已发布版本只能发新版本或撤回。"""
    version, errors = crud_content.update_draft(db, version_id, data)
    if not version:
        _raise(errors, 404 if "版本不存在" in errors else 400)
    return _version_to_schema(db, version, detail=True)


@router.post("/api/versions/{version_id}/publish",
             response_model=schemas.ContentVersionDetail)
def publish_version(
    version_id: int,
    data: schemas.ContentVersionPublish,
    db: Session = Depends(get_db),
):
    """发布版本：成为当前可用内容，并通知未开始场次有新版本待学校确认。"""
    version, errors = crud_content.publish_version(db, version_id, data.operator)
    if not version:
        _raise(errors, 404 if "版本不存在" in errors else 400)
    return _version_to_schema(db, version, detail=True)


@router.post("/api/versions/{version_id}/withdraw",
             response_model=schemas.ContentVersionDetail)
def withdraw_version(
    version_id: int,
    data: schemas.ContentVersionWithdraw,
    db: Session = Depends(get_db),
):
    """撤回版本：未开始场次进入"版本撤回待重新确认"，已结束场次证据不动。"""
    version, errors = crud_content.withdraw_version(db, version_id, data.operator, data.reason)
    if not version:
        _raise(errors, 404 if "版本不存在" in errors else 400)
    return _version_to_schema(db, version, detail=True)


# ------------------------------ 紧急勘误 ------------------------------

@router.get("/api/versions/{version_id}/erratas",
            response_model=List[schemas.Erratum])
def list_erratas(
    version_id: int,
    status: Optional[ErrataStatus] = Query(None, description="勘误状态"),
    db: Session = Depends(get_db),
):
    """获取版本的勘误链（含已被取代的勘误，按编号排序）。"""
    if not crud_content.get_version(db, version_id):
        raise HTTPException(status_code=404, detail="版本不存在")
    erratas = crud_content.list_erratas(db, version_id, status=status)
    return [_erratum_to_schema(e) for e in erratas]


@router.post("/api/versions/{version_id}/erratas",
             response_model=schemas.Erratum, status_code=201)
def issue_erratum(
    version_id: int,
    data: schemas.ErratumCreate,
    db: Session = Depends(get_db),
):
    """发布紧急勘误：未开始场次需重新回应，已结束场次证据不改写。"""
    erratum, errors = crud_content.issue_erratum(db, version_id, data)
    if not erratum:
        _raise(errors, 404 if "版本不存在" in errors else 400)
    db.refresh(erratum)
    return _erratum_to_schema(erratum)


# ------------------------------ 场次内容确认与还原 ------------------------------

@router.post("/api/sessions/{session_id}/content/confirm",
             response_model=schemas.SessionFreeze, status_code=201)
def confirm_session_content(
    session_id: int,
    data: schemas.FreezeCreate,
    db: Session = Depends(get_db),
):
    """学校确认场次内容：冻结一份可核验的内容清单（快照+哈希）。"""
    freeze, errors = crud_content.confirm_session_content(db, session_id, data)
    if not freeze:
        _raise(errors, 404 if "场次不存在" in errors else 400)
    return _freeze_to_schema(db, freeze)


@router.get("/api/sessions/{session_id}/content/current",
            response_model=schemas.SessionFreeze)
def get_current_freeze(session_id: int, db: Session = Depends(get_db)):
    """获取场次当前冻结清单（含确定状态与勘误回应情况）。"""
    freeze = crud_content.get_current_freeze(db, session_id)
    if not freeze:
        raise HTTPException(status_code=404, detail="该场次尚无内容确认记录")
    return _freeze_to_schema(db, freeze)


@router.get("/api/sessions/{session_id}/content/history",
            response_model=List[schemas.SessionFreeze])
def list_freeze_history(session_id: int, db: Session = Depends(get_db)):
    """获取场次历次确认的冻结清单（旧行保留，证据只追加）。"""
    freezes = crud_content.list_freezes(db, session_id)
    if not freezes:
        raise HTTPException(status_code=404, detail="该场次尚无内容确认记录")
    return [_freeze_to_schema(db, f) for f in freezes]


@router.get("/api/sessions/{session_id}/content/replay",
            response_model=schemas.FreezeReplay)
def replay_session_content(session_id: int, db: Session = Depends(get_db)):
    """按场次还原冻结清单及后续勘误链，并给出当前实际生效段落。"""
    freeze = crud_content.get_current_freeze(db, session_id)
    if not freeze:
        raise HTTPException(status_code=404, detail="该场次尚无内容确认记录")
    return _build_replay(db, freeze)


@router.get("/api/freezes/{freeze_id}/replay",
            response_model=schemas.FreezeReplay)
def replay_freeze_by_id(freeze_id: int, db: Session = Depends(get_db)):
    """按冻结记录 ID 还原（可查看历史冻结行对应的证据）。"""
    freeze = crud_content.get_freeze(db, freeze_id)
    if not freeze:
        raise HTTPException(status_code=404, detail="冻结记录不存在")
    return _build_replay(db, freeze)


def _build_replay(db: Session, freeze) -> schemas.FreezeReplay:
    replay = crud_content.replay_freeze(db, freeze)
    return schemas.FreezeReplay(
        freeze=_freeze_to_schema(db, freeze, replay=replay),
        errata_chain=[_erratum_to_schema(e) for e in replay["errata_chain"]],
        pending_erratas=[_erratum_to_schema(e) for e in replay["pending_erratas"]],
        effective_sections=[
            schemas.FreezeSectionItem(
                section_no=s["section_no"], title=s["title"], body=s["body"],
                is_required=s["is_required"],
                erratas=[_erratum_to_schema(e) for e in s.get("erratas", [])],
            ) for s in replay["effective_sections"]
        ],
    )


# ------------------------------ 改期 ------------------------------

@router.post("/api/freezes/{freeze_id}/reschedule/request",
             response_model=schemas.SessionFreeze)
def request_reschedule(
    freeze_id: int,
    data: schemas.RescheduleRequest,
    db: Session = Depends(get_db),
):
    """场次改期申请：进入"改期待审核"，审核通过前场次时间不变。"""
    freeze, errors = crud_content.request_reschedule(db, freeze_id, data)
    if not freeze:
        _raise(errors, 404 if "冻结记录不存在" in errors else 400)
    return _freeze_to_schema(db, freeze)


@router.post("/api/freezes/{freeze_id}/reschedule/review",
             response_model=schemas.SessionFreeze)
def review_reschedule(
    freeze_id: int,
    data: schemas.RescheduleReview,
    db: Session = Depends(get_db),
):
    """审核改期：通过后更新场次时间，驳回则维持原排期，均有确定状态。"""
    freeze, errors = crud_content.review_reschedule(db, freeze_id, data)
    if not freeze:
        _raise(errors, 404 if "冻结记录不存在" in errors else 400)
    return _freeze_to_schema(db, freeze)


# ------------------------------ 学校对新版本/勘误的回应 ------------------------------

@router.post("/api/freezes/{freeze_id}/new-version-decision",
             response_model=schemas.SessionFreeze)
def decide_new_version(
    freeze_id: int,
    data: schemas.NewVersionDecision,
    db: Session = Depends(get_db),
):
    """学校回应新版本：接受则冻结新版本清单，拒绝则保留原冻结并标记"学校拒绝新版本"。"""
    freeze, errors = crud_content.decide_new_version(db, freeze_id, data)
    if not freeze:
        _raise(errors, 404 if "冻结记录不存在" in errors else 400)
    return _freeze_to_schema(db, freeze)


@router.post("/api/freezes/{freeze_id}/erratas/{erratum_id}/decision",
             response_model=schemas.ErrataAckItem)
def decide_erratum(
    freeze_id: int,
    erratum_id: int,
    data: schemas.ErrataDecision,
    db: Session = Depends(get_db),
):
    """场次回应勘误：未开始场次可应用/拒绝；已结束场次证据锁定，拒绝操作。"""
    ack, errors = crud_content.decide_erratum(db, freeze_id, erratum_id, data)
    if not ack:
        _raise(errors, 404 if "冻结记录不存在" in errors else 400)
    return schemas.ErrataAckItem(
        id=ack.id,
        erratum_id=ack.erratum_id,
        erratum_title=ack.erratum.title if ack.erratum else "",
        severity=ack.erratum.severity if ack.erratum else None,
        status=ack.status,
        decided_by=ack.decided_by,
        decided_at=ack.decided_at,
        note=ack.note,
        created_at=ack.created_at,
    )


# ------------------------------ 讲解员临时替换 ------------------------------

@router.post("/api/sessions/{session_id}/replace-staff",
             response_model=schemas.StaffReplacementRecord, status_code=201)
def replace_staff(
    session_id: int,
    data: schemas.StaffReplacementCreate,
    db: Session = Depends(get_db),
):
    """讲解员/讲师临时替换：校验资格与时间，追加替换留痕，内容冻结不受影响。"""
    record, errors = crud_content.replace_staff(
        db, session_id, data.old_staff_id, data.new_staff_id, data.operator, data.reason,
    )
    if not record:
        _raise(errors, 404 if "场次不存在" in errors else 400)
    return schemas.StaffReplacementRecord(
        id=record.id,
        session_id=record.session_id,
        old_staff_id=record.old_staff_id,
        old_staff_name=record.old_staff.name if record.old_staff else "",
        new_staff_id=record.new_staff_id,
        new_staff_name=record.new_staff.name if record.new_staff else "",
        old_assignment_id=record.old_assignment_id,
        role=record.role,
        reason=record.reason,
        operator=record.operator,
        created_at=record.created_at,
    )


@router.get("/api/sessions/{session_id}/replacements",
            response_model=List[schemas.StaffReplacementRecord])
def list_replacements(session_id: int, db: Session = Depends(get_db)):
    """获取场次的临时替换记录链。"""
    records = crud_content.list_replacements(db, session_id)
    return [
        schemas.StaffReplacementRecord(
            id=r.id,
            session_id=r.session_id,
            old_staff_id=r.old_staff_id,
            old_staff_name=r.old_staff.name if r.old_staff else "",
            new_staff_id=r.new_staff_id,
            new_staff_name=r.new_staff.name if r.new_staff else "",
            old_assignment_id=r.old_assignment_id,
            role=r.role,
            reason=r.reason,
            operator=r.operator,
            created_at=r.created_at,
        ) for r in records
    ]
