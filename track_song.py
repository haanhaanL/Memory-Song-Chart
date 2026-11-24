import csv
import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# 配置
SONG_NAME = "阴天也会有烦恼吗"
CSV_FILE = "song_rank_history.csv"
TARGET_URL = "https://i2.y.qq.com/n3/other/pages/fav_song_2026/index.html"

def fetch_current_data():
    """使用 Playwright 获取当前排名和票数"""
    with sync_playwright() as p:
        # 启动无头浏览器，加上防自动化检测的参数
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        # 使用移动端 UA 和视口，更容易拿到完整页面
        context = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="zh-CN"
        )
        page = context.new_page()
        
        # 拦截 .apk 下载请求，防止重定向
        page.route("**/*.apk", lambda route: route.abort())

        print("正在加载页面...")
        # 使用 domcontentloaded 加快初始加载
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        print("滚动加载完整榜单(300名)...")
        # 目标歌曲排在第 148 名，需要循环滚动到底部触发懒加载
        for _ in range(8):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

        print("尝试查找歌曲信息...")
        try:
            # 等待目标歌曲出现在 DOM 中
            page.wait_for_selector(f"text={SONG_NAME}", timeout=15000)
        except Exception as e:
            print("未找到歌曲元素，保存截图...")
            page.screenshot(path="debug.png", full_page=True)
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            browser.close()
            raise Exception("页面中找不到目标歌曲，可能被拦截或页面结构改变")

        content = page.content()
        browser.close()

        # 提取纯文本行进行解析
        text = re.sub(r'<[^>]+>', '\n', content)
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        rank = None
        votes = None

        for i, line in enumerate(lines):
            if SONG_NAME in line:
                # 向上找排名
                for j in range(max(0, i-5), i):
                    if lines[j].isdigit():
                        rank = int(lines[j])
                        break
                # 向下找票数
                for j in range(i+1, min(len(lines), i+10)):
                    if "邀请投票" in lines[j] or "人已邀请" in lines[j]:
                        nums = re.findall(r'\d+', lines[j])
                        if nums:
                            votes = int(nums[0])
                            break
                    elif lines[j].isdigit():
                        votes = int(lines[j])
                        break
                
                if rank is not None and votes is not None:
                    break

        if rank is None or votes is None:
            raise Exception(f"解析失败，未能提取《{SONG_NAME}》的排名和票数")

        return rank, votes

def get_history_records():
    """从 CSV 读取历史记录"""
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_record(row_data):
    """保存记录到 CSV"""
    file_exists = os.path.exists(CSV_FILE)
    fieldnames = ['时间', '排名', '总票数', '较上次排名变化', '较上次票数涨幅', '当日排名变化', '当日票数涨幅']
    
    with open(CSV_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_data)

def main():
    print(f"开始获取《{SONG_NAME}》的数据...")
    
    try:
        current_rank, current_votes = fetch_current_data()
        # 强制使用北京时间，避免 GitHub Actions 在 UTC 时区下日期出错
        from datetime import timezone, timedelta
        bj_time = datetime.now(timezone(timedelta(hours=8)))
        today_str = bj_time.strftime('%Y-%m-%d')
        print(f"当前排名: {current_rank}, 当前票数: {current_votes}, 时间: {bj_time.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"获取失败: {e}")
        return

    records = get_history_records()
    
    # 初始化变化值
    last_rank_change = 0
    last_votes_change = 0
    daily_rank_change = 0
    daily_votes_change = 0

    if records:
        # 1. 计算与上一次运行的变化（较上次）
        last_record = records[-1]
        last_rank = int(last_record['排名'])
        last_votes = int(last_record['总票数'])
        
        last_rank_change = last_rank - current_rank
        last_votes_change = current_votes - last_votes
        
        print(f"相比上次: 排名变化 {last_rank_change:+d}, 票数涨幅 {last_votes_change:+d}")

        # 2. 计算当日内的变化
        today_records = [r for r in records if r['时间'].startswith(today_str)]
        
        if today_records:
            # 拿今天的第一条记录和当前对比
            first_today_record = today_records[0]
            first_today_rank = int(first_today_record['排名'])
            first_today_votes = int(first_today_record['总票数'])
            
            daily_rank_change = first_today_rank - current_rank
            daily_votes_change = current_votes - first_today_votes
            print(f"相比今日首测: 排名变化 {daily_rank_change:+d}, 票数涨幅 {daily_votes_change:+d}")
        else:
            print("今日首测，当日涨幅记为 0。")
    else:
        print("这是历史第一条记录，所有变化为 0。")

    # 组装要保存的数据
    row_data = {
        '时间': bj_time.strftime('%Y-%m-%d %H:%M:%S'),
        '排名': current_rank,
        '总票数': current_votes,
        '较上次排名变化': last_rank_change,
        '较上次票数涨幅': last_votes_change,
        '当日排名变化': daily_rank_change,
        '当日票数涨幅': daily_votes_change
    }

    save_record(row_data)
    print(f"数据已保存到 {CSV_FILE}")

if __name__ == "__main__":
    main()
