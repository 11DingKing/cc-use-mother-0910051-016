#!/usr/bin/env python3
"""讲解词版本化 + 场次冻结 + 勘误链 + 临时替换 端到端验证。"""
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="content_ver_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test_content.db"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import crud_content
from app.models import (
    FreezeScheduleState, ErrataAckStatus, VersionStatus,
    SessionContentFreeze,
)

client = TestClient(app)
failures = []


def check(cond, msg):
    if cond:
        print(f"  ✓ {msg}")
    else:
        failures.append(msg)
        print(f"  ✗ {msg}")


def must(r, code=200):
    if r.status_code != code:
        raise AssertionError(f"期望 {code}，实际 {r.status_code}: {r.text}")
    return r.json()


def header(t):
    print("\n" + "=" * 70)
    print(f"  {t}")
    print("=" * 70)


def main():
    header("1. 基础数据：主题/场地/学校/讲解员")
    theme = must(client.post("/api/themes", json={
        "name": "青铜礼器", "category": "历史文物", "description": "青铜礼器讲解"
    }), 200)
    theme_id = theme["id"]
    venue = must(client.post("/api/venues", json={
        "name": "青铜厅", "venue_type": "展厅", "capacity": 60, "location": "A馆"
    }), 200)
    venue_id = venue["id"]
    school = must(client.post("/api/schools", json={
        "name": "验证小学", "contact_person": "王老师", "phone": "13800000000"
    }), 200)
    school_id = school["id"]

    def make_guide(name):
        return must(client.post("/api/staff", json={
            "name": name, "staff_type": "讲解员",
            "themes": [{"theme_id": theme_id, "proficiency_level": 5}],
            "venues": [{"venue_id": venue_id, "is_certified": True}],
        }), 200)["id"]

    guide1 = make_guide("张讲解")
    guide2 = make_guide("李讲解")

    header("2. 主题内容以版本发布（适用年龄、必讲段落、生效区间）")
    v1 = must(client.post(f"/api/themes/{theme_id}/versions", json={
        "min_age": 6, "max_age": 12,
        "effective_from": "2026-01-01T00:00:00",
        "effective_to": "2027-12-31T23:59:59",
        "change_note": "首版",
        "created_by": "内容组",
        "sections": [
            {"title": "开篇导览", "body": "欢迎来到青铜展厅（旧表述）", "is_required": True},
            {"title": "拓展故事", "body": "选听：鼎的传说", "is_required": False},
        ],
    }), 201)
    v1_id = v1["id"]
    check(v1["status"] == "草稿", "新建版本为草稿，不直接影响线上")
    check(v1["required_section_count"] == 1, "识别必讲段落数量")
    check(bool(v1["content_hash"]), "版本内容含哈希")

    # 已发布版本不可改：先发布
    must(client.post(f"/api/versions/{v1_id}/publish", json={"operator": "馆长"}), 200)
    cur = must(client.get(f"/api/themes/{theme_id}/current-version"), 200)
    check(cur["id"] == v1_id and cur["status"] == "已发布", "当前可用内容为已发布的 v1")

    r = client.put(f"/api/versions/{v1_id}", json={"change_note": "篡改已发布版本"})
    check(r.status_code == 400, "已发布版本拒绝直接修改")

    header("3. 场次确认时冻结可核验清单")
    session_a = must(client.post("/api/sessions", json={
        "title": "青铜研学A", "theme_id": theme_id, "venue_id": venue_id,
        "session_type": "研学实践",
        "start_time": "2026-11-01T09:00:00", "end_time": "2026-11-01T10:30:00",
        "audience_type": "学校", "audience_count": 40, "school_id": school_id,
        "guides_needed": 1, "needs_lecturer": False,
    }), 200)
    a_id = session_a["id"]

    r = client.post(f"/api/sessions/{a_id}/content/confirm",
                    json={"audience_age": 18, "confirmed_by": "王老师"})
    check(r.status_code == 400 and "适用年龄" in str(r.json()["detail"]),
          "受众年龄超出版本适用区间时拒绝确认")

    fz_a = must(client.post(f"/api/sessions/{a_id}/content/confirm",
                            json={"audience_age": 10, "confirmed_by": "王老师"}), 201)
    check(fz_a["version_no"] == 1 and fz_a["schedule_state"] == "已确认",
          "确认成功，状态=已确认，冻结 v1")
    check(fz_a["snapshot"]["version"]["id"] == v1_id, "快照记录版本ID")
    check(len(fz_a["snapshot"]["sections"]) == 2, "快照含完整段落清单")
    check(bool(fz_a["content_hash"]), "冻结清单含校验哈希")

    header("4. 紧急勘误形成勘误链，未开始场次必须回应")
    section1_id = v1["sections"][0]["id"]
    err1 = must(client.post(f"/api/versions/{v1_id}/erratas", json={
        "section_id": section1_id,
        "title": "开篇措辞勘误",
        "old_text": "旧表述", "new_text": "欢迎来到青铜文明展厅（新表述）",
        "reason": "敏感表述调整", "severity": "紧急勘误", "issued_by": "内容组",
    }), 201)
    fz_a = must(client.get(f"/api/sessions/{a_id}/content/current"), 200)
    check(fz_a["schedule_state"] == "勘误待回应", "勘误发布后场次状态=勘误待回应")
    check(len(fz_a["erratum_acks"]) == 1 and fz_a["erratum_acks"][0]["status"] == "待回应",
          "生成一条待回应勘误")

    replay = must(client.get(f"/api/sessions/{a_id}/content/replay"), 200)
    check(len(replay["pending_erratas"]) == 1, "还原视图列出待处理勘误")

    ack = must(client.post(
        f"/api/freezes/{fz_a['id']}/erratas/{err1['id']}/decision",
        json={"apply": True, "responder": "王老师"}), 200)
    check(ack["status"] == "已应用", "学校/馆方应用勘误")
    replay = must(client.get(f"/api/sessions/{a_id}/content/replay"), 200)
    check(replay["effective_sections"][0]["body"] == "欢迎来到青铜文明展厅（新表述）",
          "还原时开篇段落叠加勘误后的新文本")
    check(replay["freeze"]["schedule_state"] == "已确认", "勘误处理完状态回到已确认")

    # 同段再发一条勘误，旧勘误应被取代（勘误链）
    err2 = must(client.post(f"/api/versions/{v1_id}/erratas", json={
        "section_id": section1_id,
        "title": "开篇二次勘误", "old_text": "新表述",
        "new_text": "欢迎来到青铜文明特展", "severity": "文字微调",
    }), 201)
    chain = must(client.get(f"/api/versions/{v1_id}/erratas"), 200)
    check(any(e["status"] == "已被取代" and e["id"] == err1["id"] for e in chain)
          and err2["supersedes_id"] == err1["id"],
          "同段新勘误取代旧勘误，形成勘误链")

    header("5. 发布新版本 v2，学校拒绝新版本")
    v2 = must(client.post(f"/api/themes/{theme_id}/versions", json={
        "min_age": 6, "max_age": 15,
        "effective_from": "2026-01-01T00:00:00",
        "effective_to": "2027-12-31T23:59:59",
        "change_note": "调整敏感表述与适龄提示",
        "sections": [
            {"title": "开篇导览", "body": "欢迎来到青铜文明特展（v2 适龄版）", "is_required": True},
        ],
    }), 201)
    v2_id = v2["id"]
    must(client.post(f"/api/versions/{v2_id}/publish", json={"operator": "馆长"}), 200)
    fz_a = must(client.get(f"/api/sessions/{a_id}/content/current"), 200)
    check(fz_a["schedule_state"] == "新版本待确认"
          and fz_a["target_version_no"] == 2
          and fz_a["school_response"] == "待回应",
          "新版本发布后未开始场次状态=新版本待确认")

    must(client.post(f"/api/freezes/{fz_a['id']}/new-version-decision",
                     json={"accepted": False, "responder": "王老师", "note": "已印材料沿用旧版"}), 200)
    fz_a = must(client.get(f"/api/sessions/{a_id}/content/current"), 200)
    check(fz_a["schedule_state"] == "学校拒绝新版本", "学校拒绝后有确定状态")
    replay = must(client.get(f"/api/sessions/{a_id}/content/replay"), 200)
    check(replay["freeze"]["version_no"] == 1, "拒绝新版本后仍按 v1 冻结清单执行")

    header("6. 版本撤回：未开始场次进入“版本撤回待重新确认”")
    session_b = must(client.post("/api/sessions", json={
        "title": "青铜研学B", "theme_id": theme_id, "venue_id": venue_id,
        "session_type": "研学实践",
        "start_time": "2026-11-02T09:00:00", "end_time": "2026-11-02T10:30:00",
        "audience_type": "学校", "audience_count": 35, "school_id": school_id,
        "guides_needed": 1, "needs_lecturer": False,
    }), 200)
    b_id = session_b["id"]
    # 新场次确认时拿到当前最新 v2
    fz_b = must(client.post(f"/api/sessions/{b_id}/content/confirm",
                            json={"audience_age": 11, "confirmed_by": "李老师"}), 201)
    check(fz_b["version_no"] == 2, "新场次确认的是当前版本 v2")

    must(client.post(f"/api/versions/{v2_id}/withdraw",
                     json={"operator": "馆长", "reason": "表述需再修订"}), 200)
    fz_b = must(client.get(f"/api/sessions/{b_id}/content/current"), 200)
    check(fz_b["schedule_state"] == "版本撤回待重新确认"
          and fz_b["target_version_no"] == 1,
          "版本撤回后未开始场次待重新确认，并推荐可替代版本 v1")
    # 学校接受替代版本 -> 重新冻结
    must(client.post(f"/api/freezes/{fz_b['id']}/new-version-decision",
                     json={"accepted": True, "responder": "李老师"}), 200)
    fz_b = must(client.get(f"/api/sessions/{b_id}/content/current"), 200)
    check(fz_b["version_no"] == 1, "重新确认后冻结 v1")
    # v1 上仍有生效中的 err2，重新确认后需回应
    pending = [a for a in fz_b["erratum_acks"] if a["status"] == "待回应"]
    check(len(pending) == 1 and pending[0]["erratum_id"] == err2["id"],
          "重新确认后承接 v1 生效勘误 err2 的待回应")
    must(client.post(
        f"/api/freezes/{fz_b['id']}/erratas/{err2['id']}/decision",
        json={"apply": True, "responder": "李老师"}), 200)
    hist = must(client.get(f"/api/sessions/{b_id}/content/history"), 200)
    check(len(hist) == 2 and hist[1]["is_current"] is False and hist[0]["is_current"] is True,
          "历史冻结行保留，证据只追加不改写")

    header("7. 场次改期：待审核 → 通过后改时间，冻结清单不变")
    fz_b = must(client.get(f"/api/sessions/{b_id}/content/current"), 200)
    must(client.post(f"/api/freezes/{fz_b['id']}/reschedule/request", json={
        "new_start_time": "2026-11-03T14:00:00",
        "new_end_time": "2026-11-03T15:30:00",
        "reason": "学校校车冲突", "requester": "李老师",
    }), 200)
    sess_b_mid = must(client.get(f"/api/sessions/{b_id}"), 200)
    check(sess_b_mid["start_time"].startswith("2026-11-02"), "审核通过前场次时间不变")
    fz_b = must(client.get(f"/api/sessions/{b_id}/content/current"), 200)
    check(fz_b["schedule_state"] == "改期待审核", "改期申请有确定状态")
    must(client.post(f"/api/freezes/{fz_b['id']}/reschedule/review",
                     json={"approved": True, "reviewer": "馆方调度"}), 200)
    sess_b = must(client.get(f"/api/sessions/{b_id}"), 200)
    check(sess_b["start_time"].startswith("2026-11-03"), "审核通过后场次改到新时间")
    fz_b = must(client.get(f"/api/sessions/{b_id}/content/current"), 200)
    check(fz_b["schedule_state"] == "已确认" and fz_b["version_no"] == 1,
          "改期完成后内容冻结仍是 v1")

    header("8. 讲解员临时替换：校验资格并留痕，不动内容证据")
    must(client.post(f"/api/sessions/{b_id}/assignments",
                     json={"staff_id": guide1, "role": "讲解员", "is_primary": True}), 200)
    rep = must(client.post(f"/api/sessions/{b_id}/replace-staff", json={
        "old_staff_id": guide1, "new_staff_id": guide2,
        "reason": "张讲解突发不适", "operator": "调度员",
    }), 201)
    check(rep["old_staff_name"] == "张讲解" and rep["new_staff_name"] == "李讲解",
          "替换记录留痕（旧→新）")
    reps = must(client.get(f"/api/sessions/{b_id}/replacements"), 200)
    check(len(reps) == 1, "可按场次查询替换链")
    fz_b = must(client.get(f"/api/sessions/{b_id}/content/current"), 200)
    check(fz_b["version_no"] == 1, "人员替换不影响内容冻结证据")

    header("9. 场次结束后证据锁定：新勘误不改写，操作被拒绝")
    must(client.put(f"/api/sessions/{a_id}", json={"status": "已完成"}), 200)
    fz_a = must(client.get(f"/api/sessions/{a_id}/content/current"), 200)
    check(fz_a["schedule_state"] == "已结束证据锁定", "已结束场次状态=证据锁定")

    # v1 再发紧急勘误
    err3 = must(client.post(f"/api/versions/{v1_id}/erratas", json={
        "section_id": section1_id, "title": "结束后紧急勘误",
        "old_text": "x", "new_text": "结束后才发布的表述",
        "severity": "紧急勘误",
    }), 201)
    fz_a = must(client.get(f"/api/sessions/{a_id}/content/current"), 200)
    check(all(a["erratum_id"] != err3["id"] for a in fz_a["erratum_acks"]),
          "结束后发布的勘误不为已结束场次生成待办")
    replay = must(client.get(f"/api/sessions/{a_id}/content/replay"), 200)
    check(replay["effective_sections"][0]["body"] == "欢迎来到青铜文明展厅（新表述）",
          "已结束场次只保留学校已应用的 err1 文本，不含未回应的 err2 与结束后的 err3")
    check(len(replay["pending_erratas"]) == 0, "已结束场次无勘误待办")

    r = client.post(f"/api/freezes/{fz_a['id']}/erratas/{err2['id']}/decision",
                    json={"apply": True, "responder": "某人"})
    check(r.status_code == 400, "已结束场次拒绝任何勘误回应操作")

    r = client.post(f"/api/sessions/{a_id}/content/confirm",
                    json={"audience_age": 10})
    check(r.status_code == 400, "已结束场次不能重新确认内容")

    r = client.post(f"/api/sessions/{a_id}/replace-staff", json={
        "new_staff_id": guide2, "operator": "调度员"})
    check(r.status_code == 400, "已结束场次不能临时替换人员")

    header("10. 哈希可核验：篡改快照能被发现")
    db = SessionLocal()
    try:
        freeze_row = db.query(SessionContentFreeze).filter(
            SessionContentFreeze.session_id == a_id,
            SessionContentFreeze.is_current.is_(True),
        ).first()
        check(crud_content.verify_freeze_hash(freeze_row), "原始冻结哈希校验通过")
        freeze_row.frozen_snapshot = freeze_row.frozen_snapshot.replace(
            "欢迎来到青铜展厅", "被人偷偷改过的内容")
        db.commit()
        check(not crud_content.verify_freeze_hash(freeze_row),
              "快照被篡改后哈希校验失败（证据可核验）")
    finally:
        db.close()

    header("11. 版本全景可追溯")
    versions = must(client.get(f"/api/themes/{theme_id}/versions"), 200)
    statuses = {v["version_no"]: v["status"] for v in versions}
    check(statuses == {1: "已发布", 2: "已撤回"}, "草稿/发布/撤回版本均可追溯")

    header("12. 撤回时无替代版本：状态确定，后续新版本可接续确认")
    theme2 = must(client.post("/api/themes", json={
        "name": "临展主题", "category": "临时展览", "description": "临展讲解"
    }), 200)
    t2 = theme2["id"]
    w1 = must(client.post(f"/api/themes/{t2}/versions", json={
        "min_age": 8, "max_age": 14,
        "effective_from": "2026-01-01T00:00:00",
        "effective_to": "2027-12-31T23:59:59",
        "sections": [{"title": "唯一必讲段", "body": "临展原文", "is_required": True}],
    }), 201)
    must(client.post(f"/api/versions/{w1['id']}/publish", json={"operator": "馆长"}), 200)
    session_c = must(client.post("/api/sessions", json={
        "title": "临展研学C", "theme_id": t2, "venue_id": venue_id,
        "session_type": "研学实践",
        "start_time": "2026-12-01T09:00:00", "end_time": "2026-12-01T10:00:00",
        "audience_type": "学校", "audience_count": 20, "school_id": school_id,
        "guides_needed": 0, "needs_lecturer": False,
    }), 200)
    c_id = session_c["id"]
    fz_c = must(client.post(f"/api/sessions/{c_id}/content/confirm",
                            json={"audience_age": 10, "confirmed_by": "陈老师"}), 201)
    must(client.post(f"/api/versions/{w1['id']}/withdraw",
                     json={"operator": "馆长", "reason": "临展撤展，内容停用"}), 200)
    fz_c = must(client.get(f"/api/sessions/{c_id}/content/current"), 200)
    check(fz_c["schedule_state"] == "版本撤回待重新确认"
          and fz_c["target_version_no"] is None,
          "无替代版本时撤回仍是确定状态，且不伪造替代版本")
    r = client.post(f"/api/freezes/{fz_c['id']}/new-version-decision",
                    json={"accepted": True, "responder": "陈老师"})
    check(r.status_code == 400, "没有可替代版本时无法完成重新确认")

    w2 = must(client.post(f"/api/themes/{t2}/versions", json={
        "min_age": 8, "max_age": 14,
        "effective_from": "2026-01-01T00:00:00",
        "effective_to": "2027-12-31T23:59:59",
        "change_note": "撤展后重编",
        "sections": [{"title": "唯一必讲段", "body": "临展修订文", "is_required": True}],
    }), 201)
    must(client.post(f"/api/versions/{w2['id']}/publish", json={"operator": "馆长"}), 200)
    fz_c = must(client.get(f"/api/sessions/{c_id}/content/current"), 200)
    check(fz_c["schedule_state"] == "版本撤回待重新确认"
          and fz_c["target_version_no"] == 2,
          "新替代版本发布后接续为撤回重认（指向 v2）")
    must(client.post(f"/api/freezes/{fz_c['id']}/new-version-decision",
                     json={"accepted": True, "responder": "陈老师"}), 200)
    fz_c = must(client.get(f"/api/sessions/{c_id}/content/current"), 200)
    check(fz_c["version_no"] == 2 and fz_c["schedule_state"] == "已确认",
          "学校确认后冻结新版本，状态回到已确认")
    replay_c = must(client.get(f"/api/sessions/{c_id}/content/replay"), 200)
    check(replay_c["freeze"]["snapshot"]["sections"][0]["body"] == "临展修订文",
          "新冻结清单内容为修订版")
    check(len(must(client.get(f"/api/sessions/{c_id}/content/history"), 200)) == 2,
          "撤回再确认保留两次冻结证据")

    if failures:
        print("\n" + "=" * 70)
        print(f"  失败 {len(failures)} 项：")
        for f in failures:
            print(f"   - {f}")
        print("=" * 70)
        sys.exit(1)

    print("\n🎉 所有测试通过！讲解词版本化、场次冻结、勘误链与状态机均符合要求。")


if __name__ == "__main__":
    main()
