import json
from pathlib import Path

root = Path(__file__).parent
history = json.loads((root / 'history.json').read_text())
cases = json.loads((root / 'cases.json').read_text())
for split in ('development', 'held-out'):
    for mode in ('literal', 'structured'):
        hits = total = 0
        for case in (case for case in cases if case['split'] == split):
            candidates = [row['id'] for row in history if
                          (row['description'].casefold() == case['description'].casefold()
                           if mode == 'literal' else row['spec'] == case['spec'] and row['verified'])][:25]
            total += len(case['gold'])
            hits += len(set(candidates) & set(case['gold']))
        print(f'{split} {mode}: {hits}/{total} gold IDs at budget 25')
