"""Actual backend in its unchanged Python environment; never shared UI cache."""
from pathlib import Path
import subprocess,threading,queue,json,uuid,os,time
from .contracts import ROOT,read_json,DashboardError
from .scenarios import scenario

class LiveJob:
    def __init__(self,key):
        scenario(key)
        if key=='rejection':raise DashboardError('The rejection excerpt is precomputed only. Run Adaptive recovery for its full live episode.')
        self.key=key;self.output=ROOT/'data/runs/dashboard_v1/live'/uuid.uuid4().hex
        self.output.mkdir(parents=True);self.events=[];self.error=None;self.bundle=None;self.started=time.perf_counter()
        self._queue=queue.Queue();self._done=False
        env=dict(os.environ,PYTHONPATH=str(ROOT/'src')+os.pathsep+str(ROOT))
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        self._process=subprocess.Popen([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/phase3a_live.py'),
            '--scenario',key,'--output',str(self.output)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',creationflags=flags)
        threading.Thread(target=self._read,daemon=True).start()
    def _read(self):
        with (self.output/'worker.log').open('w',encoding='utf-8') as log:
            for line in self._process.stdout:
                log.write(line);log.flush()
                try:
                    event=json.loads(line)
                    if event.get('dashboard_event'):self._queue.put(event)
                except ValueError:pass
        code=self._process.wait();self._queue.put(dict(dashboard_event='worker_finished',exit_code=code))
    def poll(self):
        while True:
            try:event=self._queue.get_nowait()
            except queue.Empty:break
            self.events.append(event)
            if event['dashboard_event']=='worker_finished':
                self._done=True
                if event['exit_code']==0:
                    try:self.bundle=read_json(self.output/'bundle.json')
                    except DashboardError:self.error='Live evidence unavailable. Recommendation withheld.'
                else:self.error='The deterministic run did not return accepted evidence. Review worker log; recommendation withheld.'
        return dict(done=self._done,error=self.error,bundle=self.bundle,events=list(self.events),elapsed=time.perf_counter()-self.started)
