#!/usr/bin/env python3
"""
Portrait 部署验证脚本

模拟完整的数据清洗流程，用于验证部署是否成功：
1. 同步通话记录
2. 计算用户画像快照
3. 计算场景汇总
4. 同步任务名称

使用方式:
    python verify_deployment.py [--date 2025-11-05] [--api-url http://localhost:8000]
"""

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


def make_request(url: str, method: str = "GET", data: dict = None) -> dict:
    """发送 HTTP 请求"""
    headers = {"Content-Type": "application/json"}
    
    if data:
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers=headers, method=method)
    else:
        req = Request(url, headers=headers, method=method)
    
    try:
        with urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except URLError as e:
        return {"error": f"连接失败: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def print_step(step: int, title: str):
    """打印步骤标题"""
    print(f"\n{'='*60}")
    print(f"  步骤 {step}: {title}")
    print('='*60)


def print_result(success: bool, message: str):
    """打印结果"""
    status = "✅ 成功" if success else "❌ 失败"
    print(f"\n  {status}: {message}")


def check_health(api_url: str) -> bool:
    """检查 API 健康状态"""
    print_step(0, "检查 API 服务")
    
    result = make_request(f"{api_url}/health")
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    print_result(True, f"API 服务正常 - {result.get('status', 'ok')}")
    return True


def check_system_status(api_url: str) -> dict:
    """获取系统状态"""
    print_step(1, "获取系统状态")
    
    result = make_request(f"{api_url}/api/v1/admin/status")
    if "error" in result:
        print_result(False, result["error"])
        return {}
    
    data = result.get("data", {})
    print(f"""
  系统状态: {data.get('status', 'unknown')}
  数据库:   {data.get('database', 'unknown')}
  源数据库: {data.get('source_db', 'unknown')}
  已计算周期数: {data.get('total_periods', 0)}
  画像快照总数: {data.get('total_snapshots', 0)}
  增强记录总数: {data.get('total_enriched_records', 0)}
""")
    
    print_result(True, "系统状态获取成功")
    return data


def sync_call_records(api_url: str, target_date: str) -> bool:
    """同步通话记录"""
    print_step(2, f"同步通话记录 ({target_date})")
    
    result = make_request(
        f"{api_url}/api/v1/admin/sync",
        method="POST",
        data={"date": target_date}
    )
    
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    data = result.get("data", {})
    status = data.get("status", "unknown")
    synced = data.get("synced", 0)
    message = data.get("message", "")
    
    if status == "skipped" and message == "source_db_unavailable":
        print_result(False, "源数据库不可用 - 请检查 MYSQL_HOST 配置")
        return False
    
    print_result(True, f"同步 {synced} 条记录")
    return True


def compute_snapshot(api_url: str, period_type: str, period_key: str) -> bool:
    """计算用户画像快照"""
    print_step(3, f"计算用户画像快照 ({period_type}/{period_key})")
    
    result = make_request(
        f"{api_url}/api/v1/admin/compute",
        method="POST",
        data={"period_type": period_type, "period_key": period_key, "force": True}
    )
    
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    data = result.get("data", {})
    status = data.get("status", "unknown")
    users = data.get("users", 0)
    records = data.get("records", 0)
    
    if status != "success":
        print_result(False, data.get("message", "计算失败"))
        return False
    
    print_result(True, f"计算 {users} 个用户, {records} 条记录")
    return True


def compute_task_summary(api_url: str, period_type: str, period_key: str) -> bool:
    """计算场景汇总"""
    print_step(4, f"计算场景汇总 ({period_type}/{period_key})")
    
    result = make_request(
        f"{api_url}/api/v1/admin/compute-task-summary",
        method="POST",
        data={"period_type": period_type, "period_key": period_key, "force": True}
    )
    
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    data = result.get("data", {})
    status = data.get("status", "unknown")
    tasks = data.get("tasks", 0)
    
    if status != "success":
        print_result(False, data.get("message", "计算失败"))
        return False
    
    print_result(True, f"计算 {tasks} 个场景/任务")
    return True


def sync_task_names(api_url: str) -> bool:
    """同步任务名称"""
    print_step(5, "同步任务名称")
    
    result = make_request(
        f"{api_url}/api/v1/admin/sync-task-names",
        method="POST"
    )
    
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    data = result.get("data", {})
    status = data.get("status", "unknown")
    tasks = data.get("tasks", 0)
    updated = data.get("updated", 0)
    
    if status == "skipped":
        print_result(False, "源数据库不可用，无法同步任务名称")
        return False
    
    print_result(True, f"同步 {tasks} 个任务, 更新 {updated} 条记录")
    return True


def verify_data(api_url: str, period_type: str, period_key: str) -> bool:
    """验证数据"""
    print_step(6, "验证数据")
    
    # 检查周期列表
    result = make_request(f"{api_url}/api/v1/task/periods?period_type={period_type}")
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    periods = result.get("data", [])
    if not periods:
        print_result(False, "没有找到任何周期数据")
        return False
    
    print(f"  找到 {len(periods)} 个周期")
    
    # 检查任务列表
    result = make_request(
        f"{api_url}/api/v1/task?limit=5&period_type={period_type}&period_key={period_key}"
    )
    if "error" in result:
        print_result(False, result["error"])
        return False
    
    tasks = result.get("data", [])
    if not tasks:
        print_result(False, "没有找到任何任务数据")
        return False
    
    print(f"  找到 {len(tasks)} 个任务/场景")
    print(f"\n  任务列表 (前5个):")
    for task in tasks[:5]:
        name = task.get("task_name") or "(未命名)"
        count = task.get("customer_count", 0)
        print(f"    - {name}: {count} 客户")
    
    print_result(True, "数据验证通过")
    return True


def get_week_key(target_date: date) -> str:
    """获取周期编号"""
    iso_calendar = target_date.isocalendar()
    return f"{iso_calendar[0]}-W{iso_calendar[1]:02d}"


def main():
    parser = argparse.ArgumentParser(description="Portrait 部署验证脚本")
    parser.add_argument(
        "--date", 
        default=(datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
        help="同步日期 (默认: 昨天)"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API 地址 (默认: http://localhost:8000)"
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="跳过数据同步步骤"
    )
    args = parser.parse_args()
    
    api_url = args.api_url.rstrip("/")
    target_date = args.date
    period_key = get_week_key(date.fromisoformat(target_date))
    
    print("\n" + "="*60)
    print("  Portrait 部署验证")
    print("="*60)
    print(f"  API 地址: {api_url}")
    print(f"  同步日期: {target_date}")
    print(f"  周期编号: {period_key}")
    print("="*60)
    
    # 执行验证流程
    success = True
    
    if not check_health(api_url):
        print("\n❌ 验证失败: API 服务不可用")
        sys.exit(1)
    
    check_system_status(api_url)
    
    if not args.skip_sync:
        if not sync_call_records(api_url, target_date):
            success = False
        else:
            if not compute_snapshot(api_url, "week", period_key):
                success = False
            else:
                if not compute_task_summary(api_url, "week", period_key):
                    success = False
                else:
                    sync_task_names(api_url)
    
    if not verify_data(api_url, "week", period_key):
        success = False
    
    # 最终结果
    print("\n" + "="*60)
    if success:
        print("  ✅ 部署验证通过!")
    else:
        print("  ⚠️  部署验证完成，但有错误")
    print("="*60 + "\n")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
