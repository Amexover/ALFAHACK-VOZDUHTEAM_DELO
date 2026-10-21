"""Приёмка только на отдельном демонстрационном стенде; сброс общей базы не вызывается."""
import argparse
import http.cookiejar
import json
import urllib.error
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--base', default='http://127.0.0.1:8081')
parser.add_argument('--isolated', action='store_true', required=True)
parser.add_argument('--verify', action='store_true')
parser.add_argument('--state', default='/tmp/delo-acceptance-state.json')
args = parser.parse_args()
assert args.base == 'http://127.0.0.1:8081', 'Only the isolated loopback stack on port 8081 is allowed.'
checks = 0

class Client:
    def __init__(self, login):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call('POST', '/auth/login', {'login': login, 'password': 'demo'})
    def call(self, method, path, body=None, expected=200):
        global checks
        raw = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(args.base + '/api' + path, data=raw, method=method, headers={'Content-Type': 'application/json'})
        try:
            res = self.opener.open(req, timeout=15)
        except urllib.error.HTTPError as exc:
            res = exc
        data = json.loads(res.read())
        assert res.code == expected, (method, path, res.code, expected, data)
        checks += 1
        return data

alexey, staff, maria = Client('alexey'), Client('staff'), Client('maria')
if args.verify:
    state = json.loads(Path(args.state).read_text())
    for key, app_id in state['ids'].items():
        app = alexey.call('GET', f'/applications/{app_id}')
        assert app['status'] == ('REJECTED' if key == 'rejected' else 'COMPLETED'), app
        assert app['events']
        checks += 2
    print(json.dumps({'result': 'PASS', 'phase': 'after-api-restart', 'checks': checks, 'ids': state['ids']}))
    raise SystemExit()

companies = alexey.call('GET', '/companies')['items']
ip = next(c for c in companies if c['legal_form'] == 'IP')
vector = next(c for c in companies if 'Вектор' in c['name'])
profile = {'industry': 'Синтетическое производство', 'months_operating': 36, 'monthly_revenue': 1800000, 'monthly_debt_payments': 120000, 'purpose_details': 'Изолированная проверка полного процесса.'}

def draft(cid, mode='NEW_CREDIT', **fields):
    a = alexey.call('POST', f'/companies/{cid}/applications', {'borrowing_mode': mode}, expected=201)
    aid = a['id']
    alexey.call('PATCH', f'/applications/{aid}', {'business_profile': profile, **fields})
    return aid

def submit(aid):
    return alexey.call('POST', f'/applications/{aid}/submit', {'confirm_data': True})

maria.call('GET', f"/companies/{ip['id']}/dashboard", expected=404)
alexey.call('GET', '/staff/applications', expected=403)
aid = draft(ip['id'], product_id='EQUIPMENT', amount=1500000, term_months=24)
alexey.call('PATCH', f'/applications/{aid}', {'amount': 3500000}, expected=422)
alexey.call('POST', f'/applications/{aid}/submit', {}, expected=422)
a = submit(aid)
assert a['preliminary_rate'] == 18 and a['preliminary_payment'] == 74886
checks += 2
alexey.call('POST', f'/applications/{aid}/submit', {'confirm_data': True}, expected=409)
maria.call('GET', f'/applications/{aid}', expected=404)
staff.call('POST', f'/staff/applications/{aid}/request-info', {'message': 'Уточните выручку', 'requested_fields': ['monthly_revenue']})
alexey.call('POST', f'/applications/{aid}/info-response', {'answer_text': 'Ответ', 'fields': {}}, expected=422)
alexey.call('POST', f'/applications/{aid}/info-response', {'answer_text': 'Выручка выросла', 'fields': {'monthly_revenue': 2100000}})
staff.call('POST', f'/staff/applications/{aid}/counter-offer', {'amount': 1200000, 'term_months': 24, 'rate': 19.5, 'comment': 'Другие условия по итогам рассмотрения'})
a = alexey.call('GET', f'/applications/{aid}')
assert a['decision']['monthly_payment'] == 60782
checks += 1
alexey.call('POST', f'/applications/{aid}/supplement', {'answer_text': 'Дополняем сведения для пересмотра', 'fields': {'monthly_revenue': 2400000}})
a = alexey.call('GET', f'/applications/{aid}')
assert a['status'] == 'IN_REVIEW' and a['decision'] is None
checks += 2
staff.call('POST', f'/staff/applications/{aid}/approve', {'comment': 'Одобрено после проверки дополнений'})
a = alexey.call('POST', f'/applications/{aid}/accept')
assert a['status'] == 'COMPLETED'
checks += 1
alexey.call('POST', f'/applications/{aid}/accept', expected=409)
loans = alexey.call('GET', f"/companies/{ip['id']}/loans")['items']
assert len(loans) == 1
checks += 1
rid = draft(ip['id'], 'REFINANCE', existing_loan_id=loans[0]['id'], term_months=24)
alexey.call('PATCH', f'/applications/{rid}', {'amount': 700000}, expected=422)
submit(rid)
staff.call('POST', f'/staff/applications/{rid}/counter-offer', {'amount': 500000, 'term_months': 24, 'rate': 17, 'comment': 'Частичное покрытие долга'})
a = alexey.call('GET', f'/applications/{rid}')
assert a['decision']['refinance_remainder'] == 100000 and a['decision']['refinance_remainder_text']
checks += 2
alexey.call('POST', f'/applications/{rid}/accept')
nid = draft(vector['id'], product_id='WORKING_CAPITAL')
submit(nid)
staff.call('POST', f'/staff/applications/{nid}/reject', {'reason_code': 'LOW_RATING', 'comment': 'Синтетический сценарий отказа'})
a = alexey.call('GET', f'/applications/{nid}')
assert a['status'] == 'REJECTED' and a['decision']['reason_text'] and not a['available_actions']
checks += 3
alexey.call('POST', f'/applications/{nid}/accept', expected=409)
news = alexey.call('GET', f"/news?company_id={ip['id']}&product_id=EQUIPMENT")['items']
assert len(news) == 6 and news[0]['tag'] == 'EQUIPMENT'
checks += 2
state = {'result': 'PASS', 'phase': 'postgres-full-flow', 'checks': checks, 'ids': {'completed_new': aid, 'completed_refinance': rid, 'rejected': nid}}
Path(args.state).write_text(json.dumps(state, indent=2))
print(json.dumps(state))
