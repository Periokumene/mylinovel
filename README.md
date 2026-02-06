# 轻小说爬虫EPUB生成工具

从 linovelib.com 爬取轻小说内容并生成 EPUB 电子书。

## 项目结构

```
mylinovel/
├── crawler/                    # 爬虫模块
│   ├── __init__.py
│   ├── downloader.py          # HTTP下载器（统一处理请求、重试、限速）
│   ├── catalog_parser.py      # 目录页解析器（提取书籍信息和章节列表）
│   ├── special_chapter_resolver.py  # 特殊章节解析器（处理javascript:cid(0)链接）
│   ├── chapter_parser.py       # 章节内容解析器（使用Selenium下载章节正文）
│   └── reorder.py              # 动态页面内容提取工具
├── storage/                    # 存储模块
│   ├── __init__.py
│   └── chapter_storage.py      # 章节内容存储管理器
├── epub/                       # EPUB生成模块（待实现）
│   └── __init__.py
├── data/                       # 数据目录
│   ├── books/                  # 书籍结构JSON文件
│   └── chapters/               # 章节内容（按书籍ID分目录）
├── examples/                   # 示例文件
│   ├── book_structure.json     # 书籍结构示例
│   ├── pageUrls.txt            # 多页章节URL示例
│   └── *.html                  # 示例HTML文件
├── test_catalog/               # 目录页测试数据
├── test_loaddiff/              # 动态页面重排序测试数据
├── requirements.txt            # Python依赖
└── README.md                   # 本文件
```

## 安装依赖

### 1. 创建虚拟环境（推荐）

```bash
# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate

# Windows
python3 -m venv .venv
.venv\Scripts\activate
```

### 2. 安装依赖包

```bash
pip install -r requirements.txt
```

### 3. 依赖说明

- `requests`: HTTP请求库
- `beautifulsoup4`: HTML解析库
- `lxml`: HTML解析器后端
- `brotli`: Brotli压缩解压支持
- `selenium`: 浏览器自动化（用于章节内容解析）
- `webdriver-manager`: Chrome驱动自动管理
- `ebooklib`: EPUB生成（待使用）
- `tqdm`: 进度条显示（待使用）

## 使用方法

### 1. 解析目录页

解析书籍目录，提取书籍信息、卷信息和章节列表。

```bash
# 使用书籍ID（推荐）
python -m crawler.catalog_parser --book-id 4519

# 或使用完整URL
python -m crawler.catalog_parser --url https://www.linovelib.com/novel/4519/catalog
```

**输出文件**：
- `data/books/{book_id}_structure.json` - 书籍结构JSON文件
- `data/books/{book_id}_catalog.html` - HTML副本（用于调试）

**功能说明**：
- ✅ 提取书籍基本信息（书名、作者、最后更新时间、最新章节）
- ✅ 提取卷信息（卷名、封面URL、封面图片）
- ✅ 提取章节列表（章节标题、URL、序号）
- ✅ 处理异常链接（`javascript:cid(0)`），标记为 `needs_resolve: true`
- ✅ 自动解析特殊章节URL（通过上一章的多页导航）
- ✅ 保存为JSON格式，符合 `book_structure.json` 规范

### 2. 下载章节内容

下载章节正文内容，支持单章或全量下载。

```bash
# 下载指定章节
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47

# 下载所有章节
python -m crawler.chapter_parser --book-id 4519 --all-chapters

# 强制重新下载已存在的章节
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47 --force

# 显示浏览器窗口（调试用）
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47 --no-headless
```

**输出文件**：
- `data/chapters/{book_id}/{chapter_index}_title.txt` - 章节标题
- `data/chapters/{book_id}/{chapter_index}_content.md` - 章节内容（Markdown格式）

**功能说明**：
- ✅ 使用Selenium+WebDriver访问页面，等待JavaScript执行完成
- ✅ 等待页面动态重排序完成（检测`mark("mid")`标记）
- ✅ 支持多页章节合并（自动检测`_2.html`, `_3.html`等）
- ✅ 提取段落时保留段落之间的额外空行（`<br>`标签）
- ✅ 过滤广告和无效内容
- ✅ 生成Markdown格式的纯文本内容（移除HTML标签）
- ✅ 支持增量下载（跳过已存在的章节）

**注意事项**：
- 首次运行会自动下载Chrome驱动（可能需要一些时间）
- 如果遇到Cloudflare拦截，可能需要增加等待时间或使用非无头模式
- 章节下载速度较慢（每个页面需要等待JavaScript执行），请耐心等待

### 3. 检查下载进度

```bash
# 查看已下载的章节列表（需要手动编写脚本）
python3 << 'EOF'
from storage.chapter_storage import ChapterStorage
storage = ChapterStorage("4519")
chapters = storage.get_downloaded_chapters()
print(f"已下载 {len(chapters)} 个章节: {chapters}")
EOF
```

## 输出格式

### 书籍结构JSON (`data/books/{book_id}_structure.json`)

```json
{
    "name": "书籍名称",
    "author": "作者名称",
    "last_update": "2025-09-03",
    "latest_chapter": "最新章节名称",
    "book_id": "4519",
    "volumes": [
        {
            "volume_name": "第一卷",
            "front_page": "https://www.linovelib.com/novel/4519/volume/1",
            "cover_image": "https://...",
            "chapters": [
                {
                    "index": 1,
                    "title": "第一章",
                    "url": "https://www.linovelib.com/novel/4519/262081.html",
                    "needs_resolve": false
                },
                {
                    "index": 2,
                    "title": "第二章",
                    "url": "javascript:cid(0)",
                    "needs_resolve": true,
                    "original_url": "javascript:cid(0)"
                }
            ]
        }
    ]
}
```

### 章节内容格式

**标题文件** (`{chapter_index}_title.txt`):
```
第一章 标题
```

**内容文件** (`{chapter_index}_content.md`):
```markdown
段落1内容

段落2内容（前面有空行）

段落3内容
```

## 模块说明

### crawler/downloader.py

HTTP下载器，统一封装所有HTTP请求。

**功能**：
- 自动重试（指数退避）
- 全局限速（避免触发429错误）
- 随机User-Agent轮换
- Brotli/gzip/deflate解压
- 处理`Retry-After`响应头

**使用示例**：
```python
from crawler.downloader import Downloader

downloader = Downloader(base_url="https://www.linovelib.com")
html = downloader.download("/novel/4519/catalog")
```

### crawler/catalog_parser.py

目录页解析器，提取书籍信息和章节列表。

**功能**：
- 解析书籍基本信息（书名、作者、更新时间等）
- 解析卷信息和章节列表
- 处理异常链接（`javascript:cid(0)`）
- 自动调用特殊章节解析器补全URL
- 保存HTML副本用于调试

**使用示例**：
```python
from crawler.catalog_parser import CatalogParser

parser = CatalogParser()
structure = parser.parse_catalog(book_id="4519")
```

### crawler/special_chapter_resolver.py

特殊章节解析器，处理`javascript:cid(0)`链接。

**功能**：
- 通过上一章的多页导航推导下一章URL
- 解析`var nextpage="..."`变量
- 追踪章节ID变化以确定下一章URL

**使用示例**：
```python
from crawler.special_chapter_resolver import resolve_all_special_chapters
from crawler.downloader import Downloader

downloader = Downloader()
resolve_all_special_chapters(book_structure, downloader)
```

### crawler/chapter_parser.py

章节内容解析器，使用Selenium下载章节正文。

**功能**：
- 使用Selenium WebDriver访问页面
- 等待JavaScript执行和动态重排序完成
- 支持多页章节合并
- 提取段落并保留格式
- 生成Markdown格式内容

**使用示例**：
```python
from crawler.chapter_parser import ChapterParser

parser = ChapterParser(headless=True)
parser.parse_chapter(book_id="4519", chapter_index=47)
parser.close()
```

### crawler/reorder.py

动态页面内容提取工具。

**功能**：
- 从`#TextContent`中提取段落
- 过滤无效内容（广告、脚本等）
- 检测内容问题（段落数量、重复等）

**使用示例**：
```python
from crawler.reorder import extract_paragraphs, detect_content_issues

paragraphs = extract_paragraphs(html_content)
has_issues, issues = detect_content_issues(html_content)
```

### storage/chapter_storage.py

章节内容存储管理器。

**功能**：
- 保存和加载章节内容
- 检查章节是否已下载
- 获取已下载章节列表

**使用示例**：
```python
from storage.chapter_storage import ChapterStorage

storage = ChapterStorage("4519")
storage.save_chapter(1, "第一章", "内容...")
title, content = storage.load_chapter(1)
exists = storage.chapter_exists(1)
```

## 开发状态

- [x] ✅ HTTP下载器（downloader.py）
- [x] ✅ 目录页解析器（catalog_parser.py）
- [x] ✅ 特殊章节解析器（special_chapter_resolver.py）
- [x] ✅ 章节内容解析器（chapter_parser.py）
- [x] ✅ 动态页面内容提取工具（reorder.py）
- [x] ✅ 章节内容存储管理器（chapter_storage.py）
- [ ] ⏳ EPUB生成器（epub/，待实现）

## 常见问题

### 1. Chrome驱动下载失败

**问题**：首次运行时Chrome驱动下载失败。

**解决**：
- 检查网络连接
- 手动下载Chrome驱动并配置环境变量
- 或使用`--no-headless`模式查看详细错误信息

### 2. Cloudflare拦截

**问题**：访问页面时被Cloudflare拦截。

**解决**：
- 增加等待时间（修改`chapter_parser.py`中的等待时间）
- 使用非无头模式（`--no-headless`）
- 检查User-Agent设置

### 3. 章节内容顺序不正确

**问题**：下载的章节内容段落顺序不正确。

**解决**：
- 检查页面是否包含`mark("mid")`标记
- 增加等待时间，确保JavaScript完全执行
- 检查`reorder.py`的提取逻辑

### 4. 429 Too Many Requests

**问题**：频繁请求导致429错误。

**解决**：
- 增加`downloader.py`中的请求间隔时间
- 减少并发请求数量
- 使用更长的重试延迟

## 技术细节

### 反爬虫策略

1. **随机User-Agent**：每次请求随机选择不同的浏览器User-Agent
2. **请求限速**：相邻请求之间加入随机延迟（1-2秒）
3. **指数退避**：请求失败时按指数增加重试延迟
4. **Brotli解压**：支持Brotli压缩格式的内容解压
5. **Selenium反检测**：禁用自动化标识，模拟真实浏览器

### 动态页面处理

某些章节页面使用JavaScript动态加载和重排序内容：

1. **检测mark标记**：查找`mark("mid")`脚本标记
2. **等待重排序**：等待段落顺序稳定（最多25秒）
3. **验证顺序**：检查第一个段落是否符合预期顺序
4. **提取内容**：从重排序后的DOM中提取段落

### 特殊章节解析

对于`javascript:cid(0)`链接：

1. 找到上一章（需有有效URL）
2. 追踪上一章的多页导航（`var nextpage`）
3. 检测章节ID变化，确定下一章URL
4. 更新书籍结构中的URL

## 许可证

见 LICENSE 文件

## 贡献

欢迎提交Issue和Pull Request！
