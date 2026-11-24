"""Reuse the frozen Spot generator with checked finite-DFA totalization.

The original generator assumes to_finite preserves completeness. The first
attempt on the new safety specifications returned missing transitions instead.
This isolated adapter invokes Spot.complete after to_finite, verifies that
existing transitions and acceptance are preserved, and checks that every newly
filled transition leads only to permanently rejecting finite continuations.
The original generator, its original specifications and its tables are not
modified. Generation is not execution-trace acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import buddy
import spot

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT/'scripts/generate_ltlf_transition_tables.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def graph_rows(generator, automaton):
    propositions = sorted((str(item), item) for item in automaton.ap())
    rows = {}
    for state in range(automaton.num_states()):
        row = []
        for mask in range(1 + (2**len(propositions)-1)):
            cube = generator._valuation_cube(automaton, propositions, mask)
            destinations = sorted({
                int(edge.dst) for edge in automaton.out(state)
                if (edge.cond & cube) != buddy.bddfalse})
            if len(destinations) > 1:
                raise RuntimeError('Finite automaton is not deterministic.')
            row.append(destinations[0] if destinations else None)
        rows[state] = row
    return [name for name, _ in propositions], rows


def generate(source, output, audit_output):
    for path in (output, audit_output):
        if path.exists():
            raise FileExistsError('Existing generation evidence must not be overwritten: '+str(path))
    spec = importlib.util.spec_from_file_location('original_ltlf_generator_isolated', ORIGINAL)
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    completion_audits = []

    def completed_finite(buchi):
        partial = spot.to_finite(buchi)
        before_ap, before = graph_rows(generator, partial)
        before_accepting = {
            state:bool(partial.state_is_accepting(state))
            for state in before}
        completed = spot.complete(partial)
        after_ap, after = graph_rows(generator, completed)
        if before_ap != after_ap or any(
                destination is None for row in after.values() for destination in row):
            raise RuntimeError('Finite totalization changed propositions or remains incomplete.')
        if any(state not in after for state in before):
            raise RuntimeError('Cannot verify original finite state identities after completion.')
        if any(bool(completed.state_is_accepting(state)) != accepting
               for state, accepting in before_accepting.items()):
            raise RuntimeError('Totalization changed an original finite accepting state.')
        filled = set()
        retained = 0
        for state, row in before.items():
            for mask, destination in enumerate(row):
                if destination is None:
                    filled.add(after[state][mask])
                elif destination != after[state][mask]:
                    raise RuntimeError('Totalization changed an original finite transition.')
                else:
                    retained += 1
        for start in filled:
            pending, visited = [start], set()
            while pending:
                state = pending.pop()
                if state in visited:
                    continue
                visited.add(state)
                if completed.state_is_accepting(state):
                    raise RuntimeError('A missing partial transition acquired an accepting continuation.')
                pending.extend(after[state])
        completion_audits.append(dict(
            original_states=len(before), total_states=len(after),
            original_transitions_preserved=retained,
            missing_original_transitions=sum(
                destination is None for row in before.values() for destination in row),
            completed_transition_count=sum(len(row) for row in after.values()),
            original_acceptance_preserved=True,
            filled_transitions_have_no_accepting_continuation=True,
            finite_language_preservation='PASS_STRUCTURAL',
            execution_trace_validation_run=False))
        return completed

    # Replace only this locally imported generator reference, not the installed
    # Spot module or any original source file.
    generator.spot = SimpleNamespace(
        from_ltlf=spot.from_ltlf, to_finite=completed_finite, version=spot.version)
    raw = json.loads(source.read_text())
    tables = []
    for item in raw['specifications']:
        previous = len(completion_audits)
        tables.append(generator.build_transition_table(item))
        if len(completion_audits) != previous+1:
            raise RuntimeError('Unexpected number of finite translations.')
        completion_audits[-1]['specification_id'] = item['id']
    payload = dict(
        schema_version=1, source_path=str(source.resolve().relative_to(ROOT)),
        source_sha256=sha(source),
        generator=dict(
            name='Spot', version=spot.version(),
            pipeline='from_ltlf -> deterministic complete buchi/sbacc -> to_finite -> Spot.complete',
            reused_generator=str(ORIGINAL), reused_generator_sha256=sha(ORIGINAL),
            finite_completion='Missing finite transitions are totalized into rejecting continuations; original language preservation is checked structurally.'),
        specifications=tables)
    audit = dict(
        schema='clinic-finite-completion-audit/v1',
        status='PASS_GENERATION_AND_STRUCTURAL_COMPLETION',
        source_sha256=sha(source), specification_count=len(tables),
        audits=completion_audits, actual_execution_validation='NOT_RUN')
    for path, value in ((output, payload), (audit_output, audit)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write(chr(10))
    print(json.dumps(dict(
        status=audit['status'], output=str(output),
        specification_count=len(tables),
        actual_execution_validation='NOT_RUN'), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audit-output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.source, args.output, args.audit_output)
