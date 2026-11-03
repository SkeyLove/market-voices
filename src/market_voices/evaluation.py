"""Report separate dimensions; never substitute synthetic labels for human review."""
DIMENSIONS=('speaker','faithfulness','stance','quote','bilingual')


def evaluate(rows):
    report={'total':len(rows),'dimensions':{},'provenance':{}}
    for row in rows:
        origin=row.get('label_origin','unreviewed')
        report['provenance'][origin]=report['provenance'].get(origin,0)+1
    for dimension in DIMENSIONS:
        reviewed=[r for r in rows if r.get('label_origin')=='human' and
                  isinstance(r.get('checks',{}).get(dimension),bool)]
        correct=sum(r['checks'][dimension] for r in reviewed)
        report['dimensions'][dimension]={'reviewed':len(reviewed),'passed':correct,
                                         'rate':correct/len(reviewed) if reviewed else None}
    return report
