import csv
import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# 配置
SONG_NAME = "阴天也会有烦恼吗"
CSV_FILE = "song_rank_history.csv"
TARGET_URL = "https://i2.y.qq.com/n3/other/pages/fav_song_2026/index.html?ADTAG=yy_gnyy_26jygq&_button=1&_fontscale=1&_hidehd=1&_miniplayer=1&ablumId=004PpJGW1dmLu3&actID=Z108qLI&channelId=10036163&hosteuin=oKoA7K-q7e6s7z%2A%2A&issue=1&openinqqmusic=1&shareCode=NzJU1w6w+IGmCY9hTAozVr3lpfA%3D&songId=742708761&songName=%E9%98%B4%E5%A4%A9%E4%B9%9F%E4%BC%9A%E6%9C%89%E7%83%A6%E6%81%BC%E5%90%97&taskID=Z2itbho%40742708761&type=4"

def fetch_current_data():
    """使用 Playwright 获取当前排名和票数"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("正在加载页面...")
        page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_selector(f"text={SONG_NAME}", timeout=30000)
        
        content = page.content()
        browser.close()
        
        text = re.sub(r'<[^>]+>', '\n', content)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        rank = None
        votes = None
        
        for i, line in enumerate(lines):
            if SONG_NAME in line:
                for j in range(max(0, i-5), i):
                    if lines[j].isdigit():
                        rank = int(lines[j])
                        break
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
            raise Exception(f"无法解析《{SONG_NAME}》的数据，页面结构可能已变化")
            
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
    # 定义列名，改名为“较上次”
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
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        print(f"当前排名: {current_rank}, 当前票数: {current_votes}, 时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
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
        '时间': now.strftime('%Y-%m-%d %H:%M:%S'),
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
