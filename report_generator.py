import os
import webbrowser
from datetime import datetime

REPORTS_DIR = "reports"


def generate_report(logs: list, mode: str, counts: dict, elapsed: float) -> str:
    folder = "dry_run" if mode == "dry_run" else "clean_wipe"
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = os.path.join(REPORTS_DIR, folder, timestamp)
    os.makedirs(report_dir, exist_ok=True)

    report_path = os.path.join(report_dir, "index.html")
    html = _build_html(logs, mode, counts, elapsed)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    try:
        webbrowser.open(os.path.abspath(report_path))
    except Exception:
        pass

    return report_path


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _build_html(logs: list, mode: str, counts: dict, elapsed: float) -> str:
    rows_html = ""
    for log in logs:
        category = log.get("category", "okay")
        badge_class = f"badge-{category}" if category in ("important", "okay", "unwanted") else "badge-okay"
        action = log.get("action", "KEPT")
        action_class = {
            "KEPT": "action-kept",
            "DELETED": "action-deleted",
            "DRY_RUN": "action-dryrun",
            "DELETE_FAILED": "action-failed",
        }.get(action.split(":")[0], "")

        sender = _escape(log.get("sender", ""))
        subject = _escape(log.get("subject", ""))
        reason = _escape(log.get("reason", ""))
        action_display = _escape(action)

        rows_html += f"""
                    <tr data-category="{category}">
                        <td class="cell-sender" title="{sender}">{sender}</td>
                        <td class="cell-subject" title="{subject}">{subject}</td>
                        <td><span class="badge {badge_class}">{category}</span></td>
                        <td class="cell-reason" title="{reason}">{reason}</td>
                        <td><span class="action {action_class}">{action_display}</span></td>
                    </tr>"""

    mode_display = "DRY RUN" if mode == "dry_run" else "CLEAN WIPE"
    mode_class = "mode-dry" if mode == "dry_run" else "mode-wipe"
    date_display = datetime.now().strftime("%B %d, %Y &middot; %I:%M %p")
    total = sum(counts.values())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InboxGuard &mdash; {mode_display} Report</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
            background:#0d1117;color:#c9d1d9;min-height:100vh;
        }}

        /* ── header ─────────────────────────────── */
        .header{{
            background:linear-gradient(135deg,#161b22 0%,#1a1225 100%);
            border-bottom:1px solid #30363d;padding:1.8rem 2.5rem;
        }}
        .header-row{{display:flex;align-items:center;justify-content:space-between}}
        .logo{{font-size:1.4rem;font-weight:700;color:#58a6ff;letter-spacing:-.5px}}
        .logo span{{color:#f0883e}}
        .mode-tag{{
            padding:.35rem .9rem;border-radius:20px;
            font-weight:600;font-size:.8rem;letter-spacing:.4px;
        }}
        .mode-dry{{
            background:rgba(227,179,65,.12);color:#e3b341;
            border:1px solid rgba(227,179,65,.25);
        }}
        .mode-wipe{{
            background:rgba(248,81,73,.12);color:#f85149;
            border:1px solid rgba(248,81,73,.25);
        }}
        .header-sub{{color:#8b949e;font-size:.85rem;margin-top:.4rem}}

        /* ── container ──────────────────────────── */
        .wrap{{max-width:1280px;margin:0 auto;padding:1.8rem 2rem}}

        /* ── stat cards ─────────────────────────── */
        .stats{{
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
            gap:.9rem;margin-bottom:1.8rem;
        }}
        .card{{
            background:#161b22;border:1px solid #30363d;
            border-radius:10px;padding:1.1rem;text-align:center;
        }}
        .card .num{{font-size:1.9rem;font-weight:700;line-height:1.2}}
        .card .lbl{{
            color:#8b949e;font-size:.75rem;
            text-transform:uppercase;letter-spacing:.4px;margin-top:.25rem;
        }}
        .c-imp .num{{color:#3fb950}} .c-ok .num{{color:#58a6ff}}
        .c-unw .num{{color:#e3b341}} .c-fail .num{{color:#f85149}}
        .c-time .num{{color:#bc8cff;font-size:1.4rem}}

        /* ── table chrome ───────────────────────── */
        .tbl-wrap{{
            background:#161b22;border:1px solid #30363d;
            border-radius:10px;overflow:hidden;
        }}
        .tbl-bar{{
            padding:.85rem 1.2rem;border-bottom:1px solid #30363d;
            display:flex;align-items:center;gap:1rem;flex-wrap:wrap;
        }}
        .tbl-bar h2{{font-size:.95rem;font-weight:600;white-space:nowrap}}
        .tbl-bar .spacer{{flex:1}}
        .search{{
            background:#0d1117;border:1px solid #30363d;color:#c9d1d9;
            padding:.35rem .7rem;border-radius:6px;font-size:.82rem;width:200px;
            outline:none;transition:border .2s;
        }}
        .search:focus{{border-color:#58a6ff}}
        .search::placeholder{{color:#484f58}}
        .filters{{display:flex;gap:.35rem}}
        .fbtn{{
            background:#21262d;border:1px solid #30363d;color:#8b949e;
            padding:.3rem .7rem;border-radius:6px;cursor:pointer;
            font-size:.78rem;transition:all .15s;
        }}
        .fbtn:hover,.fbtn.on{{
            color:#c9d1d9;border-color:#58a6ff;
            background:rgba(88,166,255,.08);
        }}

        /* ── table ──────────────────────────────── */
        table{{width:100%;border-collapse:collapse}}
        thead th{{
            background:#1c2128;padding:.65rem 1rem;text-align:left;
            font-weight:600;font-size:.75rem;text-transform:uppercase;
            letter-spacing:.4px;color:#8b949e;border-bottom:1px solid #30363d;
            position:sticky;top:0;
        }}
        tbody tr{{border-bottom:1px solid #21262d;transition:background .12s}}
        tbody tr:hover{{background:#1c2128}}
        tbody tr.hide{{display:none}}
        td{{padding:.6rem 1rem;font-size:.85rem}}
        .cell-sender,.cell-reason{{
            max-width:220px;overflow:hidden;
            text-overflow:ellipsis;white-space:nowrap;color:#8b949e;
        }}
        .cell-subject{{
            max-width:360px;overflow:hidden;
            text-overflow:ellipsis;white-space:nowrap;
        }}
        .cell-reason{{font-size:.8rem}}

        /* badges */
        .badge{{
            padding:.15rem .55rem;border-radius:10px;
            font-size:.72rem;font-weight:600;text-transform:uppercase;
        }}
        .badge-important{{background:rgba(63,185,80,.12);color:#3fb950}}
        .badge-okay{{background:rgba(88,166,255,.12);color:#58a6ff}}
        .badge-unwanted{{background:rgba(227,179,65,.12);color:#e3b341}}

        .action{{font-size:.78rem;font-weight:600}}
        .action-kept{{color:#3fb950}}
        .action-deleted{{color:#f85149}}
        .action-dryrun{{color:#e3b341}}
        .action-failed{{color:#f85149}}

        .empty{{padding:2.5rem;text-align:center;color:#484f58}}
        .footer{{text-align:center;padding:1.5rem;color:#30363d;font-size:.75rem}}

        @media(max-width:768px){{
            .wrap{{padding:1rem}}
            .cell-sender,.cell-subject,.cell-reason{{max-width:140px}}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-row">
            <div class="logo">Inbox<span>Guard</span></div>
            <span class="mode-tag {mode_class}">{mode_display}</span>
        </div>
        <div class="header-sub">{date_display} &middot; {total} emails in {elapsed:.1f}s</div>
    </div>

    <div class="wrap">
        <div class="stats">
            <div class="card c-imp">
                <div class="num">{counts.get('important',0)}</div>
                <div class="lbl">Important</div>
            </div>
            <div class="card c-ok">
                <div class="num">{counts.get('okay',0)}</div>
                <div class="lbl">Okay</div>
            </div>
            <div class="card c-unw">
                <div class="num">{counts.get('unwanted',0)}</div>
                <div class="lbl">Unwanted</div>
            </div>
            <div class="card c-fail">
                <div class="num">{counts.get('failed',0)}</div>
                <div class="lbl">Failed</div>
            </div>
            <div class="card c-time">
                <div class="num">{elapsed:.1f}s</div>
                <div class="lbl">Duration</div>
            </div>
        </div>

        <div class="tbl-wrap">
            <div class="tbl-bar">
                <h2>Email Classifications</h2>
                <div class="spacer"></div>
                <input class="search" type="text" id="search" placeholder="Search sender or subject…">
                <div class="filters">
                    <button class="fbtn on" data-f="all">All ({total})</button>
                    <button class="fbtn" data-f="important">Important ({counts.get('important',0)})</button>
                    <button class="fbtn" data-f="okay">Okay ({counts.get('okay',0)})</button>
                    <button class="fbtn" data-f="unwanted">Unwanted ({counts.get('unwanted',0)})</button>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Sender</th>
                        <th>Subject</th>
                        <th>Category</th>
                        <th>Reason</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="rows">{rows_html}
                </tbody>
            </table>
            <div class="empty" id="empty" style="display:none">No emails match your filter.</div>
        </div>
    </div>

    <div class="footer">InboxGuard v1.0 &mdash; AI-powered email cleanup</div>

    <script>
    (function(){{
        const rows=document.querySelectorAll('#rows tr');
        const btns=document.querySelectorAll('.fbtn');
        const input=document.getElementById('search');
        const empty=document.getElementById('empty');
        let curFilter='all';

        function apply(){{
            const q=input.value.toLowerCase();
            let visible=0;
            rows.forEach(r=>{{
                const cat=r.dataset.category;
                const text=r.textContent.toLowerCase();
                const matchCat=curFilter==='all'||cat===curFilter;
                const matchQ=!q||text.includes(q);
                if(matchCat&&matchQ){{r.classList.remove('hide');visible++}}
                else{{r.classList.add('hide')}}
            }});
            empty.style.display=visible?'none':'block';
        }}

        btns.forEach(b=>b.addEventListener('click',()=>{{
            btns.forEach(x=>x.classList.remove('on'));
            b.classList.add('on');
            curFilter=b.dataset.f;
            apply();
        }}));

        input.addEventListener('input',apply);
    }})();
    </script>
</body>
</html>"""
