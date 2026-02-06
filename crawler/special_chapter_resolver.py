"""特殊章节解析器（目录阶段 URL 补全）

用途：
    目录页中有部分章节的链接是 `javascript:cid(0)`，表示“站内占位链接 / 未公开链接”。
    这些章节在正文页面中仍然存在，只是目录不直接给出 URL。

    本模块在“目录阶段”通过 HTTP + HTML 解析，尝试为这些章节补出真实 URL，
    从而让后续正文爬取与 EPUB 生成阶段只面对“干净”的 URL 列表。

核心思路（基于 examples/pageUrls.txt 与示例章节 HTML）：

    对于目录中某个异常章节 A（url 为 javascript:cid(0)）：

    1. 在整本书结构中找到它的“上一章” B（需已存在有效 url，且 `needs_resolve=False`）。
    2. 使用 HTTP（通过 Downloader）依次请求 B 的第一页、第二页……：
       - 多页信息通常由 JS 变量 `var nextpage="..."` 控制；
       - 例如：`/novel/4519/262081.html` -> `/novel/4519/262081_2.html` -> `/novel/4519/262081_3.html`。
    3. 只要 `nextpage` 中的 chapter id 与 B 相同（262081），就继续视为“同一章的下一页”，继续追踪。
    4. 一旦 `nextpage` 的 chapter id 发生变化（例如从 262081* 变成 262082），
       就认为跳到了“下一章” A 的第一页，该 URL 即为 A 的真实 URL。
    5. 解析成功后，在目录结构中就地更新：
       - `chapter.url` 改为真实 URL；
       - `chapter.original_url = "javascript:cid(0)"`（保留原始信息）；
       - `chapter.needs_resolve = False`。

设计约束：
    - 不使用 Selenium，仅依赖纯 HTTP + HTML 解析；
    - 不下载正文，只负责“补 URL”；
    - 所有 HTTP 调用统一通过 Downloader，继承其节流、重试与 UA 策略；
    - 解析失败不会中断整个目录流程，只打印带前缀的日志，便于后续分析。
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .downloader import Downloader


NEXT_PAGE_VAR_PATTERN = re.compile(r'var\s+nextpage\s*=\s*"([^"]+)"')
CHAPTER_ID_PATTERN = re.compile(r"/novel/(\d+)/(\d+)(?:_\d+)?\.html")


def _extract_article_and_chapter(path_or_url: str) -> Optional[Tuple[str, str]]:
    """从路径或URL中提取 (article_id, chapter_id_base)。

    示例：
    - /novel/4519/262081.html      -> ("4519", "262081")
    - /novel/4519/262081_2.html    -> ("4519", "262081")
    - https://.../novel/4519/262081_3.html -> ("4519", "262081")
    """
    m = CHAPTER_ID_PATTERN.search(path_or_url)
    if not m:
        return None
    return m.group(1), m.group(2)


def _extract_nextpage_path(html: str) -> Optional[str]:
    """从章节 HTML 中提取 nextpage 路径（如果存在）。

    优先从 <script> 中查找 `var nextpage="..."`。
    退而求其次，可以考虑从分页导航中的“下一页”链接提取，但目前 examples
    显示 JS 变量足够使用。
    """
    soup = BeautifulSoup(html, "lxml")

    scripts_text = []
    for sc in soup.find_all("script"):
        t = sc.get_text() or ""
        if "nextpage" in t:
            scripts_text.append(t)

    if not scripts_text:
        return None

    joined = "\n".join(scripts_text)
    m = NEXT_PAGE_VAR_PATTERN.search(joined)
    if not m:
        return None
    return m.group(1)


def resolve_next_chapter_url(
    prev_chapter_url: str,
    downloader: Downloader,
    base_url: str = "https://www.linovelib.com",
    max_hops: int = 20,
) -> Optional[str]:
    """从上一章的多页导航中推导“下一章”的真实URL。

    Args:
        prev_chapter_url: 上一章第一页的 URL（可以是绝对或相对）
        downloader: 已配置好的 HTTP 下载器
        base_url: 站点基础 URL
        max_hops: 最多追踪多少次 nextpage，避免死循环

    Returns:
        下一章第一页的完整 URL，如果无法解析则返回 None。
    """
    # 解析上一章的 article_id 和 base chapter_id
    ids = _extract_article_and_chapter(prev_chapter_url)
    if not ids:
        print(f"[special_resolver] 无法从上一章URL中提取章节ID: {prev_chapter_url}")
        return None

    article_id, chapter_base = ids
    visited = set()

    # current_url 始终指向“当前页”的 URL（第一页 / 第二页 / ...）
    current_url = prev_chapter_url

    for _ in range(max_hops):
        full_url = current_url
        if not full_url.startswith("http"):
            full_url = urljoin(base_url, full_url)

        if full_url in visited:
            print(f"[special_resolver] 检测到循环，终止: {full_url}")
            return None
        visited.add(full_url)

        try:
            html = downloader.download(full_url)
        except Exception as e:
            print(f"[special_resolver] 下载上一章页面失败: {full_url}, 错误: {e}")
            return None

        next_path = _extract_nextpage_path(html)
        if not next_path:
            # 没有 nextpage，说明上一章本身已经没有“下一页 / 下一章”
            print(f"[special_resolver] 未找到 nextpage 变量: {full_url}")
            return None

        # 解析 nextpage 的章节ID
        ids2 = _extract_article_and_chapter(next_path)
        if not ids2:
            print(f"[special_resolver] 无法从 nextpage 中提取章节ID: {next_path}")
            return None

        article_id2, chapter2 = ids2
        if article_id2 != article_id:
            # 跨书籍了，不合理
            print(
                f"[special_resolver] nextpage 指向不同书籍: {next_path} "
                f"({article_id2} != {article_id})"
            )
            return None

        if chapter2 == chapter_base:
            # 仍然是同一章（不同分页），继续向后追踪
            current_url = next_path
            continue

        # chapter id 发生变化 => 认为跳到了“下一章”的第一页
        resolved = urljoin(base_url, next_path)
        print(
            f"[special_resolver] 解析到下一章URL: prev={prev_chapter_url} -> next={resolved}"
        )
        return resolved

    print(
        f"[special_resolver] 超过最大 hops({max_hops}) 仍未跳出当前章节: {prev_chapter_url}"
    )
    return None


def resolve_all_special_chapters(
    book_structure: Dict,
    downloader: Downloader,
    base_url: str = "https://www.linovelib.com",
) -> None:
    """在目录结构中解析所有 `needs_resolve == True` 的章节。

    就地修改 book_structure，不返回值。
    """
    volumes = book_structure.get("volumes") or []

    # 辅助函数：寻找 (vi, ci) 之前最近一个 needs_resolve == False 的章节
    def find_prev_normal_chapter(
        vol_idx: int, ch_idx: int
    ) -> Optional[Tuple[int, int, Dict]]:
        # 从当前卷向前，再从前面的卷向前
        for v in range(vol_idx, -1, -1):
            ch_list = volumes[v].get("chapters") or []
            start = ch_idx - 1 if v == vol_idx else len(ch_list) - 1
            for c in range(start, -1, -1):
                ch = ch_list[c]
                if not ch.get("needs_resolve"):
                    return v, c, ch
        return None

    for vi, vol in enumerate(volumes):
        chapters = vol.get("chapters") or []
        for ci, ch in enumerate(chapters):
            if not ch.get("needs_resolve"):
                continue

            # 查找上一章
            prev_info = find_prev_normal_chapter(vi, ci)
            if not prev_info:
                print(
                    f"[special_resolver] 无法为异常章节找到上一章: "
                    f"volume={vol.get('volume_name')}, title={ch.get('title')}"
                )
                continue

            _pv, _pc, prev_ch = prev_info
            prev_url = prev_ch.get("url")
            if not prev_url or prev_url == "javascript:cid(0)":
                print(
                    f"[special_resolver] 上一章URL无效，放弃解析: "
                    f"prev_title={prev_ch.get('title')}, prev_url={prev_url}"
                )
                continue

            resolved_url = resolve_next_chapter_url(
                prev_chapter_url=prev_url,
                downloader=downloader,
                base_url=base_url,
            )
            if not resolved_url:
                print(
                    f"[special_resolver] 未能解析异常章节URL: "
                    f"title={ch.get('title')}, 原始url={ch.get('url')}"
                )
                continue

            # 更新章节结构
            original_url = ch.get("url")
            ch["original_url"] = original_url
            ch["url"] = resolved_url
            ch["needs_resolve"] = False

            print(
                f"[special_resolver] 已更新章节URL: "
                f"title={ch.get('title')}, original={original_url}, resolved={resolved_url}"
            )

