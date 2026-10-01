"""Append-only episode records; public summaries and concise rationale, no CoT."""
from dataclasses import dataclass
from pathlib import Path
import json, time
from .contracts import digest, primitive, BoundaryError


class AuditLog:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory else None
        if self.directory:
            self.directory.mkdir(parents=True,exist_ok=False)
        self.records=[];self.started=time.perf_counter()
        self.metrics=dict(tool_calls=0,optimizer_calls=0,replay_calls=0,failed_tool_calls=0,replans=0,
                          model_calls=0,llm_latency_seconds=0.0,input_tokens=0,output_tokens=0,estimated_API_cost=None)

    def append(self,kind,payload):
        row=dict(sequence=len(self.records),kind=kind,payload=primitive(payload),
                 previous_sha256=self.records[-1]['record_sha256'] if self.records else None)
        row['record_sha256']=digest(row);self.records.append(row)
        if self.directory:
            with (self.directory/'audit.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,allow_nan=False)+'\n')
        return row

    def finish(self,packet):
        self.metrics['wall_clock_seconds']=time.perf_counter()-self.started
        self.append('final_disposition',packet.to_dict())
        if self.directory:
            for name,value in [('decision_packet.json',packet.to_dict()),('observability.json',self.metrics)]:
                (self.directory/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')

    def verify_chain(self):
        previous=None
        for row in self.records:
            copy=dict(row);h=copy.pop('record_sha256')
            if copy['previous_sha256']!=previous or digest(copy)!=h:raise BoundaryError('Audit chain altered')
            previous=h
        return True
