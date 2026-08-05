---
name: baidu-index-crawler
description: 爬取百度指数数据（搜索指数、资讯指数、内容头条），支持按省/市地域筛选，输出 Excel 文件。Make sure to use this skill whenever the user mentions 百度指数, Baidu Index, 搜索指数, 资讯指数, 搜索热度, 关键词趋势, or wants to download/crawl trend data for Chinese keywords, even if they don't explicitly ask for "百度指数."
---

# 百度指数爬虫

用 Python 脚本爬取百度指数（Baidu Index）数据，输出 Excel 文件。

## 脚本路径

```
.claude/skills/baidu-index-crawler/scripts/baidu_index_crawler.py
```

认证文件（脚本同目录）：
- `baidu_cipher.txt` — Cipher-Text 请求头
- `baidu_cookies.txt` — Cookie 请求头

---

## 完整工作流程

### 第一步：确认爬取参数

从用户的消息中提取参数，不明确的向用户确认：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| **关键词** (必填) | 搜索关键词，如 "人工智能"、"房价" | — |
| **时间范围** | `--days 7/30/90/180/365`、`--days all`（全部历史）、或用 `--start-date` / `--end-date` 指定区间 | `30` |
| **指数类型** | `search`（搜索指数）/ `feed`（资讯指数·内容头条） | `search` |
| **地域** | 全国 / 省名 / 市名 / area 码，多地域用 `--regions` 逗号分隔 | `全国` |
| **补零** | `--fill-gaps` 缺失日期填 0 | 不补 |
| **合并** | `--combined` 多地域合并到一个 Excel 宽表 | 分文件 |

如果用户想查看可用地域，直接跑 `--list-areas`（无需认证）：

```bash
python3 .claude/skills/baidu-index-crawler/scripts/baidu_index_crawler.py --list-areas
```

### 第二步：检查依赖

```bash
pip install pandas requests openpyxl
```

### 第三步：检查并配置认证信息

**检查认证文件是否存在且非空：**

```bash
cat .claude/skills/baidu-index-crawler/scripts/baidu_cipher.txt 2>/dev/null
cat .claude/skills/baidu-index-crawler/scripts/baidu_cookies.txt 2>/dev/null
```

**如果文件存在且内容非空 → 跳到第四步。**

**如果文件不存在或为空 → 引导用户获取认证：**

向用户展示以下引导（分两步，先 Cipher-Text，再 Cookie）：

---

> 🔑 **需要百度指数认证信息，请按以下步骤获取：**
>
> **第一步：获取 Cipher-Text**
> 1. 用浏览器打开 https://index.baidu.com 并登录
> 2. 按 F12 → 切换到 **Network**（网络）面板
> 3. 在百度指数页面搜索任意关键词（如"天氣"）
> 4. 在 Network 中找到 `SearchApi/index` 请求，点击它
> 5. 右侧找到 **Request Headers**，找到 **Cipher-Text** 这一行
> 6. 把 **Cipher-Text** 的值复制给我
>
> （格式类似 `1760000000000_1760000000000_AbCdEf...`）

等用户粘贴 Cipher-Text 后，写入文件：

```bash
echo "用户粘贴的内容" > .claude/skills/baidu-index-crawler/scripts/baidu_cipher.txt
```

然后继续引导用户获取 Cookie：

> ✅ Cipher-Text 已保存。**第二步：获取 Cookie**
> 1. 在同一个请求的 Request Headers 中找到 **Cookie** 这一行
> 2. 把整个 **Cookie** 的值复制给我
>
> （格式类似 `BDUSS=...; BAIDUID=...; ...`，很长是正常的）

等用户粘贴 Cookie 后，写入文件：

```bash
echo "用户粘贴的内容" > .claude/skills/baidu-index-crawler/scripts/baidu_cookies.txt
```

认证信息配好后通知用户，然后继续执行爬取。

### 第四步：运行爬取

根据第一步确认的参数组装命令：

```bash
python3 .claude/skills/baidu-index-crawler/scripts/baidu_index_crawler.py "关键词" [参数...]
```

**常用命令示例：**

```bash
# 基础：近30天搜索指数，全国
python3 <skill>/scripts/baidu_index_crawler.py "人工智能"

# 指定天数
python3 <skill>/scripts/baidu_index_crawler.py "人工智能" --days 90

# 全部历史（搜索指数约 2011 至今）
python3 <skill>/scripts/baidu_index_crawler.py "人工智能" --days all --fill-gaps

# 指定指数类型
python3 <skill>/scripts/baidu_index_crawler.py "人工智能" --days 7 --type feed

# 指定地域
python3 <skill>/scripts/baidu_index_crawler.py "人工智能" --days 365 --area 广东

# 自定义日期区间
python3 <skill>/scripts/baidu_index_crawler.py "人工智能" --start-date 2020-01-01 --end-date 2024-12-31

# 多地域对比
python3 <skill>/scripts/baidu_index_crawler.py "人工智能" --regions 全国,北京,上海,广东 --days 90 --combined
```

如果用户同时需要多种指数类型（如搜索指数 + 资讯指数），分别执行多条命令。

### 第五步：处理结果 or 处理失败

**成功时：** 告诉用户：
- 生成的 Excel 文件路径和文件名
- 数据概览（行数、日期范围）

**如果运行时报以下错误 → 认证过期，帮用户刷新：**

- `未获取到数据` / `异常访问行为` / `status != 0` / `status_code != 200`
- 任何百度风控相关的提示

向用户说：

> ⚠️ 认证信息可能已过期，需要更新。请重新获取：
> （然后重复第三步的引导流程，让用户粘贴新的 Cipher-Text 和 Cookie）

**注意：** 过期刷新时两步一起引导即可，不需要分两步；首次配置时分两步是为了降低用户负担。

### 第六步：如需查看 Excel 内容

如果用户想预览数据，可以用 pandas 读取并展示前几行：

```bash
python3 -c "
import pandas as pd
df = pd.read_excel('文件路径')
print(f'共 {len(df)} 行')
print(df.head(10).to_string())
"
```

---

## 参数速查

| CLI 参数 | 取值 | 说明 |
|----------|------|------|
| `keyword` | 任意中文/英文 | 位置参数，必填 |
| `--days` | `7/30/90/180/365` 或 `all` | 快捷天数，默认 30 |
| `--type` | `search` / `feed` | 指数类型，默认 search |
| `--area` | 全国/省名/市名/数字码 | 单地域，默认全国 |
| `--regions` | `全国,广东,合肥` | 多地域逗号分隔 |
| `--start-date` | `YYYY-MM-DD` | 自定义起始日期 |
| `--end-date` | `YYYY-MM-DD` | 自定义结束日期 |
| `--fill-gaps` | flag | 缺失日期补 0 |
| `--combined` | flag | 多地域合并为宽表 |
| `--list-areas` | flag | 列出可用地域（无需认证） |
| `--output-dir` | 目录路径 | 自定义输出目录 |

## 输出说明

| 指数类型 | Excel 列 |
|----------|----------|
| `search`（搜索指数） | 日期、整体指数(PC+移动)、PC端指数、移动端指数 |
| `feed`（资讯指数·内容头条） | 日期、资讯指数（内容头条） |

## 注意事项

- 百度 Cookie 一般 1-2 周过期，Cipher-Text 随页面刷新更换
- 脚本内置 1 秒请求间隔防风控，长区间自动按年分块保持日粒度
- 资讯指数（内容头条）约 2017 年起有数据，更早的可能为空
- `--list-areas` 不需要认证，可以随时查看
