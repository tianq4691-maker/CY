"""
陈毅历史行迹图 - 地理编码预处理脚本
- 内嵌144个地点坐标
- 国内坐标自动从 GCJ02 转为 WGS84（供 Leaflet/OSM 使用）
- 国际坐标原生 WGS84
- 可选调用高德 REST API 补充缺失坐标（当前已100%匹配，无需调用）
"""

import pandas as pd
import json
import math
import time
import urllib.request
import urllib.parse
from datetime import datetime

EXCEL_FILE = "陈毅生平事件摘要.xlsx"
OUTPUT_FILE = "geodata.json"
AMAP_KEY = "e286cc18dce1d9ca32be40a06a4b40ad"  # 用于 geocoding REST 回退

# ── 阶段定义 ──────────────────────────────────────────────────────────────────
PHASES = [
    {"id": 1, "name": "早年求学", "start": "1901-08-26", "end": "1923-11-01", "color": "#4A90D9"},
    {"id": 2, "name": "武装革命", "start": "1923-11-02", "end": "1937-09-29", "color": "#E84C3D"},
    {"id": 3, "name": "新四军抗战", "start": "1937-09-30", "end": "1945-10-25", "color": "#F39C12"},
    {"id": 4, "name": "解放战争",   "start": "1945-10-26", "end": "1949-05-27", "color": "#8E44AD"},
    {"id": 5, "name": "外交建设",   "start": "1949-05-28", "end": "1972-01-10", "color": "#27AE60"},
]

# ── GCJ02 → WGS84 转换 ───────────────────────────────────────────────────────
def _out_of_china(lng, lat):
    return not (73.66 < lng < 135.05 and 3.86 < lat < 53.55)

def _transform_lat(x, y):
    ret = -100.0 + 2.0*x + 3.0*y + 0.2*y*y + 0.1*x*y + 0.2*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    ret += (20.0*math.sin(y*math.pi) + 40.0*math.sin(y/3.0*math.pi)) * 2.0/3.0
    ret += (160.0*math.sin(y/12.0*math.pi) + 320*math.sin(y*math.pi/30.0)) * 2.0/3.0
    return ret

def _transform_lng(x, y):
    ret = 300.0 + x + 2.0*y + 0.1*x*x + 0.1*x*y + 0.1*math.sqrt(abs(x))
    ret += (20.0*math.sin(6.0*x*math.pi) + 20.0*math.sin(2.0*x*math.pi)) * 2.0/3.0
    ret += (20.0*math.sin(x*math.pi) + 40.0*math.sin(x/3.0*math.pi)) * 2.0/3.0
    ret += (150.0*math.sin(x/12.0*math.pi) + 300.0*math.sin(x/30.0*math.pi)) * 2.0/3.0
    return ret

def gcj02_to_wgs84(lng, lat):
    """高德GCJ02 → WGS84"""
    if _out_of_china(lng, lat):
        return lng, lat
    a = 6378245.0
    ee = 0.00669342162296594323
    dlat = _transform_lat(lng - 105.0, lat - 35.0)
    dlng = _transform_lng(lng - 105.0, lat - 35.0)
    radlat = lat / 180.0 * math.pi
    magic = math.sin(radlat)
    magic = 1 - ee*magic*magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((a * (1-ee)) / (magic * sqrtmagic) * math.pi)
    dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat) * math.pi)
    mglat = lat + dlat
    mglng = lng + dlng
    return lng * 2 - mglng, lat * 2 - mglat

# ── 坐标原始表（国内GCJ02 / 国际WGS84）──────────────────────────────────────
LOCATION_COORDS_RAW = {
    # 国内主要城市
    "北京市":(116.4074,39.9042),"上海市":(121.4737,31.2304),"成都市":(104.0668,30.5728),
    "重庆市":(106.5516,29.5630),"武汉市":(114.3054,30.5931),"南京市":(118.7969,32.0603),
    "南昌市":(115.8922,28.6764),"广州市":(113.2644,23.1291),"杭州市":(120.1551,30.2741),
    "西安市":(108.9398,34.3416),"昆明市":(102.8329,24.8800),"沈阳市":(123.4315,41.8057),
    "贵阳市":(106.6302,26.6470),"青岛市":(120.3826,36.0662),"石家庄市":(114.5149,38.0428),
    "洛阳市":(112.4535,34.6197),"拉萨市":(91.1409,29.6453),"三亚市":(109.5121,18.2528),
    "大理市":(100.2257,25.5894),"商丘市":(115.6500,34.4167),"和田市":(79.9253,37.1140),
    "景洪市":(100.7977,22.0035),"延安市":(109.4896,36.5853),"临沂市":(118.3564,35.1042),
    "徐州市":(117.2841,34.2618),"丹阳市":(119.5812,31.9912),"东台市":(120.3145,32.8536),
    "盐城市":(120.1615,33.3473),"宿迁市":(118.2751,33.9445),"镇江市":(119.4521,32.2041),
    "海安市":(120.4587,32.5460),"龙岩市":(117.0177,25.0758),"吉安市":(114.9868,27.1116),
    "南雄市":(114.3124,25.1179),"瑞金市":(116.0272,25.8852),"永城市":(116.4453,33.9295),
    "邹城市":(116.9731,35.4060),
    # 区县
    "姜堰区":(120.1528,32.5087),"金坛区":(119.5779,31.7469),"贾汪区":(117.4518,34.4443),
    "淄川区":(117.9666,36.6430),"北戴河区":(119.4853,39.8343),"合川区":(106.2765,29.9719),
    "上杭县":(116.4233,25.0492),"古田县":(118.7446,26.5772),"宁冈县":(114.1510,26.7230),
    "兴国县":(115.3633,26.3374),"宁都县":(116.0136,26.4726),"永丰县":(115.4428,27.1787),
    "大余县":(114.3597,25.3961),"泰和县":(114.9068,26.8010),"宜黄县":(116.2366,27.5543),
    "永兴县":(113.1107,26.1310),"萧县":(116.9448,34.1889),"沂水县":(118.6348,35.7882),
    "横县":(109.2632,22.6807),
    # 乡镇村
    "砻市镇":(114.1040,26.6670),"松源镇":(115.9167,24.7500),"梅岭":(114.3028,25.2356),
    "泾县云岭":(118.2853,30.6953),"岩寺镇":(118.1625,29.9074),"竹箦镇":(119.4073,31.6139),
    "黄桥镇":(120.1473,32.2921),"曲塘镇":(120.3597,32.6056),"曹甸镇":(119.6925,33.0822),
    "戴楼镇":(119.4361,33.7772),"半城镇":(118.2750,33.5694),"临淮关镇":(117.6097,32.8942),
    "城南庄镇":(113.9028,38.8472),"白马市":(105.6171,22.0323),"黄花塘镇":(118.7792,32.9439),
    "黄花塘村":(118.7792,32.9439),"宽田乡":(115.4461,25.9750),"黄麟乡":(116.0569,26.1306),
    "油山镇":(114.1750,25.4833),"德胜乡":(116.3831,39.9583),"正沟湾村":(105.0147,30.2742),
    "上坪村":(116.4961,25.0942),"土塘村":(116.4722,24.8333),"水西村":(119.0217,31.6139),
    "瑶岗村":(117.5833,31.8833),"孙家圩":(117.4361,32.9028),"杨家沟":(110.2139,37.8417),
    "沙河铺":(104.1305,30.6785),"西柏坡":(113.9531,38.2964),
    # 地理特征
    "崇明岛":(121.6974,31.6235),"舟山市":(122.2067,30.0173),"庐山":(115.9780,29.5510),
    "石河子":(86.0412,44.3056),"珍宝岛":(133.7164,46.4880),"孟良崮":(117.9400,35.4900),
    # 省级
    "江苏省":(118.7674,32.0415),"江西省":(115.8925,28.6764),"福建省":(119.2965,26.0745),
    "台湾":(120.9605,23.6978),"朝鲜":(127.5101,40.3399),
    # 国际城市（WGS84）
    "巴黎":(2.3522,48.8566),"仰光":(96.1561,16.8661),"仰光市":(96.1561,16.8661),
    "金边":(104.9282,11.5564),"金边市":(104.9282,11.5564),"开罗市":(31.2357,30.0444),
    "内罗毕":(36.8219,-1.2921),"内罗毕市":(36.8219,-1.2921),"喀布尔":(69.2075,34.5553),
    "喀布尔市":(69.2075,34.5553),"莫斯科市":(37.6173,55.7558),"达卡":(90.4125,23.8103),
    "卡拉奇":(67.0099,24.8607),"卡拉奇市":(67.0099,24.8607),"伊斯兰堡":(73.0479,33.7294),
    "拉合尔":(74.3436,31.5497),"拉瓦尔品第":(73.0551,33.5651),"雅加达":(106.8456,-6.2088),
    "雅加达市":(106.8456,-6.2088),"万隆市":(107.6191,-6.9175),"河内市":(105.8342,21.0278),
    "平壤市":(125.7625,39.0392),"元山市":(127.4353,39.1547),"科伦坡市":(79.8612,6.9271),
    "日内瓦":(6.1432,46.2044),"柏林市":(13.4050,52.5200),"德里市":(77.2090,28.6139),
    "加德满都市":(85.3240,27.7172),"突尼斯市":(10.1815,36.8065),
    "阿尔及尔市":(3.0588,36.7538),"阿克拉市":(-0.1870,5.5560),"巴马科市":(-8.0026,12.6392),
    "科纳克里市":(-13.5784,9.5370),"摩加迪沙市":(45.3182,2.0469),"喀土穆市":(32.5599,15.5007),
    "地拉那市":(19.8187,41.3317),"阿斯马拉":(38.9318,15.3229),"阿斯马拉市":(38.9318,15.3229),
    "拉巴特市":(-6.8498,33.9716),"暹粒":(103.8548,13.3671),"磅湛":(104.6652,12.1192),
    "曼德勒":(96.0785,21.9588),"蒲甘":(94.8585,21.1717),"乌兰巴托市":(106.9057,47.8864),
    "温都尔汗":(110.6552,47.3238),"亚格拉":(78.0081,27.1767),"大马士革":(36.2765,33.5102),
}

INTERNATIONAL_NAMES = {
    "巴黎","仰光","仰光市","金边","金边市","开罗市","内罗毕","内罗毕市",
    "喀布尔","喀布尔市","莫斯科市","达卡","卡拉奇","卡拉奇市","伊斯兰堡",
    "拉合尔","拉瓦尔品第","雅加达","雅加达市","万隆市","河内市","平壤市",
    "元山市","科伦坡市","日内瓦","柏林市","德里市","加德满都市","突尼斯市",
    "阿尔及尔市","阿克拉市","巴马科市","科纳克里市","摩加迪沙市","喀土穆市",
    "地拉那市","阿斯马拉","阿斯马拉市","拉巴特市","暹粒","磅湛","曼德勒",
    "蒲甘","乌兰巴托市","温都尔汗","亚格拉","大马士革","白马市","朝鲜",
}

# 预计算：把所有国内坐标从 GCJ02 转 WGS84
LOCATION_COORDS = {}
for name, (lng, lat) in LOCATION_COORDS_RAW.items():
    if name in INTERNATIONAL_NAMES:
        LOCATION_COORDS[name] = (lng, lat)
    else:
        LOCATION_COORDS[name] = gcj02_to_wgs84(lng, lat)


def amap_geocode(address):
    """调用高德 REST 地理编码接口（WGS84 返回需再转，这里得到GCJ02再转WGS84）"""
    url = "https://restapi.amap.com/v3/geocode/geo?" + urllib.parse.urlencode({
        "key": AMAP_KEY, "address": address, "output": "json"
    })
    try:
        with urllib.request.urlopen(url, timeout=6) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0]["location"]
            lng, lat = map(float, loc.split(","))
            return gcj02_to_wgs84(lng, lat)
    except Exception as e:
        print(f"   API失败 {address}: {e}")
    return None


def get_phase(date_num):
    if date_num <= 19231101: return 1
    if date_num <= 19370929: return 2
    if date_num <= 19451025: return 3
    if date_num <= 19490527: return 4
    return 5


def parse_date(val):
    if pd.isna(val):
        return None, 0, 0, 0, 0
    try:
        if hasattr(val, 'year'):
            y, m, d = val.year, val.month, val.day
        else:
            val = pd.Timestamp(val)
            y, m, d = val.year, val.month, val.day
        return f"{y:04d}-{m:02d}-{d:02d}", y*10000+m*100+d, y, m, d
    except Exception:
        return None, 0, 0, 0, 0


def main():
    print("=" * 60)
    print("陈毅历史行迹图 - 地理编码（WGS84，供Leaflet/OSM使用）")
    print("=" * 60)

    df = pd.read_excel(EXCEL_FILE)
    print(f"读取 {len(df)} 条事件")

    unique_locs = [str(l).strip() for l in df["*地点"].dropna().unique() if str(l).strip()]
    print(f"唯一地点 {len(unique_locs)} 个")

    location_coords = {}
    missing = []
    for loc in unique_locs:
        if loc in LOCATION_COORDS:
            lng, lat = LOCATION_COORDS[loc]
            location_coords[loc] = {"lng": lng, "lat": lat,
                                    "is_international": loc in INTERNATIONAL_NAMES}
        else:
            print(f"   → 调用高德API: {loc}")
            res = amap_geocode(loc)
            time.sleep(0.3)
            if res:
                location_coords[loc] = {"lng": res[0], "lat": res[1], "is_international": False}
            else:
                missing.append(loc)
                location_coords[loc] = {"lng": None, "lat": None, "is_international": False}

    print(f"\n✓ 匹配 {len(unique_locs)-len(missing)} / {len(unique_locs)}")
    if missing:
        print(f"✗ 未匹配: {missing}")

    events = []
    for i, row in df.iterrows():
        loc = str(row["*地点"]).strip() if pd.notna(row["*地点"]) else None
        date_str, date_num, y, m, d = parse_date(row.get("*起始日期（YYYY/MM/DD）"))
        phase = get_phase(date_num) if date_num > 0 else 5
        info = location_coords.get(loc, {}) if loc else {}
        title = str(row.get("*事件名【主体名+动词+客体名（地点名）】", "")).strip()
        desc = str(row.get("被拆解语句", "")).strip()
        if desc == "nan": desc = title
        events.append({
            "id": i+1, "date": date_str, "date_num": date_num,
            "year": y, "month": m, "day": d,
            "location": loc or "", "title": title, "description": desc,
            "phase": phase,
            "lng": info.get("lng"), "lat": info.get("lat"),
            "has_coords": info.get("lng") is not None,
            "is_international": info.get("is_international", False),
        })

    events.sort(key=lambda e: e["date_num"] if e["date_num"] > 0 else 99999999)
    dated = [e for e in events if e["date_num"] > 0]

    geodata = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_events": len(events),
            "events_with_coords": sum(1 for e in events if e["has_coords"]),
            "unique_locations": len(unique_locs),
            "coord_system": "WGS84",
            "date_range": [dated[0]["date"] if dated else "", dated[-1]["date"] if dated else ""],
        },
        "phases": PHASES,
        "events": events,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(geodata, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 已输出 {OUTPUT_FILE}")
    print(f"   总事件 {len(events)} · 有坐标 {sum(1 for e in events if e['has_coords'])}")
    print(f"   日期范围 {geodata['meta']['date_range']}")


if __name__ == "__main__":
    main()
