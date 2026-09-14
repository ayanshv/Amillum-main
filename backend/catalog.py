"""Canonical plan configuration. Run as a module to print the catalog seed SQL."""
import json
from pathlib import Path

def plans():
    return json.loads((Path(__file__).parent/'config/plans.json').read_text())

if __name__=='__main__':
    print('begin;')
    for plan in plans():
        data=json.dumps(plan).replace("'","''")
        print("insert into public.billing_plans(id,config) values ('%s','%s'::jsonb) on conflict(id) do update set config=excluded.config;"%(plan['id'],data))
    print('commit;')
