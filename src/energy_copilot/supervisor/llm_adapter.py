"""Provider-agnostic JSON chat transport. Offline mock is NOT LLM evidence."""
from dataclasses import dataclass
from typing import Protocol
import json, os, time
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from .contracts import SupervisorAction,BoundaryError,ServiceUnavailable
from .policy import PROMPT


class SupervisorModel(Protocol):
    name:str
    is_live_llm:bool
    def decide(self,context,tools)->SupervisorAction:...


def parse_action(node):
    if not isinstance(node,dict) or not {'tool'}<=set(node)<= {'tool','plan_mode'}:raise BoundaryError('Model action schema mismatch')
    return SupervisorAction(**node).validate()


class MockSupervisorModel:
    name='G1-MOCK-protocol';is_live_llm=False
    def decide(self,context,tools):
        # Tests the wire/schema boundary. It intentionally follows supplied routing.
        wire=json.dumps(dict(tool=context['required_next_tool'],plan_mode=context.get('next_plan_mode')))
        return parse_action(json.loads(wire))


class APISupervisorModel:
    is_live_llm=True
    def __init__(self,config,transport=None):
        api=config['api'];self.endpoint=os.environ.get(api['endpoint_environment']);self.model=os.environ.get(api['model_environment'])
        self.key=os.environ.get(api['credential_environment']);self.timeout=config['api_timeout_seconds'];self.limit=config['maximum_response_bytes']
        self.name='G1-API:'+str(self.model);self.last_usage={};self.transport=transport
        if not self.endpoint or not self.model:raise ServiceUnavailable('LLM endpoint/model not configured')
        u=urlparse(self.endpoint)
        local=api['allow_local_http'] and u.hostname in ('127.0.0.1','localhost','::1')
        if u.username or u.password or u.query or u.fragment or (u.scheme!='https' and not(local and u.scheme=='http')):
            raise BoundaryError('Invalid trusted API endpoint')
        if not local and not self.key:raise ServiceUnavailable('LLM credential not configured')

    def decide(self,context,tools):
        # No files, secrets, raw tables, arbitrary code, or tool bindings sent remotely.
        public_context={k:v for k,v in context.items() if k not in ('required_next_tool','next_plan_mode')}
        body=dict(model=self.model,messages=[dict(role='system',content=PROMPT),
            dict(role='user',content=json.dumps(dict(public_context=public_context,allowed_tools=tools),allow_nan=False))],
            response_format={'type':'json_object'},temperature=0)
        started=time.perf_counter()
        if self.transport:response=self.transport(body)
        else:
            headers={'Content-Type':'application/json'}
            if self.key:headers['Authorization']='Bearer '+self.key
            req=Request(self.endpoint,data=json.dumps(body).encode(),headers=headers,method='POST')
            try:
                with urlopen(req,timeout=self.timeout) as handle:
                    raw=handle.read(self.limit+1)
                if len(raw)>self.limit:raise BoundaryError('Oversized model response')
                response=json.loads(raw)
            except BoundaryError:raise
            except Exception:raise ServiceUnavailable('LLM API unavailable') from None
        if len(json.dumps(response).encode())>self.limit:raise BoundaryError('Oversized model response')
        try:
            usage=response.get('usage',{});self.last_usage=dict(input_tokens=int(usage.get('prompt_tokens',0)),output_tokens=int(usage.get('completion_tokens',0)),
                latency_seconds=time.perf_counter()-started,usage_reported=bool(usage),model=self.model)
            if min(self.last_usage['input_tokens'],self.last_usage['output_tokens'])<0:raise ValueError
            action=parse_action(json.loads(response['choices'][0]['message']['content']))
        except (KeyError,IndexError,ValueError,TypeError):raise BoundaryError('Invalid API action response') from None
        return action
