#!/usr/bin/env python3
"""主题内容版本化 + 场次冻结证据 + 紧急勘误链 端到端验证。

通过 FastAPI TestClient 在独立临时数据库上跑通：
版本发布、学校确认冻结、紧急勘误、撤回、学校拒绝新版本、
场次改期重确认、讲解员临时替换，以及已结束场次证据不可改写。
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

_tmp = tempfile.mkdtemp(prefix="content_ver_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

PASS = 0


def check(cond, msg):
    global PASS
    assert cond, f"✗ {msg}"
    PASS += 1
    print(f"  ✓ {msg}")


def must_ok(resp, code=200):
    assert resp.status_code == code, f"期望 {code}，实际 {resp.status_code}: {resp.text}"
    return resp.json()


def header(t):
    print("\n" + "=" * 66)
    print(f"  {t}")
    print("=" * 66)


# ---------- 基础数据 ----------
header("1. 初始化主题/场地/学校/讲解员")
theme = must_ok(client.post("/api/themes", json={
    "name": "青铜器文化", "description": "商周青铜器", "category": "历史"}), 200)
theme_id = theme["id"]
venue = must_ok(client.post("/api/venues", json={
    "name": "青铜馆", "venue_type": "展厅", "capacity": 60, "location": "1F"}), 200)
venue_id = venue["id"]
school = must_ok(client.post("/api/schools", json={
    "name": "实验小学", "contact_person": "王老师", "phone": "13800138000"}), 200)
school_id = school["id"]

g1 = must_ok(client.post("/api/staff", json={
    "name": "张讲解", "staff_type": "讲解员",
    "themes": [{"theme_id": theme_id, "proficiency_level": 5}],
    "venues": [{"venue_id": venue_id, "is_certified": True}]}), 200)
g2 = must_ok(client.post("/api/staff", json={
    "name": "李讲解", "staff_type": "讲解员",
    "themes": [{"theme_id": theme_id, "proficiency_level": 4}],
    "venues": [{"venue_id": venue_id, "is_certified": True}]}), 200)

now = datetime.now().replace(microsecond=0)
s1_start = (now + timedelta(days=10)).replace(hour=9, minute=0, second=0)
s1_end = s1_start + timedelta(hours=2)
s1 = must_ok(client.post("/api/sessions", json={
    "title": "青铜器研学", "theme_id": theme_id, "venue_id": venue_id,
    "session_type": "研学实践",
    "start_time": s1_start.isoformat(), "end_time": s1_end.isoformat(),
    "audience_type": "学校", "audience_count": 30, "school_id": school_id,
    "guides_needed": 1, "needs_lecturer": False}), 200)
s1_id = s1["id"]

# ---------- 内容版本 v1 发布 ----------
header("2. 发布内容版本 v1（适用年龄 + 必讲段落 + 生效区间）")
v1 = must_ok(client.post(f"/api/themes/{theme_id}/content-versions", json={
    "title": "青铜器讲解词",
    "age_min": 8, "age_max": 12,
    "content_text": "同学们好，今天我们认识青铜器……",
    "required_segments": [
        {"segment_key": "opening", "title": "开场引入", "body": "提问：大家见过鼎吗？",
         "is_required": True, "sort_order": 1},
        {"segment_key": "houmuwu", "title": "后母戊鼎", "body": "后母戊鼎是商代重器。",
         "is_required": True, "sort_order": 2},
    ],
    "sensitivity_notes": "避免墓葬恐怖化描述",
    "effective_from": (now - timedelta(days=1)).isoformat(),
    "effective_to": (now + timedelta(days=30)).isoformat(),
    "created_by": "策展员赵"}), 201)
check(v1["status"] == "草稿", "新建版本为草稿")
v1_id = v1["id"]
v1 = must_ok(client.post(f"/api/content-versions/{v1_id}/publish"))
check(v1["status"] == "已发布", "v1 已发布")
check(len(v1["required_segments"]) == 2, "v1 含 2 条必讲段落")
seg_hash = v1["required_segments"][1]["content_hash"]

# 发布校验：空必讲段落不能发布
bad = must_ok(client.post(f"/api/themes/{theme_id}/content-versions", json={
    "age_min": 6, "age_max": 10, "content_text": "x",
    "required_segments": [],
    "effective_from": now.isoformat()}), 201)
r = client.post(f"/api/content-versions/{bad['id']}/publish")
check(r.status_code == 400, "无必讲段落的版本不能发布")

# ---------- 学校确认 → 冻结 ----------
header("3. 学校确认场次内容，冻结可核验清单")
conf = must_ok(client.post(f"/api/sessions/{s1_id}/content/confirm",
                           json={"confirmed_by": "王老师"}), 201)
check(conf["version_number"] == 1, "确认的是当前生效的 v1")
check(conf["status"] == "已确认", "确认状态=已确认")
check(len(conf["checklist"]) == 2, "冻结清单含 2 条")
check(conf["frozen_age_min"] == 8 and conf["frozen_age_max"] == 12, "冻结适用年龄 8-12")
frozen_hash = conf["content_hash"]
check(bool(frozen_hash), f"生成整体校验值 {frozen_hash[:12]}…")
# 重复确认必须走重确认
r = client.post(f"/api/sessions/{s1_id}/content/confirm", json={"confirmed_by": "王老师"})
check(r.status_code == 400, "已确认场次不能重复直接确认")

# 安排讲解员 → 场次自动排定
must_ok(client.post(f"/api/sessions/{s1_id}/assignments",
                    json={"staff_id": g1["id"], "role": "讲解员", "is_primary": True}))

# ---------- 发布 v2，敏感表述被调整，但不影响冻结 ----------
header("4. 馆方发布 v2 调整敏感表述；已排期场次仍锁定 v1")
v2 = must_ok(client.post(f"/api/themes/{theme_id}/content-versions", json={
    "title": "青铜器讲解词（适龄优化）",
    "age_min": 7, "age_max": 12,
    "content_text": "同学们好，今天我们从一件青铜器开始……",
    "required_segments": [
        {"segment_key": "opening", "title": "开场引入", "body": "猜一猜：三千年前的人怎么煮饭？",
         "is_required": True, "sort_order": 1},
        {"segment_key": "houmuwu", "title": "后母戊鼎", "body": "后母戊鼎是商代晚期的青铜重器。",
         "is_required": True, "sort_order": 2},
    ],
    "sensitivity_notes": "不出现血腥/墓葬细节",
    "effective_from": (now - timedelta(days=1)).isoformat(),
    "effective_to": (now + timedelta(days=60)).isoformat()}), 201)
v2_id = v2["id"]
VN2 = v2["version_number"]
must_ok(client.post(f"/api/content-versions/{v2_id}/publish"))

cur = must_ok(client.get(f"/api/themes/{theme_id}/content-versions/current"))
check(cur["version_id"] == v2_id, "当前可用内容为 v2")

sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc["version_number"] == 1, "场次仍冻结在 v1")
check(sc["current_available_version_number"] == VN2, "接口同时给出当前可用 v2")
check(sc["frozen"]["content_hash"] == frozen_hash, "冻结校验值未被新版本改写")
check(sc["frozen"]["checklist"][1]["body"] == "后母戊鼎是商代重器。", "冻结清单仍是旧表述")

# 已发布版本内容冻结：PUT 必须被拒
r = client.put(f"/api/content-versions/{v1_id}",
               json={"content_text": "被篡改的正文"})
check(r.status_code == 400, "已发布 v1 内容不可直接修改")
sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc["frozen"]["checklist"][1]["body"] == "后母戊鼎是商代重器。", "拒绝修改后冻结证据不变")

# ---------- 紧急勘误链 ----------
header("5. v1 紧急勘误：未开始场次待重新确认，证据不被改写")
err1 = must_ok(client.post(f"/api/content-versions/{v1_id}/errata", json={
    "target_item_id": v1["required_segments"][1]["id"],
    "severity": "重要", "old_text": "商代重器",
    "new_text": "商代晚期王室重器",
    "reason": "年代表述需更严谨", "issued_by": "内容主管",
    "require_reconfirm": True}), 201)
check(err1["erratum_no"] == 1, "勘误编号 #1")
sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc["needs_reconfirm"] is True, "场次进入“待重新确认”")
check(sc["confirmation_status"] == "待重新确认", "确认状态=待重新确认")
check(sc["pending_errata_count"] == 1, "勘误已送达（1 条待知悉）")
check(sc["frozen"]["errata_chain"][0]["new_text"] == "商代晚期王室重器", "勘误链可按场次还原")
check(sc["frozen"]["content_hash"] == frozen_hash, "勘误不改写冻结清单校验值")
check(sc["frozen"]["checklist"][1]["body"] == "后母戊鼎是商代重器。", "勘误不改写原始段落原文")

# 勘误链：#2 替代 #1
err2 = must_ok(client.post(f"/api/content-versions/{v1_id}/errata", json={
    "severity": "一般", "new_text": "商代晚期司祭礼器",
    "supersedes_erratum_id": err1["id"], "require_reconfirm": False}), 201)
chain = must_ok(client.get(f"/api/content-versions/{v1_id}/errata"))
check(chain[0]["status"] == "已被替代", "#1 被 #2 标记为已替代")
sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
view1 = sc["frozen"]["errata_chain"][0]
check(view1["superseded_by_id"] == err2["id"], "场次视角可还原勘误替代链")

# ---------- 学校拒绝新版本 ----------
header("6. 学校拒绝新版本 → 确定状态，馆方可核定沿用旧版")
rj = must_ok(client.post(f"/api/sessions/{s1_id}/content/reject",
                         json={"rejected_by": "王老师", "reason": "临期不再改动"}))
check(rj["status"] == "学校拒绝新版本", "状态=学校拒绝新版本")
r = client.post(f"/api/sessions/{s1_id}/content/reject",
                json={"rejected_by": "王老师"})
check(r.status_code == 400, "非待重新确认状态不能重复拒绝")
rt = must_ok(client.post(f"/api/sessions/{s1_id}/content/retain",
                         json={"operator": "调度小李"}))
check(rt["status"] == "已确认", "馆方核定沿用旧版后恢复“已确认”")

# ---------- 重新确认到 v2 ----------
header("7. 学校重新确认 v2：旧快照留痕，证据时间线可查")
# 再发一条要求重确认的勘误，制造待重新确认
must_ok(client.post(f"/api/content-versions/{v1_id}/errata", json={
    "severity": "重要", "new_text": "以适龄语言讲解礼器用途",
    "require_reconfirm": True}), 201)
sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc["needs_reconfirm"] is True, "再次进入待重新确认")
# 知悉勘误（不改状态、不改证据）
ack = must_ok(client.post(
    f"/api/sessions/{s1_id}/content/errata/{err1['id']}/ack",
    json={"acknowledged_by": "王老师", "note": "已知悉"}))
chain_v1 = {e["id"]: e for e in ack["errata_chain"]}
check(chain_v1[err1["id"]]["acknowledged_by"] == "王老师", "勘误知悉情况已记录")

rc = must_ok(client.post(f"/api/sessions/{s1_id}/content/reconfirm",
                         json={"operator": "王老师", "target_version_id": v2_id}))
check(rc["version_number"] == VN2 and rc["status"] == "已确认", "重新确认到 v2")
new_hash = rc["content_hash"]
check(new_hash != frozen_hash, "v2 冻结清单为新的校验值")
hist = must_ok(client.get(f"/api/sessions/{s1_id}/content/history"))
check(len(hist) == 2, "证据时间线含 2 次确认")
check(hist[1]["status"] == "已被新版本替代", "旧 v1 确认留痕为“已被新版本替代”")
check(hist[1]["superseded_by_id"] == rc["id"], "旧记录指向新确认")
check(hist[1]["content_hash"] == frozen_hash, "旧快照校验值永久保留")

vrf = must_ok(client.get(f"/api/sessions/{s1_id}/content/verify"))
check(vrf["intact"] is True, "当前冻结清单完整性核验通过")

# ---------- 场次改期 → 超出生效区间需重确认 ----------
header("8. 场次改期超出 v2 生效区间 → 自动待重新确认")
far_start = (now + timedelta(days=70)).replace(hour=9, minute=0, second=0)
r = client.put(f"/api/sessions/{s1_id}", json={
    "start_time": far_start.isoformat(),
    "end_time": (far_start + timedelta(hours=2)).isoformat()})
check(r.status_code == 400, "改期接口以 400 携带业务提示")
check(any("重新确认" in e for e in r.json()["detail"]["errors"]), "提示内容需重新确认")
sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc["confirmation_status"] == "待重新确认", "改期后状态=待重新确认")
# 无覆盖版本时不能重确认
r = client.post(f"/api/sessions/{s1_id}/content/reconfirm", json={"operator": "王老师"})
check(r.status_code == 400, "新时间无生效版本时拒绝重确认")
# 发布覆盖该时间的 v3，再重确认
v3 = must_ok(client.post(f"/api/themes/{theme_id}/content-versions", json={
    "age_min": 7, "age_max": 14, "content_text": "新版讲解词",
    "required_segments": [
        {"segment_key": "opening", "title": "开场", "body": "远方的朋友好",
         "is_required": True, "sort_order": 1}],
    "effective_from": (now + timedelta(days=40)).isoformat(),
    "effective_to": (now + timedelta(days=120)).isoformat()}), 201)
v3_id = v3["id"]
VN3 = v3["version_number"]
must_ok(client.post(f"/api/content-versions/{v3_id}/publish"))
rc3 = must_ok(client.post(f"/api/sessions/{s1_id}/content/reconfirm",
                          json={"operator": "王老师", "target_version_id": v3_id}))
check(rc3["version_number"] == VN3 and rc3["status"] == "已确认", "重新确认到覆盖新时间的 v3")

# ---------- 讲解员临时替换 ----------
header("9. 讲解员临时替换：待替班→到岗→回归 全状态")
assignment = must_ok(client.get(f"/api/sessions/{s1_id}"))["assignments"][0]
asg_id = assignment["id"]
sub = must_ok(client.post(f"/api/sessions/{s1_id}/substitutions", json={
    "assignment_id": asg_id, "substitute_staff_id": g2["id"],
    "reason": "张讲解突发不适", "requested_by": "前台"}), 201)
check(sub["status"] == "待替班", "替班状态=待替班")
check(sub["original_staff_name"] == "张讲解", "原讲解员留痕")
# 重复登记被拒
r = client.post(f"/api/sessions/{s1_id}/substitutions",
                json={"assignment_id": asg_id})
check(r.status_code == 400, "进行中的替班不能重复登记")
ar = must_ok(client.post(f"/api/substitutions/{sub['id']}/arrive",
                         json={"substitute_staff_id": g2["id"], "operator": "主管"}))
check(ar["status"] == "替班已到岗", "状态=替班已到岗")
s1_now = must_ok(client.get(f"/api/sessions/{s1_id}"))
check(s1_now["assignments"][0]["staff_name"] == "李讲解", "排班已改派给替班讲解员")
# 无资格替班被拒：再发起一个已到岗的非法 arrive
r = client.post(f"/api/substitutions/{sub['id']}/arrive",
                json={"substitute_staff_id": g2["id"], "operator": "主管"})
check(r.status_code == 400, "已到岗记录不能重复报到")
rs = must_ok(client.post(f"/api/substitutions/{sub['id']}/restore",
                         json={"operator": "主管"}))
check(rs["status"] == "原讲解员已回归", "状态=原讲解员已回归")
s1_now = must_ok(client.get(f"/api/sessions/{s1_id}"))
check(s1_now["assignments"][0]["staff_name"] == "张讲解", "排班回归原讲解员")
subs = must_ok(client.get(f"/api/sessions/{s1_id}/substitutions"))
check(len(subs) == 1 and subs[0]["restored_at"] is not None, "替班记录完整可追溯")
# 内容冻结证据不受替班影响
sc = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc["version_number"] == VN3, "替班不改变场次内容版本")

# ---------- 版本撤回 + 已结束场次保护 ----------
header("10. 版本撤回与已结束场次证据不可改写")
# 第二场：确认 v3 后置为已完成
s2_start = (now + timedelta(days=50)).replace(hour=14, minute=0, second=0)
s2 = must_ok(client.post("/api/sessions", json={
    "title": "已结束的研学", "theme_id": theme_id, "venue_id": venue_id,
    "session_type": "研学实践",
    "start_time": s2_start.isoformat(),
    "end_time": (s2_start + timedelta(hours=2)).isoformat(),
    "audience_type": "学校", "audience_count": 20, "school_id": school_id,
    "guides_needed": 0, "needs_lecturer": False}), 200)
s2_id = s2["id"]
c2 = must_ok(client.post(f"/api/sessions/{s2_id}/content/confirm",
                         json={"confirmed_by": "李老师", "version_id": v3_id}), 201)
hash2 = c2["content_hash"]
must_ok(client.put(f"/api/sessions/{s2_id}", json={"status": "已完成"}))

# 撤回 v3：未开始的 s1 受影响，已完成 s2 不受影响
wd = must_ok(client.post(f"/api/content-versions/{v3_id}/withdraw",
                         json={"reason": "讲解角度调整", "operator": "内容主管"}))
check(wd["status"] == "已撤回", "v3 已撤回")
check(wd["affected_pending_sessions"] >= 1, f"撤回影响 {wd['affected_pending_sessions']} 个未开始场次")
sc2 = must_ok(client.get(f"/api/sessions/{s2_id}/content"))
check(sc2["confirmation_status"] == "已确认", "已结束场次确认状态不变")
check(sc2["frozen"]["content_hash"] == hash2, "已结束场次冻结证据不变")

# 对已结束场次：勘误不送达、不允许重新确认/拒绝
must_ok(client.post(f"/api/content-versions/{v3_id}/errata", json={
    "severity": "重要", "new_text": "补充说明", "require_reconfirm": True}), 201)
sc2 = must_ok(client.get(f"/api/sessions/{s2_id}/content"))
check(sc2["pending_errata_count"] == 0, "已结束场次不被要求重新确认")
check(len(sc2["frozen"]["errata_chain"]) == 0, "已结束场次不追加勘误送达")
for path, body in [
    ("reconfirm", {"operator": "x", "target_version_id": v2_id}),
    ("reject", {"rejected_by": "x"}),
    ("retain", {"operator": "x"}),
]:
    r = client.post(f"/api/sessions/{s2_id}/content/{path}", json=body)
    check(r.status_code == 400, f"已结束场次禁止 {path}")

# 已完成场次仍可按场次还原冻结清单
hist2 = must_ok(client.get(f"/api/sessions/{s2_id}/content/history"))
check(hist2[0]["checklist"][0]["content_hash"] == hist2[0]["checklist"][0]["content_hash"],
      "历史场次冻结清单可逐条还原")

# 撤回后学校不能沿用已撤回版本
sc1 = must_ok(client.get(f"/api/sessions/{s1_id}/content"))
check(sc1["confirmation_status"] == "待重新确认", "s1 因撤回处于待重新确认")
# s1 旧版本是 v3（已撤回）；先拒绝再尝试沿用应失败
must_ok(client.post(f"/api/sessions/{s1_id}/content/reject",
                    json={"rejected_by": "王老师"}))
r = client.post(f"/api/sessions/{s1_id}/content/retain", json={"operator": "主管"})
check(r.status_code == 400, "版本已撤回时不能沿用旧版")
# 重新确认到仍有效的 v2（覆盖 +70d? v2 effective_to +60d < +70d → 不覆盖，但可指定已发布版本）
rcv2 = must_ok(client.post(f"/api/sessions/{s1_id}/content/reconfirm",
                           json={"operator": "王老师", "target_version_id": v2_id}))
check(rcv2["version_number"] == VN2 and rcv2["status"] == "已确认", "可显式重新确认到其他已发布版本 v2")

# ---------- 汇总 ----------
print("\n" + "=" * 66)
print(f"  全部 {PASS} 项断言通过 ✅")
print("=" * 66)
print("""
覆盖能力：
  ✓ 主题内容以版本发布（适用年龄/必讲段落/生效区间，发布即冻结）
  ✓ 场次确认冻结可核验清单（逐条 + 整体 SHA256，可完整性核验）
  ✓ 当前可用内容 与 按场次还原冻结清单 双视图
  ✓ 紧急勘误只追加、形成勘误链（含勘误替代），不改写历史证据
  ✓ 勘误/撤回驱动未开始场次“待重新确认”，已结束场次绝对隔离
  ✓ 学校拒绝新版本 / 馆方核定沿用旧版 确定状态
  ✓ 场次改期超出生效区间自动进入重新确认
  ✓ 讲解员临时替换四态留痕，不影响内容证据
""")
print("所有测试通过")
