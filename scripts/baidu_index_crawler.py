# -*- coding:utf-8 -*-
"""
百度指数爬虫（地域版）
====================
  - 支持按省份 / 城市爬取（百度指数用自定义数字 area 码，不是 GB 行政区划码）
  - area 码表来源：从 index.baidu.com 前端 JS 包提取（省份 901~934，城市见 cityShip）
  - 全国 = area 0；省份示例 928=安徽、913=广东、911=北京；城市示例 189=合肥、95=广州
  - 直辖市（北京/上海/天津/重庆）无下级城市，直接用省码即可

用法:
  python baidu_index_crawler.py "关键词" --days 365
  python baidu_index_crawler.py "关键词" --days all --type search --area 广东 --fill-gaps
  python baidu_index_crawler.py "关键词" --start-date 2020-01-01 --end-date 2024-12-31
  python baidu_index_crawler.py "关键词" --regions 全国,安徽,广东 --days 90 --combined
  python baidu_index_crawler.py --list-areas
"""
import argparse
import datetime
import json
import os
import re
import time
from urllib.parse import quote

import pandas as pd
import requests

# ============================================================
# 认证配置 —— 请在此填写你的百度 Cookie 和 Cipher-Text
# 获取方式：登录 index.baidu.com，从浏览器开发者工具 Network 面板
# 复制任意接口请求的 Cookie 和 Cipher-Text 请求头。
# 也可以在同目录下放置 baidu_cookies.txt 和 baidu_cipher.txt 来覆盖。
# ============================================================
CIPHER_TEXT = ""  # TODO: 填写你的 Cipher-Text
COOKIE_VALUE = ""  # TODO: 填写你的 Cookie (格式: "k=v; k=v; ...")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    "Host": "index.baidu.com",
    "Referer": "https://index.baidu.com/v2/main/index.html",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Ch-Ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Connection": "keep-alive",
    "Cipher-Text": CIPHER_TEXT,
}

# 优先从同目录 baidu_cipher.txt 读取最新 Cipher-Text
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CIPHER_FILE = os.path.join(_SCRIPT_DIR, "baidu_cipher.txt")
if os.path.exists(_CIPHER_FILE):
    with open(_CIPHER_FILE, "r", encoding="utf-8") as _f:
        _cipher_from_file = _f.read().strip()
    if _cipher_from_file:
        CIPHER_TEXT = _cipher_from_file
# 必须同步更新 HEADERS（因为 dict 初始化时用了原始空值）
HEADERS["Cipher-Text"] = CIPHER_TEXT

# 优先从同目录 baidu_cookies.txt 读取最新 Cookie
_COOKIE_FILE = os.path.join(_SCRIPT_DIR, "baidu_cookies.txt")
if os.path.exists(_COOKIE_FILE):
    with open(_COOKIE_FILE, "r", encoding="utf-8") as _f:
        _cookie_from_file = _f.read().strip()
    if _cookie_from_file:
        COOKIE_VALUE = _cookie_from_file

COOKIES = {"Cookie": COOKIE_VALUE}

# 输出目录：默认用户 home 目录，可通过 --output-dir 覆盖
OUTPUT_DIR = os.path.expanduser("~")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_html(url):
    """发送请求，防风控延时 1 秒"""
    time.sleep(1)
    try:
        response = requests.get(url, headers=HEADERS, cookies=COOKIES, timeout=20)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"请求失败：{e}")
        return ""


def decrypt(ptbk, encrypted_data):
    """百度指数官方解密算法（还原真实指数）"""
    if not ptbk or not encrypted_data:
        return ""
    n = list(ptbk)
    i = list(encrypted_data)
    mapping = {}
    half_len = len(n) // 2
    for j, k in zip(n[half_len:], n[:half_len]):
        mapping[k] = j
    return "".join([mapping.get(char, "") for char in i])


def get_ptbk(uniqid):
    """获取解密密钥 ptbk"""
    url = f"https://index.baidu.com/Interface/ptbk?uniqid={uniqid}"
    resp_text = get_html(url)
    if resp_text:
        return json.loads(resp_text)["data"]
    return ""


def _decrypt_series(data, index_type):
    """从接口响应 data 中解密出各系列数值，返回 (start, end, type, all, pc, wise)"""
    if index_type == "search":
        series = data["userIndexes"][0]
        start = series["all"]["startDate"]
        end = series["all"]["endDate"]
        typ = series.get("type", "day")
    else:
        series = data["index"][0]
        start = series.get("startDate", "")
        end = series.get("endDate", "")
        typ = series.get("type", "day")

    ptbk = get_ptbk(data["uniqid"])

    def values(field):
        if index_type == "search":
            enc = series[field]["data"]
        else:
            enc = series.get("data") if field == "all" else ""
        return [v for v in decrypt(ptbk, enc or "").split(",") if v != ""]

    if index_type == "search":
        return start, end, typ, values("all"), values("pc"), values("wise")
    return start, end, typ, values("all"), [], []


def _fetch_window(base_url, start, end, index_type):
    """请求 [start, end] 区间，返回 (dates, all, pc, wise)；失败返回 None"""
    url = f"{base_url}&startDate={start:%Y-%m-%d}&endDate={end:%Y-%m-%d}"
    resp_text = get_html(url)
    if not resp_text:
        return None
    data = json.loads(resp_text)
    if data.get("status") != 0:
        print(f"⚠️ 分块请求失败（{start}~{end}）：{data.get('message')}")
        return None
    start_str, end_str, typ, all_v, pc_v, wise_v = _decrypt_series(data["data"], index_type)
    if not all_v:
        return None
    range_start = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
    step = 7 if typ == "week" else 1
    n = len(all_v)
    if index_type == "search":
        n = min(n, len(pc_v), len(wise_v))
    dates = [
        (range_start + datetime.timedelta(days=step * i)).strftime("%Y-%m-%d")
        for i in range(n)
    ]
    return dates, all_v[:n], (pc_v[:n] if pc_v else []), (wise_v[:n] if wise_v else [])


# ===================== 地域（省/市）支持 =====================
AREA_DATA_JSON = r"""{"provinceGroup":[{"label":"A - G","values":["928","934","911","904","909","913","912","925","902"]},{"label":"H - J","values":["920","921","927","908","906","930","922","916","903"]},{"label":"L - S","values":["907","905","919","918","910","914","901","929","924"]},{"label":"T - Z","values":["923","931","932","933","926","915","917"]}],"provinces":{"901":"山东","902":"贵州","903":"江西","904":"重庆","905":"内蒙古","906":"湖北","907":"辽宁","908":"湖南","909":"福建","910":"上海","911":"北京","912":"广西","913":"广东","914":"四川","915":"云南","916":"江苏","917":"浙江","918":"青海","919":"宁夏","920":"河北","921":"黑龙江","922":"吉林","923":"天津","924":"陕西","925":"甘肃","926":"新疆","927":"河南","928":"安徽","929":"山西","930":"海南","931":"台湾","932":"西藏","933":"香港","934":"澳门"},"cityShip":{"901":[{"label":"济南","value":"1"},{"label":"滨州","value":"76"},{"label":"青岛","value":"77"},{"label":"烟台","value":"78"},{"label":"临沂","value":"79"},{"label":"潍坊","value":"80"},{"label":"淄博","value":"81"},{"label":"东营","value":"82"},{"label":"聊城","value":"83"},{"label":"菏泽","value":"84"},{"label":"枣庄","value":"85"},{"label":"德州","value":"86"},{"label":"威海","value":"88"},{"label":"济宁","value":"352"},{"label":"泰安","value":"353"},{"label":"莱芜","value":"356"},{"label":"日照","value":"366"}],"902":[{"label":"贵阳","value":"2"},{"label":"黔南","value":"3"},{"label":"六盘水","value":"4"},{"label":"遵义","value":"59"},{"label":"黔东南","value":"61"},{"label":"铜仁","value":"422"},{"label":"安顺","value":"424"},{"label":"毕节","value":"426"},{"label":"黔西南","value":"588"}],"903":[{"label":"南昌","value":"5"},{"label":"九江","value":"6"},{"label":"鹰潭","value":"7"},{"label":"抚州","value":"8"},{"label":"上饶","value":"9"},{"label":"赣州","value":"10"},{"label":"吉安","value":"115"},{"label":"萍乡","value":"136"},{"label":"景德镇","value":"137"},{"label":"新余","value":"246"},{"label":"宜春","value":"256"}],"904":[],"905":[{"label":"呼和浩特","value":"20"},{"label":"包头","value":"13"},{"label":"鄂尔多斯","value":"14"},{"label":"巴彦淖尔","value":"15"},{"label":"乌海","value":"16"},{"label":"阿拉善盟","value":"17"},{"label":"锡林郭勒盟","value":"19"},{"label":"赤峰","value":"21"},{"label":"通辽","value":"22"},{"label":"呼伦贝尔","value":"25"},{"label":"乌兰察布","value":"331"},{"label":"兴安盟","value":"333"}],"906":[{"label":"武汉","value":"28"},{"label":"黄石","value":"30"},{"label":"荆州","value":"31"},{"label":"襄阳","value":"32"},{"label":"黄冈","value":"33"},{"label":"荆门","value":"34"},{"label":"宜昌","value":"35"},{"label":"十堰","value":"36"},{"label":"随州","value":"37"},{"label":"恩施","value":"38"},{"label":"鄂州","value":"39"},{"label":"咸宁","value":"40"},{"label":"孝感","value":"41"},{"label":"仙桃","value":"42"},{"label":"天门","value":"73"},{"label":"潜江","value":"74"},{"label":"神农架","value":"687"}],"907":[{"label":"沈阳","value":"150"},{"label":"大连","value":"29"},{"label":"盘锦","value":"151"},{"label":"鞍山","value":"215"},{"label":"朝阳","value":"216"},{"label":"锦州","value":"217"},{"label":"铁岭","value":"218"},{"label":"丹东","value":"219"},{"label":"本溪","value":"220"},{"label":"营口","value":"221"},{"label":"抚顺","value":"222"},{"label":"阜新","value":"223"},{"label":"辽阳","value":"224"},{"label":"葫芦岛","value":"225"}],"908":[{"label":"长沙","value":"43"},{"label":"岳阳","value":"44"},{"label":"衡阳","value":"45"},{"label":"株洲","value":"46"},{"label":"湘潭","value":"47"},{"label":"益阳","value":"48"},{"label":"郴州","value":"49"},{"label":"湘西","value":"65"},{"label":"娄底","value":"66"},{"label":"怀化","value":"67"},{"label":"常德","value":"68"},{"label":"张家界","value":"226"},{"label":"永州","value":"269"},{"label":"邵阳","value":"405"}],"909":[{"label":"福州","value":"50"},{"label":"莆田","value":"51"},{"label":"三明","value":"52"},{"label":"龙岩","value":"53"},{"label":"厦门","value":"54"},{"label":"泉州","value":"55"},{"label":"漳州","value":"56"},{"label":"宁德","value":"87"},{"label":"南平","value":"253"}],"910":[],"911":[],"912":[{"label":"南宁","value":"90"},{"label":"柳州","value":"89"},{"label":"桂林","value":"91"},{"label":"贺州","value":"92"},{"label":"贵港","value":"93"},{"label":"玉林","value":"118"},{"label":"河池","value":"119"},{"label":"北海","value":"128"},{"label":"钦州","value":"129"},{"label":"防城港","value":"130"},{"label":"百色","value":"131"},{"label":"梧州","value":"132"},{"label":"来宾","value":"506"},{"label":"崇左","value":"665"}],"913":[{"label":"广州","value":"95"},{"label":"深圳","value":"94"},{"label":"东莞","value":"133"},{"label":"云浮","value":"195"},{"label":"佛山","value":"196"},{"label":"湛江","value":"197"},{"label":"江门","value":"198"},{"label":"惠州","value":"199"},{"label":"珠海","value":"200"},{"label":"韶关","value":"201"},{"label":"阳江","value":"202"},{"label":"茂名","value":"203"},{"label":"潮州","value":"204"},{"label":"揭阳","value":"205"},{"label":"中山","value":"207"},{"label":"清远","value":"208"},{"label":"肇庆","value":"209"},{"label":"河源","value":"210"},{"label":"梅州","value":"211"},{"label":"汕头","value":"212"},{"label":"汕尾","value":"213"}],"914":[{"label":"成都","value":"97"},{"label":"宜宾","value":"96"},{"label":"绵阳","value":"98"},{"label":"广元","value":"99"},{"label":"遂宁","value":"100"},{"label":"巴中","value":"101"},{"label":"内江","value":"102"},{"label":"泸州","value":"103"},{"label":"南充","value":"104"},{"label":"德阳","value":"106"},{"label":"乐山","value":"107"},{"label":"广安","value":"108"},{"label":"资阳","value":"109"},{"label":"自贡","value":"111"},{"label":"攀枝花","value":"112"},{"label":"达州","value":"113"},{"label":"雅安","value":"114"},{"label":"眉山","value":"291"},{"label":"甘孜","value":"417"},{"label":"阿坝","value":"457"},{"label":"凉山","value":"479"}],"915":[{"label":"昆明","value":"117"},{"label":"玉溪","value":"123"},{"label":"楚雄","value":"124"},{"label":"大理","value":"334"},{"label":"昭通","value":"335"},{"label":"红河","value":"337"},{"label":"曲靖","value":"339"},{"label":"丽江","value":"342"},{"label":"临沧","value":"350"},{"label":"文山","value":"437"},{"label":"保山","value":"438"},{"label":"普洱","value":"666"},{"label":"西双版纳","value":"668"},{"label":"德宏","value":"669"},{"label":"怒江","value":"671"},{"label":"迪庆","value":"672"}],"916":[{"label":"南京","value":"125"},{"label":"苏州","value":"126"},{"label":"无锡","value":"127"},{"label":"连云港","value":"156"},{"label":"淮安","value":"157"},{"label":"扬州","value":"158"},{"label":"泰州","value":"159"},{"label":"盐城","value":"160"},{"label":"徐州","value":"161"},{"label":"常州","value":"162"},{"label":"南通","value":"163"},{"label":"镇江","value":"169"},{"label":"宿迁","value":"172"}],"917":[{"label":"杭州","value":"138"},{"label":"丽水","value":"134"},{"label":"金华","value":"135"},{"label":"温州","value":"149"},{"label":"台州","value":"287"},{"label":"衢州","value":"288"},{"label":"宁波","value":"289"},{"label":"绍兴","value":"303"},{"label":"嘉兴","value":"304"},{"label":"湖州","value":"305"},{"label":"舟山","value":"306"}],"918":[{"label":"西宁","value":"139"},{"label":"海西","value":"608"},{"label":"海东","value":"652"},{"label":"玉树","value":"659"},{"label":"海南","value":"676"},{"label":"海北","value":"682"},{"label":"黄南","value":"685"},{"label":"果洛","value":"688"}],"919":[{"label":"银川","value":"140"},{"label":"吴忠","value":"395"},{"label":"固原","value":"396"},{"label":"石嘴山","value":"472"},{"label":"中卫","value":"480"}],"920":[{"label":"石家庄","value":"141"},{"label":"衡水","value":"143"},{"label":"张家口","value":"144"},{"label":"承德","value":"145"},{"label":"秦皇岛","value":"146"},{"label":"廊坊","value":"147"},{"label":"沧州","value":"148"},{"label":"保定","value":"259"},{"label":"唐山","value":"261"},{"label":"邯郸","value":"292"},{"label":"邢台","value":"293"}],"921":[{"label":"哈尔滨","value":"152"},{"label":"大庆","value":"153"},{"label":"伊春","value":"295"},{"label":"大兴安岭","value":"297"},{"label":"黑河","value":"300"},{"label":"鹤岗","value":"301"},{"label":"七台河","value":"302"},{"label":"齐齐哈尔","value":"319"},{"label":"佳木斯","value":"320"},{"label":"牡丹江","value":"322"},{"label":"鸡西","value":"323"},{"label":"绥化","value":"324"},{"label":"双鸭山","value":"359"}],"922":[{"label":"长春","value":"154"},{"label":"四平","value":"155"},{"label":"辽源","value":"191"},{"label":"松原","value":"194"},{"label":"吉林","value":"270"},{"label":"通化","value":"407"},{"label":"白山","value":"408"},{"label":"白城","value":"410"},{"label":"延边","value":"525"}],"923":[],"924":[{"label":"西安","value":"165"},{"label":"铜川","value":"271"},{"label":"安康","value":"272"},{"label":"宝鸡","value":"273"},{"label":"商洛","value":"274"},{"label":"渭南","value":"275"},{"label":"汉中","value":"276"},{"label":"咸阳","value":"277"},{"label":"榆林","value":"278"},{"label":"延安","value":"401"}],"925":[{"label":"兰州","value":"166"},{"label":"庆阳","value":"281"},{"label":"定西","value":"282"},{"label":"武威","value":"283"},{"label":"酒泉","value":"284"},{"label":"张掖","value":"285"},{"label":"嘉峪关","value":"286"},{"label":"平凉","value":"307"},{"label":"天水","value":"308"},{"label":"白银","value":"309"},{"label":"金昌","value":"343"},{"label":"陇南","value":"344"},{"label":"临夏","value":"346"},{"label":"甘南","value":"673"}],"926":[{"label":"乌鲁木齐","value":"467"},{"label":"石河子","value":"280"},{"label":"吐鲁番","value":"310"},{"label":"昌吉","value":"311"},{"label":"哈密","value":"312"},{"label":"阿克苏","value":"315"},{"label":"克拉玛依","value":"317"},{"label":"博尔塔拉","value":"318"},{"label":"阿勒泰","value":"383"},{"label":"喀什","value":"384"},{"label":"和田","value":"386"},{"label":"巴音郭楞","value":"499"},{"label":"伊犁","value":"520"},{"label":"塔城","value":"563"},{"label":"克孜勒苏柯尔克孜","value":"653"},{"label":"五家渠","value":"661"},{"label":"阿拉尔","value":"692"},{"label":"图木舒克","value":"693"}],"927":[{"label":"郑州","value":"168"},{"label":"南阳","value":"262"},{"label":"新乡","value":"263"},{"label":"开封","value":"264"},{"label":"焦作","value":"265"},{"label":"平顶山","value":"266"},{"label":"许昌","value":"268"},{"label":"安阳","value":"370"},{"label":"驻马店","value":"371"},{"label":"信阳","value":"373"},{"label":"鹤壁","value":"374"},{"label":"周口","value":"375"},{"label":"商丘","value":"376"},{"label":"洛阳","value":"378"},{"label":"漯河","value":"379"},{"label":"濮阳","value":"380"},{"label":"三门峡","value":"381"},{"label":"济源","value":"667"}],"928":[{"label":"合肥","value":"189"},{"label":"铜陵","value":"173"},{"label":"黄山","value":"174"},{"label":"池州","value":"175"},{"label":"宣城","value":"176"},{"label":"巢湖","value":"177"},{"label":"淮南","value":"178"},{"label":"宿州","value":"179"},{"label":"六安","value":"181"},{"label":"滁州","value":"182"},{"label":"淮北","value":"183"},{"label":"阜阳","value":"184"},{"label":"马鞍山","value":"185"},{"label":"安庆","value":"186"},{"label":"蚌埠","value":"187"},{"label":"芜湖","value":"188"},{"label":"亳州","value":"391"}],"929":[{"label":"太原","value":"231"},{"label":"大同","value":"227"},{"label":"长治","value":"228"},{"label":"忻州","value":"229"},{"label":"晋中","value":"230"},{"label":"临汾","value":"232"},{"label":"运城","value":"233"},{"label":"晋城","value":"234"},{"label":"朔州","value":"235"},{"label":"阳泉","value":"236"},{"label":"吕梁","value":"237"}],"930":[{"label":"海口","value":"239"},{"label":"万宁","value":"241"},{"label":"琼海","value":"242"},{"label":"三亚","value":"243"},{"label":"儋州","value":"244"},{"label":"东方","value":"456"},{"label":"五指山","value":"582"},{"label":"文昌","value":"670"},{"label":"陵水","value":"674"},{"label":"澄迈","value":"675"},{"label":"乐东","value":"679"},{"label":"临高","value":"680"},{"label":"定安","value":"681"},{"label":"昌江","value":"683"},{"label":"屯昌","value":"684"},{"label":"保亭","value":"686"},{"label":"白沙","value":"689"},{"label":"琼中","value":"690"}],"932":[{"label":"拉萨","value":"466"},{"label":"日喀则","value":"516"},{"label":"那曲","value":"655"},{"label":"林芝","value":"656"},{"label":"山南","value":"677"},{"label":"昌都","value":"678"},{"label":"阿里","value":"691"}],"933":[],"934":[]}}"""
AREA_DATA = json.loads(AREA_DATA_JSON)
AREA_PROVINCES = AREA_DATA["provinces"]
AREA_CITY_SHIP = AREA_DATA["cityShip"]

MUNICIPALITIES = ("北京", "上海", "天津", "重庆")

_AREA_SUFFIXES = ("特别行政区", "壮族自治区", "维吾尔自治区", "回族自治区", "自治区", "省", "市")


def resolve_area(area):
    """把用户传入的地域解析成百度 area 数字串与显示名。"""
    if area is None:
        return "0", "全国"
    s = str(area).strip()
    if s in ("0", "全国"):
        return "0", "全国"
    if s.isdigit():
        if s in AREA_PROVINCES:
            return s, AREA_PROVINCES[s]
        for cities in AREA_CITY_SHIP.values():
            for c in cities:
                if c["value"] == s:
                    return s, c["label"]
        raise ValueError(f"无法识别 area 码：{s}")
    name = s
    for suf in _AREA_SUFFIXES:
        name = name.replace(suf, "")
    for code, pn in AREA_PROVINCES.items():
        if pn == name:
            return code, pn
    for cities in AREA_CITY_SHIP.values():
        for c in cities:
            if c["label"] == name:
                return c["value"], c["label"]
    raise ValueError(
        f"无法识别地域：{area}。可用：全国 / 省名 / 市名 / area码（如 928、189）。"
        f"可用 --list-areas 查看全部省份与城市。"
    )


def list_areas():
    """打印全部省份及其下属城市（含 area 码），便于挑选地域。"""
    for code, name in sorted(AREA_PROVINCES.items(), key=lambda x: int(x[0])):
        cities = AREA_CITY_SHIP.get(code, [])
        if cities:
            city_str = "、".join(f"{c['label']}({c['value']})" for c in cities)
            print(f"{name} (省码 {code}): {city_str}")
        else:
            print(f"{name} (省码 {code}): 直辖市/无下级城市")


def crawl_regions(keyword, regions, days=30, index_type="search",
                  start_date=None, end_date=None, fill_gaps=False):
    """依次爬取多个地域，每个地域生成一个 Excel（多文件）。"""
    for area in regions:
        print(f"\n===== 地域：{area} =====")
        crawl_baidu_index(
            keyword, days=days, index_type=index_type,
            start_date=start_date, end_date=end_date,
            area=area, fill_gaps=fill_gaps,
        )


def crawl_regions_combined(keyword, regions, days=30, index_type="search",
                           start_date=None, end_date=None, fill_gaps=False):
    """把多个地域合并到同一个 Excel（宽表：日期 + 每地域一列整体指数）。"""
    value_col = "整体指数(PC+移动)" if index_type == "search" else "资讯指数（内容头条）"
    merged = None
    for area in regions:
        _, area_label = resolve_area(area)
        print(f"\n===== 地域：{area} =====")
        df = crawl_baidu_index(
            keyword, days=days, index_type=index_type,
            start_date=start_date, end_date=end_date,
            area=area, fill_gaps=fill_gaps, save=False,
        )
        if df is None or df.empty:
            print(f"⚠️ 地域 {area} 无数据，跳过")
            continue
        s = df[["日期", value_col]].rename(columns={value_col: area_label})
        merged = s if merged is None else merged.merge(s, on="日期", how="outer")

    if merged is None:
        print("❌ 没有任何地域数据")
        return
    merged = merged.sort_values("日期").reset_index(drop=True)

    if str(days).lower() == "all":
        range_tag = "全部日期"
    elif start_date or end_date:
        d0, d1 = merged["日期"].iloc[0], merged["日期"].iloc[-1]
        range_tag = f"{d0}~{d1}"
    else:
        range_tag = f"近{int(days)}天"
    file_label = "搜索指数" if index_type == "search" else "资讯指数"
    file_name = f"{keyword}_多地域_{file_label}_{range_tag}.xlsx"
    out_path = os.path.join(OUTPUT_DIR, file_name)
    merged.to_excel(out_path, index=False)
    print(f"✅ 已生成合并 Excel：{file_name}")
    print(merged.head())
    return merged


def crawl_baidu_index(keyword, days=30, index_type="search", start_date=None,
                      end_date=None, area="全国", fill_gaps=False, save=True):
    """爬取百度指数，统一「请求 -> 解密 -> 导出 Excel」流程。

    index_type: "search" 搜索指数 / "feed" 资讯指数（内容头条）
    days: 快捷天数（默认 30），如 7/30/90/180/365，"all" 表示全部历史
    start_date / end_date: 自定义区间 YYYY-MM-DD
    area: 地域，默认全国。支持全国/省名/市名/area 码
    fill_gaps: 缺失日期补 0，保证日期连续
    """
    area_code, area_label = resolve_area(area)
    encoded_keyword = quote(keyword, safe="")
    api_map = {
        "search": "SearchApi/index",
        "feed": "FeedSearchApi/getFeedIndex",
    }
    api_path = api_map.get(index_type, "SearchApi/index")
    base_url = (
        f"https://index.baidu.com/api/{api_path}?area={area_code}&word="
        f"[[%7B%22name%22:%22{encoded_keyword}%22,%22wordType%22:1%7D]]"
    )

    # ---- 1. 确定目标区间 ----
    if str(days).lower() == "all":
        # 全部日期：先探测接口给出的最早可用日期
        resp_text = get_html(base_url)
        if not resp_text:
            print("❌ 未获取到数据，请检查 Cookie / Cipher-Text 是否正确")
            return
        data = json.loads(resp_text)
        if data.get("status") != 0:
            print(f"⚠️ 接口返回异常：{data.get('message')}")
            return
        if index_type == "search":
            series = data["data"]["userIndexes"][0]
            start_str = series["all"]["startDate"]
            end_str = series["all"]["endDate"]
        else:
            series = data["data"]["index"][0]
            start_str = series.get("startDate", "")
            end_str = series.get("endDate", "")
        range_start = datetime.datetime.strptime(start_str, "%Y-%m-%d").date()
        range_end = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
        range_label = "全部日期"
    elif start_date or end_date:
        today = datetime.date.today()
        range_end = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
        range_start = datetime.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else (range_end - datetime.timedelta(days=3650))
        if range_start > range_end:
            range_start, range_end = range_end, range_start
        range_label = f"{range_start:%Y-%m-%d}~{range_end:%Y-%m-%d}"
    else:
        try:
            n = int(days)
        except (TypeError, ValueError):
            n = 30
        range_end = datetime.date.today()
        range_start = range_end - datetime.timedelta(days=n - 1)
        range_label = f"近{n}天"

    # ---- 2. 抓取数据（按窗口分块请求，>365 天自动分块保持日粒度）----
    span_days = (range_end - range_start).days + 1
    if span_days <= 365:
        windows = [(range_start, range_end)]
    else:
        windows = []
        cur = range_start
        while cur <= range_end:
            win_end = min(cur + datetime.timedelta(days=365), range_end)
            windows.append((cur, win_end))
            cur = win_end + datetime.timedelta(days=1)
        print(f"ℹ️ 跨度约 {span_days} 天，按 ≤365 天分块抓取逐日数据（共 {len(windows)} 块）")

    all_dates, all_vals, pc_vals, wise_vals = [], [], [], []
    for win_start, win_end in windows:
        res = _fetch_window(base_url, win_start, win_end, index_type)
        if res:
            d, a, p, w = res
            all_dates.extend(d)
            all_vals.extend(a)
            pc_vals.extend(p)
            wise_vals.extend(w)

    if not all_dates and not fill_gaps:
        print("❌ 没有获取到有效数据")
        return

    # ---- 3. 组表 ----
    if index_type == "search":
        n = min(len(all_dates), len(all_vals), len(pc_vals), len(wise_vals))
        result_df = pd.DataFrame({
            "日期": all_dates[:n],
            "整体指数(PC+移动)": all_vals[:n],
            "PC端指数": pc_vals[:n],
            "移动端指数": wise_vals[:n],
        })
    else:
        n = min(len(all_dates), len(all_vals))
        label = "资讯指数（内容头条）"
        result_df = pd.DataFrame({
            "日期": all_dates[:n],
            label: all_vals[:n],
        })

    file_label = "搜索指数" if index_type == "search" else "资讯指数"

    # ---- 4.5 可选：补零 ----
    if fill_gaps:
        full_dates = pd.date_range(
            start=range_start, end=range_end, freq="D"
        ).strftime("%Y-%m-%d")
        if result_df.empty:
            cols = list(result_df.columns)
            result_df = pd.DataFrame({"日期": full_dates})
            for c in cols[1:]:
                result_df[c] = 0
        else:
            result_df = (
                result_df.set_index("日期")
                .reindex(full_dates)
                .reset_index()
                .rename(columns={"index": "日期"})
                .fillna(0)
            )
            for c in result_df.columns[1:]:
                result_df[c] = (
                    pd.to_numeric(result_df[c], errors="coerce")
                    .fillna(0)
                    .astype(int)
                )

    count = len(result_df)

    # ---- 5. 导出 ----
    if save:
        area_tag = "" if area_label == "全国" else f"_{area_label}"
        if range_label.startswith("近"):
            file_name = f"{keyword}{area_tag}_{file_label}_{range_label}.xlsx"
        elif range_label == "全部日期":
            file_name = f"{keyword}{area_tag}_{file_label}_全部日期_{count}天.xlsx"
        else:
            file_name = f"{keyword}{area_tag}_{file_label}_{range_label}_{count}天.xlsx"
        output_path = os.path.join(OUTPUT_DIR, file_name)
        result_df.to_excel(output_path, index=False)
        print(f"✅ 已生成 Excel：{file_name}")
        print(f"📁 文件路径：{output_path}")
        print(result_df.head())
    return result_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="百度指数爬虫（地域版）—— 爬取百度搜索/资讯/内容头条指数，支持省/市地域筛选",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python baidu_index_crawler.py "老赖" --days 365
  python baidu_index_crawler.py "AI" --days all --type search --area 广东 --fill-gaps
  python baidu_index_crawler.py "房价" --start-date 2020-01-01 --end-date 2024-12-31 --area 北京
  python baidu_index_crawler.py "GDP" --regions 全国,安徽,广东,合肥 --days 90 --combined
  python baidu_index_crawler.py --list-areas
        """,
    )
    parser.add_argument("keyword", nargs="?", default=None, help="搜索关键词（如：老赖、AI、房价）")
    parser.add_argument("--days", default="30", help="快捷天数：7/30/90/180/365，或 'all' 表示全部历史（默认 30）")
    parser.add_argument("--type", dest="index_type", default="search",
                        choices=["search", "feed"],
                        help="指数类型：search=搜索指数, feed=资讯指数（内容头条）（默认 search）")
    parser.add_argument("--area", default="全国", help="单个地域：全国 / 省名 / 市名 / area 码（默认 全国）")
    parser.add_argument("--regions", default=None, help="多地域，逗号分隔（如：全国,安徽,广东,合肥）")
    parser.add_argument("--start-date", default=None, help="自定义开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="自定义结束日期 YYYY-MM-DD")
    parser.add_argument("--fill-gaps", action="store_true", default=False,
                        help="缺失日期补 0，保证日期连续")
    parser.add_argument("--combined", action="store_true", default=False,
                        help="多地域时合并到同一个 Excel（宽表），仅与 --regions 配合使用")
    parser.add_argument("--list-areas", action="store_true", default=False,
                        help="列出所有可用省份和城市（含 area 码），然后退出")
    parser.add_argument("--output-dir", default=None, help="自定义输出目录（默认当前工作目录）")

    args = parser.parse_args()

    if args.output_dir:
        OUTPUT_DIR = args.output_dir
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.list_areas:
        list_areas()
        exit(0)

    # 检查认证信息（--list-areas 不需要认证）
    if not CIPHER_TEXT and not os.path.exists(os.path.join(_SCRIPT_DIR, "baidu_cipher.txt")):
        print("⚠️ 未配置 Cipher-Text！")
        print("  请编辑脚本中的 CIPHER_TEXT 变量，或在脚本同目录放置 baidu_cipher.txt 文件。")
        print("  获取方式：登录 index.baidu.com，打开浏览器开发者工具 Network 面板，")
        print("  复制任意接口请求的 Cipher-Text 请求头。")
        exit(1)
    if not COOKIE_VALUE and not os.path.exists(os.path.join(_SCRIPT_DIR, "baidu_cookies.txt")):
        print("⚠️ 未配置 Cookie！")
        print("  请编辑脚本中的 COOKIE_VALUE 变量，或在脚本同目录放置 baidu_cookies.txt 文件。")
        print("  获取方式：登录 index.baidu.com，打开浏览器开发者工具 Network 面板，")
        print("  复制任意接口请求的 Cookie 请求头。")
        exit(1)

    if not args.keyword:
        parser.error("请提供搜索关键词，例如：python baidu_index_crawler.py \"老赖\" --days 365")

    if args.regions:
        region_list = [r.strip() for r in args.regions.split(",") if r.strip()]
        if args.combined:
            crawl_regions_combined(
                args.keyword, region_list,
                days=args.days, index_type=args.index_type,
                start_date=args.start_date, end_date=args.end_date,
                fill_gaps=args.fill_gaps,
            )
        else:
            crawl_regions(
                args.keyword, region_list,
                days=args.days, index_type=args.index_type,
                start_date=args.start_date, end_date=args.end_date,
                fill_gaps=args.fill_gaps,
            )
    else:
        crawl_baidu_index(
            args.keyword,
            days=args.days, index_type=args.index_type,
            start_date=args.start_date, end_date=args.end_date,
            area=args.area, fill_gaps=args.fill_gaps,
        )
