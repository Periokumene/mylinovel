# 使用指南

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 完整流程示例

以书籍ID `4519` 为例：

#### 步骤1: 解析目录页

```bash
python -m crawler.catalog_parser --book-id 4519
```

**输出**：
- `data/books/4519_structure.json` - 书籍结构
- `data/books/4519_catalog.html` - HTML副本

**检查结果**：
```bash
cat data/books/4519_structure.json | python -m json.tool | head -30
```

#### 步骤2: 下载章节内容

```bash
# 下载单个章节（测试用）
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47

# 下载所有章节（耗时较长）
python -m crawler.chapter_parser --book-id 4519 --all-chapters
```

**输出**：
- `data/chapters/4519/47_title.txt` - 章节标题
- `data/chapters/4519/47_content.md` - 章节内容

**检查结果**：
```bash
# 查看章节标题
cat data/chapters/4519/47_title.txt

# 查看章节内容（前20行）
head -20 data/chapters/4519/47_content.md

# 查看章节内容（后20行）
tail -20 data/chapters/4519/47_content.md
```

#### 步骤3: 检查下载进度

```bash
python3 << 'EOF'
from storage.chapter_storage import ChapterStorage
import json

# 加载书籍结构
with open('data/books/4519_structure.json', 'r', encoding='utf-8') as f:
    structure = json.load(f)

# 统计章节总数
total_chapters = sum(len(v['chapters']) for v in structure['volumes'])
print(f"总章节数: {total_chapters}")

# 检查已下载章节
storage = ChapterStorage("4519")
downloaded = storage.get_downloaded_chapters()
print(f"已下载章节数: {len(downloaded)}")
print(f"下载进度: {len(downloaded)}/{total_chapters} ({len(downloaded)/total_chapters*100:.1f}%)")

# 显示已下载的章节列表
if downloaded:
    print(f"\n已下载章节: {downloaded[:10]}{'...' if len(downloaded) > 10 else ''}")
EOF
```

## 命令行参数说明

### catalog_parser.py

```bash
python -m crawler.catalog_parser [选项]

选项:
  --book-id TEXT     书籍ID（如：4519）
  --url TEXT         目录页完整URL
```

**示例**：
```bash
# 使用书籍ID
python -m crawler.catalog_parser --book-id 4519

# 使用完整URL
python -m crawler.catalog_parser --url https://www.linovelib.com/novel/4519/catalog
```

### chapter_parser.py

```bash
python -m crawler.chapter_parser [选项]

必需选项:
  --book-id TEXT          书籍ID

章节选择（二选一）:
  --chapter-index INT     章节序号（从1开始）
  --all-chapters          下载所有章节

其他选项:
  --force                 强制重新下载已存在的章节
  --no-headless           不使用无头模式（显示浏览器窗口，用于调试）
```

**示例**：
```bash
# 下载单个章节
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47

# 下载所有章节
python -m crawler.chapter_parser --book-id 4519 --all-chapters

# 强制重新下载
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47 --force

# 显示浏览器窗口（调试用）
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47 --no-headless
```

## 常见使用场景

### 场景1: 下载新书

```bash
# 1. 解析目录
python -m crawler.catalog_parser --book-id 5027

# 2. 测试下载第一章
python -m crawler.chapter_parser --book-id 5027 --chapter-index 1

# 3. 确认无误后下载全部
python -m crawler.chapter_parser --book-id 5027 --all-chapters
```

### 场景2: 增量下载

```bash
# 只下载未下载的章节（默认行为）
python -m crawler.chapter_parser --book-id 4519 --all-chapters

# 如果某些章节下载失败，可以单独重新下载
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47 --force
```

### 场景3: 调试问题章节

```bash
# 使用非无头模式查看浏览器行为
python -m crawler.chapter_parser --book-id 4519 --chapter-index 47 --no-headless

# 检查下载的内容
cat data/chapters/4519/47_content.md | head -50
```

## 数据文件说明

### 书籍结构文件 (`data/books/{book_id}_structure.json`)

包含书籍的完整结构信息：
- 书籍基本信息（名称、作者、更新时间等）
- 卷信息（卷名、封面等）
- 章节列表（标题、URL、序号等）

**字段说明**：
- `needs_resolve`: `true` 表示URL为 `javascript:cid(0)`，需要特殊解析
- `original_url`: 原始URL（如果被解析过）
- `index`: 章节序号（全局唯一，从1开始）

### 章节内容文件

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

## 故障排除

### 问题1: Chrome驱动下载失败

**症状**：首次运行时提示Chrome驱动下载失败

**解决**：
1. 检查网络连接
2. 手动下载Chrome驱动并配置环境变量
3. 或使用 `--no-headless` 查看详细错误

### 问题2: Cloudflare拦截

**症状**：访问页面时被Cloudflare拦截

**解决**：
1. 使用 `--no-headless` 模式，手动完成验证
2. 增加等待时间（修改代码中的等待时间）
3. 检查User-Agent设置

### 问题3: 章节内容顺序不正确

**症状**：下载的章节段落顺序混乱

**解决**：
1. 检查页面是否包含 `mark("mid")` 标记
2. 增加等待时间（修改 `_wait_for_page_load` 中的等待时间）
3. 使用 `--no-headless` 观察页面加载过程

### 问题4: 429 Too Many Requests

**症状**：频繁出现429错误

**解决**：
1. 增加请求间隔（修改 `downloader.py` 中的 `base_interval`）
2. 减少并发请求
3. 等待一段时间后重试

### 问题5: 特殊章节URL解析失败

**症状**：某些章节的URL仍为 `javascript:cid(0)`

**解决**：
1. 检查上一章是否有有效URL
2. 检查上一章是否有多页导航
3. 查看日志中的 `[special_resolver]` 信息

## 性能优化建议

1. **批量下载**：使用 `--all-chapters` 一次性下载所有章节，避免重复初始化WebDriver
2. **增量下载**：默认跳过已存在的章节，支持断点续传
3. **请求限速**：已内置请求限速，避免触发反爬虫机制
4. **无头模式**：默认使用无头模式，减少资源消耗

## 下一步

完成章节下载后，可以使用EPUB生成器（待实现）将章节内容转换为EPUB电子书。
