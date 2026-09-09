import json
from aeko_mcp.tools import fact_check, action_plan
from aeko_mcp.server import mcp


def test_fact_tools_are_read_only_and_keep_revision_and_scope(monkeypatch):
    calls = []
    def get(path, params=None):
        calls.append((path, params))
        return {'revision':'revision-2','state':'action_required','freshness':{'wiki_current':True,'source_current':False}}
    monkeypatch.setattr(fact_check.client, 'get', get)
    result = json.loads(fact_check.aeko_get_fact_check('brand-1', 'finding-1'))
    assert result['freshness']['source_current'] is False
    fact_check.aeko_list_fact_checks('brand-1', limit=999, offset=-1)
    assert calls[0] == ('/api/fact-check/finding-1', {'domain_id':'brand-1'})
    assert calls[1][1]['limit'] == 100 and calls[1][1]['offset'] == 0
    registered={t.name:t for t in mcp._tool_manager.list_tools()}
    for name in ('aeko_list_fact_checks','aeko_get_fact_check'):
        assert registered[name].annotations.readOnlyHint is True


def test_content_task_creation_preserves_the_review_and_retry_key(monkeypatch):
    calls=[]
    def post(path, json=None, headers=None):
        calls.append((path,json,headers)); return {'id':'itm_1'}
    monkeypatch.setattr(action_plan.client, 'post', post)
    action_plan.aeko_create_action_item(domain_id='brand-1',artifact_type='external_media_markdown',idempotency_key='correction-1',content_format='correction_request',content_task='request_correction',finding_id='finding-1',finding_revision='revision-2',target_country='KR',target_language='en',content_channel='correction_request')
    assert calls[0][1]['finding_revision']=='revision-2'
    assert calls[0][1]['content_task']=='request_correction'
    assert calls[0][2]=={'Idempotency-Key':'correction-1'}
