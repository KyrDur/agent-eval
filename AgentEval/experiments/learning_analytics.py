"""Finite learning metadata only; original prose remains in workspace records."""
from datetime import datetime,timezone,timedelta
import hashlib,hmac
from .learning_pack import FAMILY_CODES

NAMES={'practice_started','initial_judgment_saved','hint_revealed','diagnosis_revised','prediction_saved','verification_completed','adoption_decided','transfer_started','transfer_submitted','transfer_feedback_revealed','feedback_recorded','practice_exited','practice_failed'}
FIELDS={'event_id','attempt_id','name','pack_id','pack_version','case_id','family_id','mode','hint_level','sequence','independent','stage','review_status'}

def initialize(store):
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS learning_metrics (
            event TEXT PRIMARY KEY, timestamp TEXT, visitor TEXT, attempt TEXT,
            name TEXT, pack TEXT, version TEXT, case_id TEXT, family TEXT, mode TEXT,
            hint INTEGER, sequence INTEGER, independent INTEGER, review TEXT)''')

def record(store,identity,value):
    if not isinstance(value,dict) or set(value)!=FIELDS or value['name'] not in NAMES:return False
    if value['pack_id']!='evidence-diagnosis-teaching' or value['pack_version']!='2026-10-16.v1':return False
    if value['case_id'] not in {f'p{i:02d}' for i in range(1,9)} or value['family_id'] not in set(FAMILY_CODES.values()):return False
    if value['mode'] not in {'TRAINING','FREE'} or type(value['hint_level']) is not int or not 0<=value['hint_level']<=3:return False
    if type(value['sequence']) is not int or not 1<=value['sequence']<=10000 or type(value['independent']) is not bool:return False
    if value['review_status'] not in {'PENDING_HUMAN_REVIEW','NOT_SUBMITTED'} or value['stage']!=value['name']:return False
    from uuid import UUID
    try:UUID(value['event_id']);UUID(value['attempt_id'])
    except (ValueError,TypeError,AttributeError):return False
    visitor=store.visitor(identity)
    hashed=lambda v:hmac.new(store.salt,(visitor+v).encode(),hashlib.sha256).hexdigest()
    with store.connect() as db:
        return bool(db.execute('INSERT OR IGNORE INTO learning_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(
            hashed(value['event_id']),datetime.now(timezone.utc).isoformat(),visitor,hashed(value['attempt_id']),
            value['name'],value['pack_id'],value['pack_version'],value['case_id'],value['family_id'],value['mode'],
            value['hint_level'],value['sequence'],int(value['independent']),value['review_status'])).rowcount)

def summarize(store,days,include_excluded):
    since=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat()
    where='timestamp>=?'+('' if include_excluded else ' AND visitor NOT IN (SELECT visitor FROM excluded)')
    with store.connect() as db:
        rows=[dict(r) for r in db.execute(f'SELECT * FROM learning_metrics WHERE {where}',(since,))]
    ids=lambda name:{r['attempt'] for r in rows if r['name']==name}
    entered=ids('transfer_started');submitted=ids('transfer_submitted')
    independent={r['attempt'] for r in rows if r['name']=='transfer_submitted' and r['independent']}
    highest={}
    for r in rows:highest[r['attempt']]=max(highest.get(r['attempt'],0),r['hint'])
    return {'unit':'尝试，不是人数','attempts_started':len(ids('practice_started')),
        'first_judgment_completed':len(ids('initial_judgment_saved')),
        'transfer_entered':len(entered),'transfer_submitted':len(submitted),
        'independent_submitted':len(independent),'transfer_unsubmitted':len(entered-submitted),
        'exited':len(ids('practice_exited')),'technical_failures':len(ids('practice_failed')),
        'highest_hint_counts':{str(i):sum(v==i for v in highest.values()) for i in range(4)},
        'independent_completion_rate':len(independent&entered)/len(entered) if entered else None,
        'learning_effect_verified':False,
        'notice':'全部进入迁移的尝试为分母，包含退出、未提交与待评；人工核验只保存在业务记录中，不由匿名埋点判断学习达标。'}
