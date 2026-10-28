"""Export the root raw review without changing its scoring rules."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def write_csv(name, rows):
    path = HERE / name
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    review = json.loads((HERE / 'C2_FULL_PRIMARY_RAW_REVIEW.json').read_text())
    assert review['new_candidate_runs'] == 12 and len(review['rows']) == 36
    rows = [{k: v for k, v in row.items() if k != 'event_checks'} for row in review['rows']]
    write_csv('C2_ALL_36_PER_RUN.csv', rows)
    write_csv('C2_ALL_24_PAIRED.csv', review['paired'])
    losses = [row for row in review['paired'] if row['result'] == 'LOSS']
    if losses:
        write_csv('C2_ALL_LOSSES.csv', losses)
    groups = []
    for group, data in review['groups'].items():
        for condition, mean in data['mean_Q_m'].items():
            groups.append({'group': group, 'n': data['n'], 'condition': condition,
                           'mean_Q_m': mean})
    write_csv('C2_GROUP_Q.csv', groups)
    print(json.dumps({'runs': len(rows), 'pairs': len(review['paired']),
                      'losses': len(losses), 'groups': len(groups)}))


if __name__ == '__main__':
    main()
