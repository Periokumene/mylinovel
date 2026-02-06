# 轻小说爬虫EPUB生成工具

从linovelib.com爬取轻小说内容并生成EPUB电子书。

## 项目结构

```
mylinovel/
├── crawler/              # 爬虫模块
│   ├── catalog_parser.py    # 目录页解析器
│   ├── downloader.py        # HTTP下载器
│   └── ...
├── storage/              # 存储模块
├── epub/                 # EPUB生成模块
├── data/                 # 数据目录
│   ├── books/            # 书籍结构JSON
│   └── chapters/         # 章节内容
├── output/               # EPUB输出目录
└── test_catalog/         # 测试数据
```

## 安装依赖

```bash
# 如果使用虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 1. 解析目录页

```bash
# 使用书籍ID
python -m crawler.catalog_parser --book-id 4519

# 或使用完整URL
python -m crawler.catalog_parser --url https://www.linovelib.com/novel/4519/catalog
```

解析结果会保存到 `data/books/{book_id}_structure.json`

**注意**：运行时会自动保存HTML副本到 `data/books/{book_id}_catalog.html`，用于后续debug。

### 2. 测试目录页解析器（使用本地HTML文件）

```bash
python test_catalog_parser.py
```

## 目录页解析器功能

- ✅ 提取书籍基本信息（书名、作者、最后更新时间、最新章节）
- ✅ 提取卷信息（卷名、封面URL、封面图片）
- ✅ 提取章节列表（章节标题、URL、序号）
- ✅ 处理异常链接（`javascript:cid(0)`），标记为 `needs_resolve: true`
- ✅ 保存为JSON格式，符合 `book_structure.json` 规范

## 输出格式

```json
{
    "name": "书籍名称",
    "author": "作者名称",
    "last_update": "2025-09-03",
    "latest_chapter": "最新章节名称",
    "book_id": "4519",
    "volumes": [
        {
            "volume_name": "卷名",
            "front_page": "卷封面URL",
            "cover_image": "卷封面图片URL",
            "chapters": [
                {
                    "index": 1,
                    "title": "章节标题",
                    "url": "章节URL或javascript:cid(0)",
                    "needs_resolve": false
                }
            ]
        }
    ]
}
```

## 开发状态

- [x] 目录页解析器
- [ ] 章节内容解析器
- [ ] 特殊章节解析器（处理异常链接）
- [ ] EPUB生成器

## 许可证

见 LICENSE 文件
