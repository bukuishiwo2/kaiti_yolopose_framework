#!/usr/bin/env python3
"""Read-only local viewer for saved Clinic experiments."""
import argparse
import json
import mimetypes
import re
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / 'web' / 'clinic'
PUBLISHED = WEB / 'evidence'
REPORTS = {
    '研究实验目录与任务规划说明': 'docs/clinic_research_experiment_guide.md',
    '第二轮工作台评审': 'docs/reviews/clinic_workbench_explainability_2026-11-24.md',
    '节点与路径来源': 'docs/reviews/clinic_node_path_sources_2026-11-24.md',
    '三次修复诊断': 'docs/reviews/clinic_three_repairs_diagnosis_2026-11-24.md',
    '最新评审': 'docs/reviews/clinic_temporal_logic_adoption_2026-11-23.md',
    '在线协同配对': 'reports/benchmarks/clinic_online_pair_2026-11-26.md',
    '路径拒绝反馈重规划': 'reports/benchmarks/clinic_feedback_repair_2026-11-26.md',
    'EPW2 进站资格对照': 'reports/benchmarks/clinic_epw2_qualification_2026-11-26.md',
    'A 区空间站位分阶段验收': 'reports/benchmarks/clinic_spatial_stand_2026-11-26.md',
    '应急插入四格对照': 'reports/benchmarks/clinic_factorial_2026-11-25.md',
    '动态分配': 'reports/benchmarks/clinic_dynamic_assignment_2026-11-18.md',
    '修复对照': 'reports/benchmarks/clinic_repair_methods_2026-11-18.md',
    '视觉正例': 'reports/benchmarks/clinic_visual_positive_2026-11-18.md',
    '实体床': 'reports/benchmarks/clinic_visual_bed_2026-11-18.md',
}

# Keep the historical API entry points importable; all reads now share one cached adapter.
sys.path.insert(0, str(REPO / 'src'))
from kaiti_review.data import (
    ASSETS, catalog, descriptors, load_map, load_run, paged_events, raw_line, offline_rows,
)
from kaiti_review.explanations import catalog_metadata, research_catalog

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path('/home/yhc/clinic_planning_ws'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    root = args.workspace.resolve()
    docs = {name: REPO / path for name, path in REPORTS.items()}
    docs.update({'运行手册': root / 'README_CLINIC_RUNTIME.md', '分级模式': root / 'README_CLINIC_MODES.md'})
    docs['工作台手册'] = WEB / 'README.md'

    def latest(prefix):
        batches = sorted((root/'verification').glob(f'{prefix}_*/viewer.json'), reverse=True)
        fallback = PUBLISHED / f'{prefix}.json'
        selected = batches[0] if batches else fallback
        return json.loads(selected.read_text()) if selected.is_file() else None

    class Handler(BaseHTTPRequestHandler):
        def reply(self, value, mime='application/json; charset=utf-8', status=200):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if mime.startswith('application/json') else value
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == '/api/catalog':
                    self.reply({'runs': catalog(root), 'metadata': catalog_metadata(root, descriptors(root)),
                                'research_catalog': research_catalog(), 'documents': list(docs),
                                'workspace': str(root), 'read_only': True})
                elif url.path == '/api/online-pair':
                    self.reply(latest('online_pair'))
                elif url.path == '/api/feedback-repair':
                    self.reply(latest('feedback_repair'))
                elif url.path == '/api/epw2-qualification':
                    self.reply(latest('epw2_qualification'))
                elif url.path == '/api/spatial-stand':
                    self.reply(latest('spatial_stand'))
                elif url.path == '/api/factorial':
                    name = query.get('name', [''])[0]
                    verification = root / 'verification'
                    if name:
                        if not re.fullmatch(r'factorial_[\w-]+', name):
                            raise ValueError('实验名称无效。')
                        self.reply(json.loads((verification / name / 'viewer.json').read_text()))
                    else:
                        self.reply(sorted((p.parent.name for p in verification.glob('factorial_*/viewer.json')),
                                          reverse=True))
                elif url.path == '/api/run':
                    self.reply(load_run(root, query.get('name', [''])[0]))
                elif url.path == '/api/map':
                    self.reply(load_map(root))
                elif url.path == '/api/events':
                    self.reply(paged_events(root, query.get('name', [''])[0],
                                            query.get('q', [''])[0], query.get('page', ['0'])[0],
                                            query.get('size', ['80'])[0]))
                elif url.path == '/api/raw':
                    self.reply(raw_line(root, query.get('name', [''])[0], query.get('line', ['0'])[0]))
                elif url.path == '/api/offline':
                    self.reply(offline_rows(root))
                elif url.path == '/api/asset':
                    path = ASSETS.get(query.get('id', [''])[0])
                    if path is None:
                        raise ValueError('未注册的证据资产；先读取其运行。')
                    self.reply(path.read_bytes(), mimetypes.guess_type(path)[0] or 'application/octet-stream')
                elif url.path == '/api/document':
                    self.reply(docs[query.get('id', [''])[0]].read_bytes(), 'text/plain; charset=utf-8')
                elif url.path in ('/factorial.html', '/factorial.js', '/factorial.css', '/online-pair.js', '/online-pair.css'):
                    path = WEB / url.path[1:]
                    self.reply(path.read_bytes(), mimetypes.guess_type(path)[0] + '; charset=utf-8')
                elif url.path in ('/review.js', '/review.css', '/platform.js', '/platform.css', '/explain.js', '/explain.css'):
                    mime = 'text/javascript; charset=utf-8' if url.path.endswith('.js') else 'text/css; charset=utf-8'
                    self.reply((WEB / url.path[1:]).read_bytes(), mime)
                elif url.path in ('/', '/index.html'):
                    self.reply((WEB / 'index.html').read_bytes(), 'text/html; charset=utf-8')
                elif url.path == '/favicon.ico':
                    self.reply(b'', 'image/x-icon', 204)
                else:
                    self.reply({'error': '页面不存在'}, status=404)
            except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
                self.reply({'error': str(error)}, status=400)

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Clinic review: http://127.0.0.1:{args.port} · 只读', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
