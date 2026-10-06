import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app import schemas, crud
from app.models import (
    ContentVersionStatus, ErratumStatus, ContentConfirmationStatus,
    ThemeContentVersion, ContentErratum, SessionContentConfirmation,
    GuideSubstitution,
)

router = APIRouter(tags=["主题内容版本化"])


# ---------- 转换器 ----------

def _segment_to_schema(item):
    return schemas.ContentSegment(
        id=item.id,
        segment_key=item.segment_key,
        title=item.title,
        body=item.body,
        is_required=item.is_required,
        content_hash=item.content_hash,
        sort_order=item.sort_order,
    )


def _version_to_schema(version: ThemeContentVersion) -> schemas.ContentVersion:
    return schemas.ContentVersion(
        id=version.id,
        theme_id=version.theme_id,
        version_number=version.version_number,
        status=version.status,
        title=version.title,
        age_min=version.age_min,
        age_max=version.age_max,
        content_text=version.content_text,
        required_segments=[_segment_to_schema(i)
                           for i in sorted(version.items, key=lambda x: (x.sort_order, x.id))],
        sensitivity_notes=version.sensitivity_notes,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        published_at=version.published_at,
        withdrawn_at=version.withdrawn_at,
        withdraw_reason=version.withdraw_reason,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _erratum_to_schema(erratum: ContentErratum) -> schemas.Erratum:
    return schemas.Erratum(
        id=erratum.id,
        content_version_id=erratum.content_version_id,
        erratum_no=erratum.erratum_no,
        target_item_id=erratum.target_item_id,
        severity=erratum.severity,
        old_text=erratum.old_text,
        new_text=erratum.new_text,
        reason=erratum.reason,
        status=erratum.status,
        issued_by=erratum.issued_by,
        issued_at=erratum.issued_at,
        supersedes_erratum_id=erratum.supersedes_erratum_id,
    )


def _confirmation_to_schema(conf: SessionContentConfirmation, chain: List[dict]) -> schemas.ContentConfirmation:
    try:
        checklist_raw = json.loads(conf.frozen_checklist)
    except (ValueError, TypeError):
        checklist_raw = []
    checklist = [schemas.FrozenChecklistItem(**c) for c in checklist_raw]
    chain_views = []
    for c in chain:
        data = _erratum_to_schema(c["erratum"]).model_dump()
        data["status"] = c["status"]  # 用链条状态覆盖（含“已被替代”等）
        chain_views.append(schemas.ErratumChainView(
            **data,
            superseded_by_id=c.get("superseded_by_id"),
            delivered_at=c["delivered_at"],
            acknowledged_at=c["acknowledged_at"],
            acknowledged_by=c["acknowledged_by"],
            note=c["note"],
        ))
    return schemas.ContentConfirmation(
        id=conf.id,
        session_id=conf.session_id,
        content_version_id=conf.content_version_id,
        version_number=conf.version.version_number if conf.version else 0,
        status=conf.status,
        frozen_age_min=conf.frozen_age_min,
        frozen_age_max=conf.frozen_age_max,
        content_hash=conf.content_hash,
        confirmed_by=conf.confirmed_by,
        confirmed_at=conf.confirmed_at,
        reconfirm_reason=conf.reconfirm_reason,
        school_response_at=conf.school_response_at,
        superseded_by_id=conf.superseded_by_id,
        checklist=checklist,
        errata_chain=chain_views,
    )


def _substitution_to_schema(sub: GuideSubstitution) -> schemas.GuideSubstitutionOut:
    return schemas.GuideSubstitutionOut(
        id=sub.id,
        session_id=sub.session_id,
        assignment_id=sub.assignment_id,
        original_staff_id=sub.original_staff_id,
        original_staff_name=sub.original_staff.name if sub.original_staff else "",
        substitute_staff_id=sub.substitute_staff_id,
        substitute_staff_name=sub.substitute_staff.name if sub.substitute_staff else None,
        role=sub.role,
        reason=sub.reason,
        status=sub.status,
        requested_by=sub.requested_by,
        requested_at=sub.requested_at,
        substituted_at=sub.substituted_at,
        restored_at=sub.restored_at,
        cancelled_at=sub.cancelled_at,
    )


# ---------- 内容版本 ----------

@router.post("/api/themes/{theme_id}/content-versions",
             response_model=schemas.ContentVersion, status_code=201)
def create_content_version(theme_id: int, version_in: schemas.ContentVersionCreate,
                           db: Session = Depends(get_db)):
    """为主题创建一个内容版本（草稿）。"""
    version, errors = crud.create_content_version(db, theme_id, version_in)
    if not version:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _version_to_schema(version)


@router.get("/api/themes/{theme_id}/content-versions",
            response_model=List[schemas.ContentVersion])
def list_content_versions(
    theme_id: int,
    status: Optional[ContentVersionStatus] = Query(None, description="版本状态"),
    db: Session = Depends(get_db)
):
    """列出主题的全部内容版本（含历史版本，用于追溯）。"""
    if not crud.get_theme(db, theme_id):
        raise HTTPException(status_code=404, detail="主题不存在")
    versions = crud.list_content_versions(db, theme_id, status=status)
    return [_version_to_schema(v) for v in versions]


@router.get("/api/themes/{theme_id}/content-versions/current",
            response_model=schemas.AvailableContentVersion)
def get_current_content(theme_id: int, db: Session = Depends(get_db)):
    """展示主题当前可用（已发布且处于生效区间）的内容版本。"""
    theme = crud.get_theme(db, theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail="主题不存在")
    version = crud.get_current_content_version(db, theme_id)
    if not version:
        raise HTTPException(status_code=404, detail="该主题当前没有生效的内容版本")
    open_errata = crud.list_errata(db, version.id, status=ErratumStatus.ISSUED)
    return schemas.AvailableContentVersion(
        theme_id=theme.id,
        theme_name=theme.name,
        version_id=version.id,
        version_number=version.version_number,
        title=version.title,
        age_min=version.age_min,
        age_max=version.age_max,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        sensitivity_notes=version.sensitivity_notes,
        open_errata_count=len(open_errata),
        segment_count=len(version.items),
    )


@router.get("/api/content-versions/{version_id}", response_model=schemas.ContentVersion)
def get_content_version(version_id: int, db: Session = Depends(get_db)):
    """获取内容版本详情（含必讲段落清单与逐条校验值）。"""
    version = crud.get_content_version(db, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="内容版本不存在")
    return _version_to_schema(version)


@router.put("/api/content-versions/{version_id}", response_model=schemas.ContentVersion)
def update_content_version(version_id: int, version_in: schemas.ContentVersionUpdate,
                           db: Session = Depends(get_db)):
    """修改内容版本——仅草稿可改，已发布版本内容冻结。"""
    version, errors = crud.update_content_version(db, version_id, version_in)
    if not version:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _version_to_schema(version)


@router.post("/api/content-versions/{version_id}/publish",
             response_model=schemas.ContentVersion)
def publish_content_version(version_id: int, db: Session = Depends(get_db)):
    """发布内容版本（固化适用年龄、必讲段落、生效区间）。"""
    version, errors = crud.publish_content_version(db, version_id)
    if not version:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _version_to_schema(version)


@router.post("/api/content-versions/{version_id}/withdraw",
             response_model=schemas.ContentVersionWithdrawResult)
def withdraw_content_version(version_id: int, body: schemas.ContentVersionWithdraw,
                             db: Session = Depends(get_db)):
    """撤回内容版本；引用它且未开始的场次进入待重新确认，已结束场次证据不变。"""
    version, affected, errors = crud.withdraw_content_version(
        db, version_id, body.reason, body.operator)
    if not version:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return schemas.ContentVersionWithdrawResult(
        **_version_to_schema(version).model_dump(),
        affected_pending_sessions=affected
    )


# ---------- 紧急勘误 ----------

@router.post("/api/content-versions/{version_id}/errata",
             response_model=schemas.Erratum, status_code=201)
def create_erratum(version_id: int, erratum_in: schemas.ErratumCreate,
                   db: Session = Depends(get_db)):
    """对已发布版本追加紧急勘误（形成勘误链），可要求未开始场次重新确认。

    勘误只追加，绝不改写原始版本或已结束场次的冻结证据。
    """
    erratum, affected, errors = crud.create_erratum(db, version_id, erratum_in)
    if not erratum:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _erratum_to_schema(erratum)


@router.get("/api/content-versions/{version_id}/errata",
            response_model=List[schemas.Erratum])
def list_errata(
    version_id: int,
    status: Optional[ErratumStatus] = Query(None, description="勘误状态"),
    db: Session = Depends(get_db)
):
    """获取内容版本的勘误链。"""
    if not crud.get_content_version(db, version_id):
        raise HTTPException(status_code=404, detail="内容版本不存在")
    return [_erratum_to_schema(e) for e in crud.list_errata(db, version_id, status=status)]


# ---------- 场次内容确认与冻结证据 ----------

@router.post("/api/sessions/{session_id}/content/confirm",
             response_model=schemas.ContentConfirmation, status_code=201)
def confirm_session_content(
    session_id: int,
    body: schemas.ContentConfirmRequest,
    version_id: Optional[int] = Query(None, description="指定版本；不传则取当前生效版本"),
    db: Session = Depends(get_db)
):
    """学校确认时冻结一份可核验的内容清单。"""
    conf, errors = crud.confirm_session_content(
        db, session_id, body.confirmed_by, version_id=version_id)
    if not conf:
        raise HTTPException(status_code=400, detail={"errors": errors})
    chain = crud.get_erratum_chain(db, conf)
    return _confirmation_to_schema(conf, chain)


@router.get("/api/sessions/{session_id}/content",
            response_model=schemas.SessionContentStatus)
def get_session_content_status(session_id: int, db: Session = Depends(get_db)):
    """按场次还原内容状态：冻结清单、确认状态与后续勘误链。"""
    session = crud.get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="场次不存在")

    conf = crud.get_session_confirmation(db, session_id)
    current = crud.get_current_content_version(db, session.theme_id)

    result = schemas.SessionContentStatus(
        session_id=session.id,
        session_title=session.title,
        session_status=session.status,
        theme_id=session.theme_id,
        current_available_version_id=current.id if current else None,
        current_available_version_number=current.version_number if current else None,
    )
    if not conf:
        return result

    chain = crud.get_erratum_chain(db, conf)
    # “待知悉”= 已送达该场次（有送达记录）但尚未知悉；未送达不计入
    pending = [c for c in chain if c["delivered_at"] is not None and c["acknowledged_at"] is None]
    frozen = _confirmation_to_schema(conf, chain)

    result.current_confirmation_id = conf.id
    result.content_version_id = conf.content_version_id
    result.version_number = conf.version.version_number if conf.version else None
    result.confirmation_status = conf.status
    result.content_hash = conf.content_hash
    result.has_pending_errata = len(pending) > 0
    result.pending_errata_count = len(pending)
    result.needs_reconfirm = conf.status == ContentConfirmationStatus.PENDING_RECONFIRM
    result.frozen = frozen
    return result


@router.post("/api/sessions/{session_id}/content/reconfirm",
             response_model=schemas.ContentConfirmation)
def reconfirm_session_content(session_id: int, body: schemas.ReconfirmRequest,
                              db: Session = Depends(get_db)):
    """学校接受新版本/勘误后重新确认；旧快照留痕为“已被新版本替代”。

    已结束场次调用将被拒绝，历史证据不可改写。
    """
    conf, errors = crud.reconfirm_session_content(
        db, session_id, body.operator,
        target_version_id=body.target_version_id, reason=body.reason)
    if not conf:
        raise HTTPException(status_code=400, detail={"errors": errors})
    chain = crud.get_erratum_chain(db, conf)
    return _confirmation_to_schema(conf, chain)


@router.post("/api/sessions/{session_id}/content/reject",
             response_model=schemas.ContentConfirmation)
def reject_new_version(session_id: int, body: schemas.SchoolRejectRequest,
                       db: Session = Depends(get_db)):
    """学校拒绝新版本：场次锁定原冻结版本，状态为“学校拒绝新版本”。"""
    conf, errors = crud.reject_new_version(db, session_id, body.rejected_by, body.reason)
    if not conf:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _confirmation_to_schema(conf, crud.get_erratum_chain(db, conf))


@router.post("/api/sessions/{session_id}/content/retain",
             response_model=schemas.ContentConfirmation)
def retain_confirmed_version(session_id: int, body: schemas.SubstitutionAction,
                             db: Session = Depends(get_db)):
    """学校拒绝新版本后，馆方核定仍按原冻结版本执行，恢复“已确认”。"""
    conf, errors = crud.retain_confirmed_version(db, session_id, body.operator)
    if not conf:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _confirmation_to_schema(conf, crud.get_erratum_chain(db, conf))


@router.post("/api/sessions/{session_id}/content/errata/{erratum_id}/ack",
             response_model=schemas.ContentConfirmation)
def acknowledge_erratum(session_id: int, erratum_id: int,
                        body: schemas.ErratumAckRequest, db: Session = Depends(get_db)):
    """知悉某条勘误（只记录知悉，不改写冻结证据）。"""
    _, errors = crud.acknowledge_erratum(
        db, session_id, erratum_id, body.acknowledged_by, body.note)
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    conf = crud.get_session_confirmation(db, session_id)
    return _confirmation_to_schema(conf, crud.get_erratum_chain(db, conf))


@router.get("/api/sessions/{session_id}/content/verify")
def verify_session_content(session_id: int, db: Session = Depends(get_db)):
    """核验场次当前冻结清单的完整性（重算校验值）。"""
    conf = crud.get_session_confirmation(db, session_id)
    if not conf:
        raise HTTPException(status_code=404, detail="场次尚无内容确认")
    intact, errors = crud.verify_frozen_checklist(db, conf.id)
    return {
        "session_id": session_id,
        "confirmation_id": conf.id,
        "content_hash": conf.content_hash,
        "intact": intact,
        "errors": errors,
    }


@router.get("/api/sessions/{session_id}/content/history",
            response_model=List[schemas.ContentConfirmation])
def list_session_content_history(session_id: int, db: Session = Depends(get_db)):
    """列出场次历次内容确认（含已被替代的历史快照），还原证据时间线。"""
    if not crud.get_session(db, session_id):
        raise HTTPException(status_code=404, detail="场次不存在")
    confs = crud.list_session_confirmations(db, session_id)
    result = []
    for conf in confs:
        chain = crud.get_erratum_chain(db, conf)
        result.append(_confirmation_to_schema(conf, chain))
    return result


# ---------- 讲解员临时替换 ----------

@router.post("/api/sessions/{session_id}/substitutions",
             response_model=schemas.GuideSubstitutionOut, status_code=201)
def request_substitution(session_id: int, body: schemas.SubstitutionCreate,
                         db: Session = Depends(get_db)):
    """登记讲解员临时替换（待替班），不影响内容冻结证据。"""
    sub, errors = crud.request_substitution(db, session_id, body)
    if not sub:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _substitution_to_schema(sub)


@router.get("/api/sessions/{session_id}/substitutions",
            response_model=List[schemas.GuideSubstitutionOut])
def list_session_substitutions(session_id: int, db: Session = Depends(get_db)):
    """获取场次的讲解员替换记录。"""
    if not crud.get_session(db, session_id):
        raise HTTPException(status_code=404, detail="场次不存在")
    return [_substitution_to_schema(s) for s in crud.list_substitutions(db, session_id)]


@router.get("/api/substitutions", response_model=List[schemas.GuideSubstitutionOut])
def list_all_substitutions(db: Session = Depends(get_db)):
    """获取全部讲解员替换记录。"""
    return [_substitution_to_schema(s) for s in crud.list_substitutions(db)]


@router.post("/api/substitutions/{substitution_id}/arrive",
             response_model=schemas.GuideSubstitutionOut)
def substitution_arrive(substitution_id: int, body: schemas.SubstitutionArrive,
                        db: Session = Depends(get_db)):
    """替班讲解员到岗（校验资格与时间后改派排班）。"""
    sub, errors = crud.substitution_arrive(
        db, substitution_id, body.substitute_staff_id, body.operator)
    if not sub:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _substitution_to_schema(sub)


@router.post("/api/substitutions/{substitution_id}/restore",
             response_model=schemas.GuideSubstitutionOut)
def substitution_restore(substitution_id: int, body: schemas.SubstitutionAction,
                         db: Session = Depends(get_db)):
    """原讲解员回归。"""
    sub, errors = crud.substitution_restore(db, substitution_id, body.operator)
    if not sub:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _substitution_to_schema(sub)


@router.post("/api/substitutions/{substitution_id}/cancel",
             response_model=schemas.GuideSubstitutionOut)
def substitution_cancel(substitution_id: int, body: schemas.SubstitutionAction,
                        db: Session = Depends(get_db)):
    """取消尚未到岗的替班需求。"""
    sub, errors = crud.substitution_cancel(db, substitution_id, body.operator)
    if not sub:
        raise HTTPException(status_code=400, detail={"errors": errors})
    return _substitution_to_schema(sub)
