#!/usr/bin/env python3
import subprocess
import re
from datetime import datetime, timezone

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def format_iso_date(iso_str):
    """Converts UTC ISO string to Local Time format"""
    try:
        # Parse UTC time
        dt = datetime.strptime(iso_str.strip(), "%Y-%m-%dT%H:%M:%SZ")
        dt = dt.replace(tzinfo=timezone.utc)
        
        # Convert to local time
        dt_local = dt.astimezone()
        tz_name = dt_local.tzname()
        
        hour_12 = dt_local.hour % 12
        if hour_12 == 0:
            hour_12 = 12
        am_pm = "am" if dt_local.hour < 12 else "pm"
        return f"{dt_local.strftime('%b')} {dt_local.day}, {hour_12}:{dt_local.minute:02d}{am_pm}"
    except ValueError:
        return iso_str

def parse_claude_usage(text):
    data = []
    for line in text.split('\n'):
        line = line.strip()
        if "Current session:" in line:
            match = re.search(r'(\d+)%\s+used\s+·\s+resets\s+(.*)', line)
            if match:
                used = int(match.group(1))
                resets = re.sub(r'\s*\([^)]+\)', '', match.group(2)).strip()
                data.append({
                    "System": "Claude",
                    "Category": "Session",
                    "Used (%)": f"{used}%",
                    "Resets": resets
                })
        elif "Current week" in line:
            match = re.search(r'(\d+)%\s+used\s+·\s+resets\s+(.*)', line)
            if match:
                used = int(match.group(1))
                resets = re.sub(r'\s*\([^)]+\)', '', match.group(2)).strip()
                data.append({
                    "System": "Claude",
                    "Category": "Weekly (All Models)",
                    "Used (%)": f"{used}%",
                    "Resets": resets
                })
    return data

def parse_agy_usage(text):
    data = []
    for line in text.split('\n'):
        if "Limit Remaining" in line:
            parts = re.split(r'\t+', line.strip())
            if len(parts) >= 4:
                category = f"{parts[0]} - {parts[1]}"
                remaining_str = parts[2].replace('%', '')
                try:
                    remaining = int(remaining_str)
                    used = 100 - remaining
                except ValueError:
                    remaining = parts[2]
                    used = "N/A"
                
                resets = format_iso_date(parts[3])
                
                if "Gemini Models" in category:
                    data.append({
                        "System": "Gemini",
                        "Category": category.replace("Limit Remaining", "").strip(),
                        "Used (%)": f"{used}%" if isinstance(used, int) else used,
                        "Resets": resets
                    })
    return data

def get_cloudflare_usage():
    storage_data = []
    ops_data = []
    env_vars = {}
    try:
        with open("/home/backtest01/reporting/.env") as f:
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
    D1_CAPACITY_KB = 5 * 1024 * 1024  # 5 GB
    R2_CAPACITY_MB = 10 * 1024        # 10 GB
    D1_READS_LIMIT = 5_000_000
    D1_WRITES_LIMIT = 100_000
    R2_CLASS_A_LIMIT = 1_000_000
    R2_CLASS_B_LIMIT = 10_000_000

    if not account_id or not api_token:
        return ops_data + storage_data

    import requests

    # Fetch D1 Size using old token that has D1 permissions
    if d1_id:
        old_token = api_token
        try:
            with open("/home/backtest01/luna-strategy-Trading/Trading/.env") as f:
                for line in f:
                    if line.startswith("CLOUDFLARE_API_TOKEN="):
                        old_token = line.strip().split("=")[1]
        except Exception:
            pass
            
        headers = {"Authorization": f"Bearer {old_token}", "Content-Type": "application/json"}
        try:
            res = requests.get(f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{d1_id}", headers=headers)
            if res.status_code == 200:
                d1_size = res.json()["result"]["file_size"]
                d1_name = res.json()["result"]["name"]
                size_kb = d1_size / 1024
                used_pct = (size_kb / D1_CAPACITY_KB) * 100
                storage_data.append({
                    "System": "Cloudflare",
                    "Category": f"D1 Storage ({d1_name})",
                    "Used (%)": f"{used_pct:.1f}%",
                    "Resets": "N/A"
                })
        except Exception:
            pass

    # Fetch R2 Size via boto3 using the venv python
    r2_script = """
import boto3, json
s3 = boto3.client('s3', endpoint_url='https://{acc_id}.r2.cloudflarestorage.com',
                  aws_access_key_id='{ak}', aws_secret_access_key='{sk}', region_name='auto')
res = s3.list_objects_v2(Bucket='{bucket}')
print(sum(obj['Size'] for obj in res.get('Contents', [])))
""".format(
        acc_id=account_id,
        ak=env_vars.get("R2_ACCESS_KEY_ID"),
        sk=env_vars.get("R2_SECRET_ACCESS_KEY"),
        bucket=bucket
    )

    try:
        venv_python = "/home/backtest01/luna-strategy-Trading/Trading/.venv/bin/python"
        r2_out = subprocess.run([venv_python, "-c", r2_script], capture_output=True, text=True).stdout.strip()
        if r2_out and r2_out.isdigit():
            size_mb = int(r2_out) / (1024 * 1024)
            used_pct = (size_mb / R2_CAPACITY_MB) * 100
            storage_data.append({
                "System": "Cloudflare",
                "Category": f"R2 Storage ({bucket})",
                "Used (%)": f"{used_pct:.1f}%",
                "Resets": "N/A"
            })
    except Exception:
        pass

    # Fetch Operations via GraphQL
    try:
        from datetime import timezone, datetime, timedelta
        now_utc = datetime.now(timezone.utc)
        start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        start_of_month = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Calculate exact reset times in local timezone
        next_midnight_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        next_midnight_local = next_midnight_utc.astimezone()
        
        if now_utc.month == 12:
            next_month_utc = now_utc.replace(year=now_utc.year+1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month_utc = now_utc.replace(month=now_utc.month+1, day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month_local = next_month_utc.astimezone()

        def fmt_dt(dt):
            hour_12 = dt.hour % 12
            if hour_12 == 0:
                hour_12 = 12
            am_pm = "am" if dt.hour < 12 else "pm"
            return f"{dt.strftime('%b')} {dt.day}, {hour_12}:{dt.minute:02d}{am_pm}"

        d1_reset = fmt_dt(next_midnight_local)
        r2_reset = fmt_dt(next_month_local)

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

        res = requests.post("https://api.cloudflare.com/client/v4/graphql", json={"query": q}, headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"})
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
                "System": "Cloudflare",
                "Category": "D1 Daily Rows Read",
                "Used (%)": f"{d1_read_pct:.1f}%",
                "Resets": d1_reset
            })
            ops_data.append({
                "System": "Cloudflare",
                "Category": "D1 Daily Rows Written",
                "Used (%)": f"{d1_write_pct:.1f}%",
                "Resets": d1_reset
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
                "System": "Cloudflare",
                "Category": "R2 Monthly Ops (Class A)",
                "Used (%)": f"{a_pct:.1f}%",
                "Resets": r2_reset
            })
            ops_data.append({
                "System": "Cloudflare",
                "Category": "R2 Monthly Ops (Class B)",
                "Used (%)": f"{b_pct:.1f}%",
                "Resets": r2_reset
            })
    except Exception as e:
        pass

    return ops_data + storage_data

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate a unified usage report.")
    parser.add_argument("-o", "--output", default="usage_report.txt", help="Output file path (default: usage_report.txt)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Do not print to console")
    parser.add_argument("--no-file", action="store_true", help="Do not save the report to a file")
    args = parser.parse_args()

    if not args.quiet:
        print("Fetching usage data (this takes a few seconds)...\n")

    claude_out = run_command('claude -p "/usage"')
    agy_out = run_command('agy -p "/usage"')

    all_data = parse_claude_usage(claude_out) + parse_agy_usage(agy_out) + get_cloudflare_usage()

    from datetime import datetime
    now = datetime.now().astimezone()
    hour_12 = now.hour % 12
    if hour_12 == 0:
        hour_12 = 12
    am_pm = "am" if now.hour < 12 else "pm"
    fetch_time = f"{now.strftime('%b')} {now.day}, {hour_12}:{now.minute:02d}{am_pm}"

    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "    <meta charset='utf-8'>",
        "    <style>",
        "        body { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; padding: min(1.2vw, 2.5vh) min(2.5vw, 5vh); margin: 0; overflow: hidden; }",
        "        table { width: 100%; border-collapse: collapse; font-size: min(3.2vw, 5.5vh); }",
        "        th, td { padding: min(0.7vw, 1.2vh) min(1.5vw, 2.5vh); text-align: left; border-bottom: 1px solid #333333; }",
        "        th { color: #4CAF50; font-weight: 600; text-transform: uppercase; font-size: min(2.7vw, 4.5vh); letter-spacing: 0.1vw; }",
        "        .header { font-size: min(2.5vw, 4.2vh); color: #aaaaaa; margin-bottom: 0; text-align: left; font-weight: 500; }",
        "        .title-bar { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid #4CAF50; padding-bottom: min(0.7vw, 1.2vh); margin-bottom: min(0.7vw, 1.2vh); }",
        "        h2 { margin: 0; color: #ffffff; font-size: min(4vw, 6.5vh); font-weight: 400; }",
        "    </style>",
        "</head>",
        "<body>",
        "    <div class='title-bar'>",
        "        <h2>UNIFIED USAGE REPORT</h2>",
        f"       <div class='header'>Data fetched at: {fetch_time}</div>",
        "    </div>",
        "    <table>",
        "        <tr><th>System / Category</th><th>Used</th><th>Reset Time</th></tr>"
    ]
    
    for row in all_data:
        html_lines.append(f"        <tr><td>{row['System']} / {row['Category']}</td><td>{row['Used (%)']}</td><td>{row['Resets']}</td></tr>")
        
    html_lines.append("    </table>")
    html_lines.append("</body>")
    html_lines.append("</html>")
    
    report_text = "\n".join(html_lines)

    if not args.quiet:
        print("HTML report generated successfully.")

    if not args.no_file and args.output:
        # Auto-switch the extension to .html if the user didn't explicitly provide a different one
        output_file = args.output
        if output_file == "usage_report.txt":
            output_file = "usage_report.html"
            
        try:
            with open(output_file, "w") as f:
                f.write(report_text + "\n")
            if not args.quiet:
                print(f"\nReport successfully saved to: {output_file}")
        except Exception as e:
            if not args.quiet:
                print(f"\nError saving to {output_file}: {e}")

if __name__ == "__main__":
    main()
