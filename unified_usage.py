#!/usr/bin/env python3
import html
import json
import os
from datetime import datetime, timedelta, timezone


def fmt_local_dt(dt):
    hour_12 = dt.hour % 12
    if hour_12 == 0:
        hour_12 = 12
    am_pm = "am" if dt.hour < 12 else "pm"
    return f"{dt.strftime('%b')} {dt.day}, {hour_12}:{dt.minute:02d}{am_pm}"


def fmt_local_time(dt):
    hour_12 = dt.hour % 12
    if hour_12 == 0:
        hour_12 = 12
    am_pm = "am" if dt.hour < 12 else "pm"
    return f"{hour_12}:{dt.minute:02d}{am_pm}"


def fmt_count(n):
    if n >= 1_000_000:
        val = n / 1_000_000
        return f"{val:.0f}M" if val.is_integer() else f"{val:.1f}M"
    if n >= 1_000:
        val = n / 1_000
        return f"{val:.0f}K" if val >= 100 or val.is_integer() else f"{val:.1f}K"
    return str(int(n))


def fmt_bytes(b):
    if b >= 1024 ** 3:
        val = b / (1024 ** 3)
        return f"{val:.0f}GB" if val.is_integer() else f"{val:.2f}GB"
    if b >= 1024 ** 2:
        val = b / (1024 ** 2)
        return f"{val:.0f}MB" if val >= 100 else f"{val:.1f}MB"
    if b >= 1024:
        return f"{b / 1024:.0f}KB"
    return f"{int(b)}B"


def status_level(pct):
    if pct >= 85:
        return "crit"
    if pct >= 60:
        return "warn"
    return "ok"


def get_cloudflare_usage():
    storage_data = []
    ops_data = []
    resets_meta = {}
    env_vars = {}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    env_vars[k] = v
    except FileNotFoundError:
        pass

    account_id = env_vars.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = env_vars.get("CLOUDFLARE_API_TOKEN")
    d1_id = env_vars.get("CLOUDFLARE_D1_DATABASE_ID")
    bucket = env_vars.get("R2_BUCKET_NAME")

    # Free Tier Limits
    D1_CAPACITY_BYTES = 5 * 1024 ** 3   # 5 GB
    R2_CAPACITY_BYTES = 10 * 1024 ** 3  # 10 GB
    D1_READS_LIMIT = 5_000_000
    D1_WRITES_LIMIT = 100_000
    R2_CLASS_A_LIMIT = 1_000_000
    R2_CLASS_B_LIMIT = 10_000_000

    if not account_id or not api_token:
        return [], resets_meta

    import requests

    # Fetch D1 Size using token that has D1 permissions
    if d1_id:
        old_token = api_token
        try:
            # .env of the trading repo, whose CLOUDFLARE_API_TOKEN has D1 permissions
            with open(env_vars["TRADING_ENV_FILE"]) as f:
                for line in f:
                    if line.startswith("CLOUDFLARE_API_TOKEN="):
                        old_token = line.strip().split("=", 1)[1]
        except Exception:
            pass

        headers = {"Authorization": f"Bearer {old_token}", "Content-Type": "application/json"}
        try:
            res = requests.get(
                f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{d1_id}",
                headers=headers,
                timeout=15,
            )
            if res.status_code == 200:
                d1_size = res.json()["result"]["file_size"]
                d1_name = res.json()["result"]["name"]
                used_pct = (d1_size / D1_CAPACITY_BYTES) * 100
                storage_data.append({
                    "label": "D1 Storage",
                    "tag": d1_name,
                    "pct": round(used_pct, 1),
                    "pct_str": f"{used_pct:.1f}%",
                    "detail": f"{fmt_bytes(d1_size)} / 5GB",
                    "level": status_level(used_pct),
                })
        except Exception:
            pass

    # Fetch R2 Size via boto3
    if bucket and env_vars.get("R2_ACCESS_KEY_ID") and env_vars.get("R2_SECRET_ACCESS_KEY"):
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=env_vars.get("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=env_vars.get("R2_SECRET_ACCESS_KEY"),
                region_name="auto",
            )
            total_bytes = 0
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket):
                total_bytes += sum(obj["Size"] for obj in page.get("Contents", []))
            used_pct = (total_bytes / R2_CAPACITY_BYTES) * 100
            storage_data.append({
                "label": "R2 Storage",
                "tag": bucket,
                "pct": round(used_pct, 1),
                "pct_str": f"{used_pct:.1f}%",
                "detail": f"{fmt_bytes(total_bytes)} / 10GB",
                "level": status_level(used_pct),
            })
        except Exception:
            pass

    # Fetch Operations via GraphQL
    try:
        now_utc = datetime.now(timezone.utc)
        start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Calculate exact reset times in local timezone
        next_midnight_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_midnight_local = next_midnight_utc.astimezone()

        if now_utc.month == 12:
            next_month_utc = now_utc.replace(year=now_utc.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_utc = now_utc.replace(month=now_utc.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month_local = next_month_utc.astimezone()

        resets_meta["d1_reset"] = fmt_local_time(next_midnight_local)
        resets_meta["r2_reset"] = fmt_local_dt(next_month_local)

        q = """
        query {
          viewer {
            accounts(filter: { accountTag: "%s" }) {
              d1AnalyticsAdaptiveGroups(limit: 10, filter: {datetime_geq: "%s"}) {
                sum { rowsRead rowsWritten }
              }
              r2OperationsAdaptiveGroups(limit: 20, filter: {datetime_geq: "%s"}) {
                sum { requests }
                dimensions { actionType }
              }
            }
          }
        }
        """ % (account_id, start_of_day, start_of_month)

        res = requests.post(
            "https://api.cloudflare.com/client/v4/graphql",
            json={"query": q},
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp_json = res.json()
        if res.status_code == 200 and not resp_json.get("errors"):
            acct_data = resp_json["data"]["viewer"]["accounts"][0]

            # D1 Ops
            d1_data = acct_data.get("d1AnalyticsAdaptiveGroups", [])
            d1_reads = sum(d["sum"].get("rowsRead", 0) for d in d1_data) if d1_data else 0
            d1_writes = sum(d["sum"].get("rowsWritten", 0) for d in d1_data) if d1_data else 0

            d1_read_pct = (d1_reads / D1_READS_LIMIT) * 100
            d1_write_pct = (d1_writes / D1_WRITES_LIMIT) * 100

            ops_data.append({
                "label": "D1 Reads",
                "tag": "DAILY",
                "pct": round(d1_read_pct, 1),
                "pct_str": f"{d1_read_pct:.1f}%",
                "detail": f"{fmt_count(d1_reads)} / 5M",
                "level": status_level(d1_read_pct),
            })
            ops_data.append({
                "label": "D1 Writes",
                "tag": "DAILY",
                "pct": round(d1_write_pct, 1),
                "pct_str": f"{d1_write_pct:.1f}%",
                "detail": f"{fmt_count(d1_writes)} / 100K",
                "level": status_level(d1_write_pct),
            })

            # R2 Ops
            r2_data = acct_data.get("r2OperationsAdaptiveGroups", [])
            class_a_types = {"PutObject", "CopyObject", "CreateMultipartUpload", "CompleteMultipartUpload", "UploadPart", "UploadPartCopy", "ListBuckets", "ListObjects", "ListMultipartUploads"}
            class_b_types = {"GetObject", "HeadObject", "HeadBucket"}

            r2_class_a = sum(d["sum"]["requests"] for d in r2_data if d["dimensions"]["actionType"] in class_a_types)
            r2_class_b = sum(d["sum"]["requests"] for d in r2_data if d["dimensions"]["actionType"] in class_b_types)

            a_pct = (r2_class_a / R2_CLASS_A_LIMIT) * 100
            b_pct = (r2_class_b / R2_CLASS_B_LIMIT) * 100

            ops_data.append({
                "label": "R2 Class A",
                "tag": "MONTHLY",
                "pct": round(a_pct, 1),
                "pct_str": f"{a_pct:.1f}%",
                "detail": f"{fmt_count(r2_class_a)} / 1M",
                "level": status_level(a_pct),
            })
            ops_data.append({
                "label": "R2 Class B",
                "tag": "MONTHLY",
                "pct": round(b_pct, 1),
                "pct_str": f"{b_pct:.1f}%",
                "detail": f"{fmt_count(r2_class_b)} / 10M",
                "level": status_level(b_pct),
            })
    except Exception:
        pass

    return ops_data + storage_data, resets_meta


def render_cards_html(metrics):
    cards = []
    for m in metrics:
        pct = min(max(float(m["pct"]), 0.0), 100.0)
        bar_style = f"width: {pct:.1f}%;"
        if pct > 0:
            bar_style += " min-width: 3px;"
        cards.append(
            f"        <div class='card level-{m['level']}'>\n"
            f"            <div class='card-body'>\n"
            f"                <div class='card-top'>\n"
            f"                    <span class='card-label'>{html.escape(m['label'])}</span>\n"
            f"                    <span class='card-tag'>{html.escape(m['tag'])}</span>\n"
            f"                </div>\n"
            f"                <div class='card-mid'>\n"
            f"                    <span class='card-detail'>{html.escape(m['detail'])}</span>\n"
            f"                    <span class='card-pct'>{html.escape(m['pct_str'])}</span>\n"
            f"                </div>\n"
            f"            </div>\n"
            f"            <div class='bar-track'><div class='bar-fill' style='{bar_style}'></div></div>\n"
            f"        </div>"
        )
    return "\n".join(cards)


def build_reset_summary(resets_meta):
    parts = []
    if resets_meta.get("d1_reset"):
        parts.append(f"D1 resets {resets_meta['d1_reset']}")
    if resets_meta.get("r2_reset"):
        parts.append(f"R2 resets {resets_meta['r2_reset']}")
    return " · ".join(parts)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate a Cloudflare usage report.")
    parser.add_argument("-o", "--output", default="output/usage_report.html", help="Output file path (default: output/usage_report.html)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Do not print to console")
    parser.add_argument("--no-file", action="store_true", help="Do not save the report to a file")
    args = parser.parse_args()

    if not args.quiet:
        print("Fetching Cloudflare usage data...\n")

    metrics, resets_meta = get_cloudflare_usage()
    fetch_time = fmt_local_dt(datetime.now().astimezone())
    reset_summary = build_reset_summary(resets_meta)
    cols = max(len(metrics), 1) if metrics else 6
    cards_html = render_cards_html(metrics)

    payload = {
        "fetch_time": fetch_time,
        "reset_summary": reset_summary,
        "metrics": metrics,
    }

    report_text = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset='utf-8'>
    <style>
        :root {{
            --bg: #0f1218;
            --card-bg: #171c26;
            --border: #262e3d;
            --text: #f1f5f9;
            --muted: #94a3b8;
            --ok: #22c55e;
            --warn: #f59e0b;
            --crit: #ef4444;
            --accent: #f38020;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html, body {{
            width: 100%;
            height: 100%;
            background: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Consolas, monospace;
            overflow: hidden;
        }}
        .shell {{
            display: flex;
            flex-direction: column;
            width: 100%;
            height: 100%;
            padding: 6px 14px 8px 14px;
            gap: 6px;
        }}
        .header-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex: 0 0 auto;
            min-height: 20px;
        }}
        .header-left {{
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
        }}
        .title {{
            font-size: clamp(11px, 1.05vw, 15px);
            font-weight: 700;
            letter-spacing: 0.08em;
            color: var(--accent);
            white-space: nowrap;
        }}
        .resets {{
            font-size: clamp(10px, 0.9vw, 13px);
            color: var(--muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .updated {{
            font-size: clamp(10px, 0.9vw, 13px);
            color: var(--muted);
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat({cols}, minmax(0, 1fr));
            gap: 8px;
            flex: 1 1 auto;
            min-height: 0;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 7px 10px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 5px;
            min-width: 0;
            min-height: 0;
        }}
        .card-body {{
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            gap: 4px;
            flex: 1 1 auto;
            min-width: 0;
        }}
        .card-top {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 6px;
            min-width: 0;
        }}
        .card-label {{
            font-size: clamp(10px, 0.95vw, 14px);
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #cbd5e1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .card-tag {{
            font-size: clamp(9px, 0.72vw, 11px);
            color: var(--muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 48%;
        }}
        .card-mid {{
            display: flex;
            flex-direction: row-reverse;
            align-items: baseline;
            justify-content: space-between;
            gap: 6px;
            font-variant-numeric: tabular-nums;
            min-width: 0;
        }}
        .card-pct {{
            font-size: clamp(18px, min(2.0vw, 22vh), 30px);
            font-weight: 700;
            line-height: 1.05;
            white-space: nowrap;
        }}
        .card-detail {{
            font-size: clamp(10px, 0.85vw, 13px);
            color: var(--muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .level-ok .card-pct {{ color: var(--text); }}
        .level-warn .card-pct {{ color: var(--warn); }}
        .level-crit .card-pct {{ color: var(--crit); }}
        .level-warn {{ border-color: rgba(245, 158, 11, 0.45); }}
        .level-crit {{ border-color: rgba(239, 68, 68, 0.65); }}
        .bar-track {{
            width: 100%;
            height: 6px;
            background: #262e3d;
            border-radius: 3px;
            overflow: hidden;
            flex: 0 0 auto;
        }}
        .bar-fill {{
            height: 100%;
            border-radius: 3px;
            transition: width 0.4s ease;
        }}
        .level-ok .bar-fill {{ background: var(--ok); }}
        .level-warn .bar-fill {{ background: var(--warn); }}
        .level-crit .bar-fill {{ background: var(--crit); }}

        /* Portrait width (e.g. 800px rotated portrait display: 3x2 card grid) */
        @media (max-width: 1000px) {{
            .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); grid-template-rows: repeat(2, minmax(0, 1fr)); }}
        }}

        /* Ultra-compact bottom bar (e.g. 800x115 portrait 91:9 or 1280x72 landscape 91:9) */
        @media (max-height: 145px) {{
            .shell {{ padding: 4px 10px 5px 10px; gap: 4px; }}
            .header-bar {{ min-height: 14px; gap: 8px; }}
            .title {{ font-size: 11px; }}
            .resets, .updated {{ font-size: 10px; }}
            .grid {{ gap: 5px; }}
            .card {{ padding: 4px 8px; gap: 4px; border-radius: 5px; }}
            .card-body {{ flex-direction: row; align-items: baseline; justify-content: space-between; gap: 6px; }}
            .card-tag {{ display: none; }}
            .card-mid {{ flex-direction: row; justify-content: flex-end; gap: 6px; flex: 0 1 auto; }}
            .card-label {{ font-size: 11px; letter-spacing: 0.03em; }}
            .card-detail {{ font-size: 10px; }}
            .card-pct {{ font-size: 14px; line-height: 1; }}
            .bar-track {{ height: 4px; }}
        }}

        /* Square or narrow/tall panes (e.g. --video split or standalone window: 2x3 card grid) */
        @media (max-aspect-ratio: 2/1) and (min-height: 146px) {{
            .shell {{ padding: 10px 14px; gap: 10px; }}
            .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); grid-template-rows: repeat(3, minmax(0, 1fr)); gap: 10px; }}
            .title {{ font-size: clamp(13px, 2.6vw, 20px); }}
            .resets, .updated {{ font-size: clamp(11px, 1.9vw, 14px); }}
            .card {{ padding: 10px 12px; }}
            .card-label {{ font-size: clamp(11px, 2.2vw, 15px); }}
            .card-tag {{ font-size: clamp(10px, 1.7vw, 12px); }}
            .card-pct {{ font-size: clamp(20px, 4.5vw, 32px); }}
            .card-detail {{ font-size: clamp(11px, 1.9vw, 14px); }}
        }}
    </style>
</head>
<body>
    <div class='shell'>
        <div class='header-bar'>
            <div class='header-left'>
                <span class='title'>CLOUDFLARE USAGE</span>
                <span class='resets' id='cf-resets'>{html.escape(reset_summary)}</span>
            </div>
            <div class='updated' id='cf-updated'>Updated {html.escape(fetch_time)}</div>
        </div>
        <div class='grid' id='cf-grid'>
{cards_html}
        </div>
    </div>
    <script>
        function esc(s) {{
            return String(s).replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
        }}
        function renderData(d) {{
            if (!d || !Array.isArray(d.metrics) || d.metrics.length === 0) return;
            const resetsEl = document.getElementById('cf-resets');
            const updatedEl = document.getElementById('cf-updated');
            const gridEl = document.getElementById('cf-grid');
            if (resetsEl) resetsEl.textContent = d.reset_summary || '';
            if (updatedEl) updatedEl.textContent = 'Updated ' + (d.fetch_time || '');
            if (gridEl) {{
                gridEl.innerHTML = d.metrics.map(m => {{
                    const pct = Math.min(Math.max(Number(m.pct) || 0, 0), 100);
                    const minW = pct > 0 ? ' min-width: 3px;' : '';
                    return `
                        <div class='card level-${{esc(m.level || 'ok')}}'>
                            <div class='card-body'>
                                <div class='card-top'>
                                    <span class='card-label'>${{esc(m.label)}}</span>
                                    <span class='card-tag'>${{esc(m.tag)}}</span>
                                </div>
                                <div class='card-mid'>
                                    <span class='card-detail'>${{esc(m.detail)}}</span>
                                    <span class='card-pct'>${{esc(m.pct_str)}}</span>
                                </div>
                            </div>
                            <div class='bar-track'><div class='bar-fill' style='width: ${{pct.toFixed(1)}}%;${{minW}}'></div></div>
                        </div>`;
                }}).join('');
            }}
        }}
        setInterval(() => {{
            fetch('usage_data.json?t=' + Date.now(), {{ cache: 'no-store' }})
                .then(r => r.ok ? r.json() : null)
                .then(d => renderData(d))
                .catch(() => {{}});
        }}, 60000);
    </script>
</body>
</html>"""

    if not args.quiet:
        print("HTML report generated successfully.")

    if not args.no_file and args.output:
        output_file = args.output
        if output_file == "usage_report.txt":
            output_file = "output/usage_report.html"

        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        try:
            with open(output_file, "w") as f:
                f.write(report_text + "\n")
            data_file = os.path.join(out_dir if out_dir else ".", "usage_data.json")
            with open(data_file, "w") as f:
                json.dump(payload, f, indent=2)
                f.write("\n")
            if not args.quiet:
                print(f"\nReport successfully saved to: {output_file}")
        except Exception as e:
            if not args.quiet:
                print(f"\nError saving to {output_file}: {e}")


if __name__ == "__main__":
    main()
