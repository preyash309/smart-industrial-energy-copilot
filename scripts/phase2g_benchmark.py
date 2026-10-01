"""Run G0, offline wire mock, or configured live G1 against one fixed manifest."""
from pathlib import Path
import argparse,json
from energy_copilot.common import write_json
from energy_copilot.supervisor.benchmark import run_benchmark,cases
from energy_copilot.supervisor import RuleBasedModel,MockSupervisorModel,APISupervisorModel
from energy_copilot.supervisor.policy import configuration,guard


def main():
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=['rule','mock','api'],required=True);a=p.parse_args()
    if Path('supervision/supervisor_v1/release_manifest.json').exists():raise RuntimeError('Benchmark release is frozen')
    manifest=Path('configs/supervisor_benchmark_v1.json')
    if not manifest.exists():write_json(manifest,dict(version='supervisor_benchmark_v1',scope='SCRIPTED-TEST-DOUBLE',cases=cases()))
    matrix=json.loads(manifest.read_text())['cases'];guard()
    model=RuleBasedModel() if a.provider=='rule' else MockSupervisorModel() if a.provider=='mock' else APISupervisorModel(configuration())
    summary=run_benchmark(Path('supervision/supervisor_v1/benchmark')/a.provider,model,manifest=matrix)
    guard();print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
