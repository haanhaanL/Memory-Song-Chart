import csv
import os
import json
import time
import re
from base64 import b64encode
from hashlib import sha1
from datetime import datetime, timezone, timedelta
import httpx

# ================= 配置 =================
SONG_NAME = "阴天也会有烦恼吗"
CSV_FILE = "song_rank_history.csv"
BJ_TZ = timezone(timedelta(hours=8))

# ================= 签名算法 =================
PART_1_INDEXES = [23, 14, 6, 36, 16, 7, 19]
PART_2_INDEXES = [16, 1, 32, 12, 19, 27, 8, 5]
SCRAMBLE_VALUES = [89, 39, 179, 150, 218, 82, 58, 252, 177, 52, 186, 123, 120, 64, 242, 133, 143, 161, 121, 179]

def zzc_sign(payload: str | bytes) -> str:
    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
    hash_hex = sha1(payload_bytes).hexdigest().upper()
    
    part1 = "".join(hash_hex[i] for i in PART_1_INDEXES)
    part2 = "".join(hash_hex[i] for i in PART_2_INDEXES)
    
    part3 = bytearray(20)
    for i, v in enumerate(SCRAMBLE_VALUES):
        value = v ^ int(hash_hex[i * 2: i * 2 + 2], 16)
        part3[i] = value
    b64_part = re.sub(rb"[\\/+=]", b"", b64encode(part3)).decode("utf-8")
    return f"zzc{part1}{b64_part}{part2}".lower()

# ================= 核心抓取逻辑 =================
def fetch_current_data():
    """直接调用接口获取榜单数据"""
    print("正在请求接口...")
    
    # 1. 构造 payload
    payload_dict = {
        "comm": {
            "g_tk": 5381, "uin": "", "format": "json",
            "inCharset": "utf-8", "outCharset": "utf-8",
            "notice": 0, "platform": "h5", "needNewCode": 1
        },
        "req_0": {
            "module": "music.actCenter.PopularSong2026Svr",
            "method": "GetRankList",
            "param": {"issue": 1, "type": 4, "beginPos": 0, "pageSize": 300}
        }
    }
    
    # 必须转成没有空格的紧凑字符串
    payload_str = json.dumps(payload_dict, separators=(',', ':'))
    
    # 2. 生成 sign
    sign = zzc_sign(payload_str)
    
    # 3. 发送请求
    url = "https://u6.y.qq.com/cgi-bin/musics.fcg"
    params = {
        "_webcgikey": "GetRankList",
        "_": int(time.time() * 1000),
        "sign": sign
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Referer": "https://y.qq.com/",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # 发送 POST 请求
    resp = httpx.post(url, params=params, data=payload_str, headers=headers, timeout=10)
    resp.raise_for_status()
    
    # 4. 解析数据
    data = resp.json()
    
    # 检查接口返回是否正常
    if "req_0" not in data or data["req_0"].get("code") != 0:
        raise Exception(f"接口返回异常: {data}")
        
    song_list = data["req_0"]["data"]["songList"]
    
    # 遍历前 300 首歌，找到目标
    for item in song_list:
        song_info = item.get("songInfo", {})
        if SONG_NAME in song_info.get("name", ""):
            rank = item.get("rank")
            votes = item.get("score")  # 已确认字段为 score
            if rank is not None and votes is not None:
                print(f"找到歌曲！排名: {rank}, 票数: {votes}")
                return int(rank), int(votes)
            else:
                print(f"找到歌曲但字段缺失，完整数据: {item}")
            
    raise Exception(f"在榜单中未找到《{SONG_NAME}》")

# ================= 本地历史对比逻辑 =================
def get_history_records():
    if not os.path.exists(CSV_FILE):
        return []
    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader)

def save_record(row_data):
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
        
        now = datetime.now(BJ_TZ)
        today_str = now.strftime('%Y-%m-%d')
        print(f"记录时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        print(f"获取失败: {e}")
        return

    records = get_history_records()
    
    last_rank_change = 0
    last_votes_change = 0
    daily_rank_change = 0
    daily_votes_change = 0

    if records:
        # 1. 计算与上一次运行的变化
        last_record = records[-1]
        last_rank = int(last_record['排名'])
        last_votes = int(last_record['总票数'])
        
        last_rank_change = last_rank - current_rank
        last_votes_change = current_votes - last_votes
        
        print(f"较上次: 排名变化 {last_rank_change:+d}, 票数涨幅 {last_votes_change:+d}")

        # 2. 计算当日内的变化
        today_records = [r for r in records if r['时间'].startswith(today_str)]
        
        if today_records:
            first_today_record = today_records[0]
            first_today_rank = int(first_today_record['排名'])
            first_today_votes = int(first_today_record['总票数'])
            
            daily_rank_change = first_today_rank - current_rank
            daily_votes_change = current_votes - first_today_votes
            print(f"较今日首测: 排名变化 {daily_rank_change:+d}, 票数涨幅 {daily_votes_change:+d}")
        else:
            print("今日首测，当日涨幅记为 0。")
    else:
        print("这是历史第一条记录，所有变化为 0。")

    # 组装并保存数据
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
