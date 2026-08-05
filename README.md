# baidu-index-crawler
百度指数爬虫Skill（仅用于学术使用）

Claude Code skill —— 在对话中直接爬取百度指数数据，支持搜索指数、资讯指数（内容头条），可按省/市地域筛选，输出 Excel 文件。

## 安装

### 方式一：直接克隆（推荐）

```bash
mkdir -p ~/.claude/skills
cd ~/.claude/skills
git clone https://github.com/Nibbles135/baidu-index-crawler.git
```

### 方式二：下载 .skill 文件

从 [Releases](https://github.com/Nibbles135/baidu-index-crawler/releases) 下载 `baidu-index-crawler.skill`，然后在 Claude Code 中安装。

### 依赖

```bash
pip install pandas requests openpyxl
```

## 配置认证（首次使用必须）

百度指数需要登录态才能访问。**首次使用前需要配置 Cookie 和 Cipher-Text：**

1. 用浏览器打开 https://index.baidu.com 并登录
2. 按 F12 → **Network** 面板
3. 搜索任意关键词
4. 找到 `SearchApi/index` 请求，查看 **Request Headers**
5. 复制 **Cipher-Text** 和 **Cookie** 的值

然后在脚本同目录下创建两个文件：

```bash
cd ~/.claude/skills/baidu-index-crawler/scripts

# 写入 Cipher-Text（一行）
echo "你的Cipher-Text值" > baidu_cipher.txt

# 写入 Cookie（一行，很长是正常的）
echo "你的Cookie值" > baidu_cookies.txt
```

或者直接编辑 `scripts/baidu_index_crawler.py` 中的 `CIPHER_TEXT` 和 `COOKIE_VALUE` 变量。

> ⚠️ Cookie 一般 1-2 周过期，Cipher-Text 随页面刷新更换。过期后重复上述步骤更新文件即可，无需改代码。

## 使用

安装后，直接在对话中说：

> "帮我爬取「人工智能」近 90 天的百度搜索指数"
> "爬取「房价」2020 到 2024 年的搜索指数，按广东"
> "对比北京、上海、深圳的「GDP」搜索指数近 30 天"
> "看看百度指数支持哪些地域"

Claude 会自动识别意图、确认参数、运行脚本、返回 Excel 文件。

### 命令行直接使用

也可以直接跑脚本：

```bash
# 基础用法
python scripts/baidu_index_crawler.py "人工智能" --days 30

# 指定指数类型：search=搜索指数, feed=资讯指数（内容头条）
python scripts/baidu_index_crawler.py "人工智能" --days 7 --type feed

# 全部历史（搜索指数约 2011 至今）
python scripts/baidu_index_crawler.py "人工智能" --days all --fill-gaps

# 指定地域
python scripts/baidu_index_crawler.py "人工智能" --days 365 --area 广东

# 自定义日期区间
python scripts/baidu_index_crawler.py "人工智能" --start-date 2020-01-01 --end-date 2024-12-31

# 多地域对比
python scripts/baidu_index_crawler.py "人工智能" --regions 全国,北京,上海,广东 --days 90 --combined

# 查看可用地域
python scripts/baidu_index_crawler.py --list-areas
```

## 参数说明

| 参数 | 取值 | 说明 |
|------|------|------|
| `keyword` | 任意中文/英文 | 位置参数，必填 |
| `--days` | `7/30/90/180/365` 或 `all` | 快捷天数，默认 30 |
| `--type` | `search` / `feed` | 指数类型，默认 search |
| `--area` | 全国/省名/市名/数字码 | 单地域，默认全国 |
| `--regions` | `全国,广东,合肥` | 多地域逗号分隔 |
| `--start-date` | `YYYY-MM-DD` | 自定义起始日期 |
| `--end-date` | `YYYY-MM-DD` | 自定义结束日期 |
| `--fill-gaps` | flag | 缺失日期补 0 |
| `--combined` | flag | 多地域合并为一张宽表 |
| `--list-areas` | flag | 列出可用地域（无需认证） |
| `--output-dir` | 目录路径 | 自定义输出目录 |

## 输出

| 指数类型 | Excel 列 |
|----------|----------|
| `search`（搜索指数） | 日期、整体指数(PC+移动)、PC端指数、移动端指数 |
| `feed`（资讯指数·内容头条） | 日期、资讯指数（内容头条） |

## 注意事项

- 脚本内置 1 秒请求间隔防风控
- 长区间（>365 天）自动按年分块，保持日粒度
- 搜索指数约 2011 年起有数据，资讯指数（内容头条）约 2017 年起

## 项目结构

```
baidu-index-crawler/
├── SKILL.md                        # Claude Code skill 定义
├── README.md                       # 本文件
└── scripts/
    └── baidu_index_crawler.py      # 爬虫脚本
```

## License

MIT
