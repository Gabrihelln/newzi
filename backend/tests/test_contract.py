import json
import os

import contract_scenario
import servers


def test_api_contract_matches_golden():
    with servers.running(os.getenv("TEST_DATABASE_URL")) as (base_url, seed):
        records = contract_scenario.run(base_url, seed)
    golden = json.loads(contract_scenario.GOLDEN.read_text(encoding="utf-8"))
    problems = contract_scenario.compare(records, golden)
    assert not problems, "\n".join(problems)
