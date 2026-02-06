"""目录页解析器，提取书籍信息和章节列表。

整体策略概述：

1. 使用 `Downloader` 下载目录 HTML，并保存一份本地副本到 `data/books/{book_id}_catalog.html`，
   便于后续 debug 与结构对比。
2. 使用 BeautifulSoup 解析：
   - 书籍基本信息：书名、作者、最后更新、最新章节；
   - 所有卷信息：通过 `div.volume.clearfix` 全局选择，兼容不同书籍的结构差异；
   - 章节列表：在每个卷下的 `ul.chapter-list.clearfix > li.col-4 > a` 中提取标题与 URL。
3. 对于 `href == "javascript:cid(0)"` 这样的异常链接，不跳过，按如下方式记录：
   - `url: "javascript:cid(0)"`；
   - `needs_resolve: true`（标记需特殊解析）。
4. 在构建出完整的 `book_structure` 之后，调用 `resolve_all_special_chapters`：
   - 利用“上一章多页导航 + var nextpage=\"...\"” 的规则，尝试在目录阶段就补全异常章节的真实 URL；
   - 补全成功后将 `needs_resolve` 置为 False，并保留 `original_url` 字段；
   - 补全失败则保留原状，只打印警告。

通过这种方式，后续的章节内容解析器与 EPUB 生成器都可以尽量在“干净”的
book_structure 上工作，而无需关心 `javascript:cid(0)` 这种站点内部占位链接。
"""

import json
import re
import os
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .downloader import Downloader
from .special_chapter_resolver import resolve_all_special_chapters


class ParseError(Exception):
    """解析错误"""
    pass


class CatalogParser:
    """目录页解析器"""
    
    BASE_URL = "https://www.linovelib.com"
    
    def __init__(self, base_url: str = BASE_URL):
        """
        初始化解析器
        
        Args:
            base_url: 网站基础URL
        """
        self.base_url = base_url
        self.downloader = Downloader(base_url=base_url)
    
    def parse_catalog(self, book_id: Optional[str] = None, 
                     catalog_url: Optional[str] = None) -> Dict:
        """
        解析目录页，返回书籍结构字典并保存到文件
        
        Args:
            book_id: 书籍ID（如"4519"）
            catalog_url: 目录页完整URL
        
        Returns:
            书籍结构字典
        
        Raises:
            ValueError: 如果book_id和catalog_url都未提供
            requests.RequestException: 如果HTTP请求失败
            ParseError: 如果HTML解析失败
        """
        # 1. 参数验证和URL构建
        if not book_id and not catalog_url:
            raise ValueError("必须提供book_id或catalog_url之一")
        
        if catalog_url:
            # 从URL中提取book_id
            match = re.search(r'/novel/(\d+)/catalog', catalog_url)
            if match:
                book_id = match.group(1)
            else:
                raise ValueError(f"无法从URL中提取book_id: {catalog_url}")
        else:
            catalog_url = f"{self.base_url}/novel/{book_id}/catalog"
        
        # 2. 下载HTML
        try:
            html_content = self.downloader.download(catalog_url)
            # 检查内容是否有效
            if not html_content or len(html_content) < 100:
                raise ParseError(f"下载的内容过短或为空，可能是错误页面")
            # 检查是否是HTML格式
            if not html_content.strip().startswith('<!'):
                # 可能是错误页面或重定向，尝试检查
                if 'error' in html_content.lower() or '403' in html_content or '404' in html_content:
                    raise ParseError(f"可能遇到错误页面，内容前100字符: {html_content[:100]}")
        except Exception as e:
            raise ParseError(f"下载目录页失败: {e}")
        
        # 2.1 保存HTML副本用于debug
        self._save_html_copy(book_id, html_content)
        
        # 3. 解析HTML
        try:
            soup = BeautifulSoup(html_content, 'lxml')
        except Exception as e:
            raise ParseError(f"HTML解析失败: {e}")
        
        # 4. 提取书籍基本信息
        book_info = self._extract_book_info(soup, book_id)
        
        # 5. 提取卷和章节信息
        volumes = self._extract_volumes(soup)
        
        # 6. 构建输出字典（先包含原始的 needs_resolve 标记）
        result = {
            "name": book_info["name"],
            "author": book_info.get("author"),
            "last_update": book_info.get("last_update"),
            "latest_chapter": book_info.get("latest_chapter"),
            "book_id": book_id,
            "volumes": volumes
        }
        
        # 6.1 在目录阶段解析特殊章节的真实URL（如果可能）
        try:
            resolve_all_special_chapters(
                book_structure=result,
                downloader=self.downloader,
                base_url=self.base_url,
            )
        except Exception as e:
            # 不让特殊解析器的错误中断整个目录解析流程
            print(f"警告: 解析特殊章节URL时出错: {e}")
        
        # 7. 保存到文件
        self._save_structure(book_id, result)
        
        return result
    
    def _extract_book_info(self, soup: BeautifulSoup, book_id: str) -> Dict:
        """提取书籍基本信息"""
        book_info = {}
        
        # 提取书名
        try:
            h1 = soup.select_one('div.book-meta > h1')
            if h1:
                book_info["name"] = h1.get_text(strip=True)
            else:
                # 尝试其他可能的选择器
                h1 = soup.select_one('h1')
                if h1:
                    book_info["name"] = h1.get_text(strip=True)
                else:
                    # 调试：打印页面标题
                    title_tag = soup.find('title')
                    title_text = title_tag.get_text(strip=True) if title_tag else "无标题"
                    raise ParseError(f"无法找到书名。页面标题: {title_text}。请检查HTML结构或网站是否返回了错误页面。")
        except ParseError:
            raise
        except Exception as e:
            raise ParseError(f"提取书名失败: {e}")
        
        # 提取作者
        try:
            spans = soup.select('div.book-meta > p > span')
            for span in spans:
                text = span.get_text()
                if '作者：' in text:
                    author_link = span.find('a')
                    if author_link:
                        book_info["author"] = author_link.get_text(strip=True)
                    break
        except Exception as e:
            print(f"警告: 提取作者失败: {e}")
        
        # 提取最后更新时间
        try:
            spans = soup.select('div.book-meta > p > span')
            for span in spans:
                text = span.get_text()
                if '最后更新：' in text:
                    # 提取日期部分
                    match = re.search(r'最后更新：(\d{4}-\d{2}-\d{2})', text)
                    if match:
                        book_info["last_update"] = match.group(1)
                    break
        except Exception as e:
            print(f"警告: 提取最后更新时间失败: {e}")
        
        # 提取最新章节
        try:
            spans = soup.select('div.book-meta > p > span')
            for span in spans:
                text = span.get_text()
                if '最新章节：' in text:
                    # 提取章节名称
                    match = re.search(r'最新章节：(.+)', text)
                    if match:
                        book_info["latest_chapter"] = match.group(1).strip()
                    break
        except Exception as e:
            print(f"警告: 提取最新章节失败: {e}")
        
        return book_info
    
    def _extract_volumes(self, soup: BeautifulSoup) -> list:
        """提取卷和章节信息

        注意：不同书籍的HTML结构略有差异：
        - 有的书籍中，所有卷的 div.volume 都包在 div#volume-list 里面
        - 有的书籍（如4519）中，div#volume-list 里只有一个“消息通知”的 li，
          后面的 div.volume 全部是它的兄弟节点，而不是子节点

        因此，这里统一直接选择页面中的所有 div.volume.clearfix，而不是限定在 #volume-list 下，
        再根据是否有章节列表进行过滤。
        """
        volumes = []
        # 原来是：'#volume-list > div.volume.clearfix'
        # 为兼容4519等结构，这里改为全局选择
        volume_divs = soup.select('div.volume.clearfix')
        
        global_chapter_index = 1
        
        for volume_div in volume_divs:
            volume = {}
            
            # 提取卷名
            try:
                h2 = volume_div.select_one('h2.v-line')
                if h2:
                    volume["volume_name"] = h2.get_text(strip=True)
                else:
                    print(f"警告: 无法找到卷名，跳过该卷")
                    continue
            except Exception as e:
                print(f"警告: 提取卷名失败: {e}")
                continue
            
            # 提取卷封面URL
            try:
                cover_link = volume_div.select_one('a.volume-cover')
                if cover_link and cover_link.get('href'):
                    href = cover_link.get('href')
                    volume["front_page"] = urljoin(self.base_url, href)
                else:
                    volume["front_page"] = None
            except Exception as e:
                print(f"警告: 提取卷封面URL失败: {e}")
                volume["front_page"] = None
            
            # 提取卷封面图片URL（可选）
            try:
                img = volume_div.select_one('a.volume-cover > img')
                if img:
                    # 优先使用data-original（懒加载）
                    cover_image = img.get('data-original') or img.get('src')
                    if cover_image:
                        volume["cover_image"] = cover_image
            except Exception as e:
                print(f"警告: 提取卷封面图片失败: {e}")
            
            # 提取章节列表
            chapters = []
            try:
                chapter_links = volume_div.select('ul.chapter-list.clearfix > li.col-4 > a')
                
                for link in chapter_links:
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    # 判断是否为异常链接
                    needs_resolve = (href == 'javascript:cid(0)')
                    
                    if needs_resolve:
                        # 异常链接：保持原样
                        chapter_url = href
                    else:
                        # 正常链接：转换为完整URL
                        try:
                            chapter_url = urljoin(self.base_url, href)
                        except Exception as e:
                            print(f"警告: URL转换失败 ({href}): {e}，跳过该章节")
                            continue
                    
                    chapters.append({
                        "index": global_chapter_index,
                        "title": title,
                        "url": chapter_url,
                        "needs_resolve": needs_resolve
                    })
                    global_chapter_index += 1
            except Exception as e:
                print(f"警告: 提取章节列表失败: {e}")
            
            if chapters:  # 只添加有章节的卷
                volume["chapters"] = chapters
                volumes.append(volume)
        
        return volumes
    
    def _save_html_copy(self, book_id: str, html_content: str):
        """保存HTML副本用于debug"""
        os.makedirs('data/books', exist_ok=True)
        html_file_path = f'data/books/{book_id}_catalog.html'
        
        try:
            # 确保内容是字符串类型
            if isinstance(html_content, bytes):
                # 如果是bytes，尝试解码
                try:
                    html_content = html_content.decode('utf-8')
                except UnicodeDecodeError:
                    html_content = html_content.decode('utf-8', errors='replace')
            
            # 确保是字符串
            if not isinstance(html_content, str):
                raise ValueError(f"html_content类型错误: {type(html_content)}")
            
            with open(html_file_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(html_content)
            print(f"HTML副本已保存到: {html_file_path} ({len(html_content)} 字符)")
        except Exception as e:
            print(f"警告: 保存HTML副本失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_structure(self, book_id: str, structure: Dict):
        """保存书籍结构到文件"""
        os.makedirs('data/books', exist_ok=True)
        file_path = f'data/books/{book_id}_structure.json'
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(structure, f, ensure_ascii=False, indent=4)
            print(f"书籍结构已保存到: {file_path}")
        except Exception as e:
            print(f"警告: 保存文件失败: {e}")
    
    def close(self):
        """关闭下载器"""
        self.downloader.close()


def parse_catalog(book_id: Optional[str] = None, 
                  catalog_url: Optional[str] = None) -> Dict:
    """
    解析目录页的便捷函数
    
    Args:
        book_id: 书籍ID
        catalog_url: 目录页URL
    
    Returns:
        书籍结构字典
    """
    parser = CatalogParser()
    try:
        return parser.parse_catalog(book_id=book_id, catalog_url=catalog_url)
    finally:
        parser.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='解析目录页')
    parser.add_argument('--book-id', type=str, help='书籍ID')
    parser.add_argument('--url', type=str, help='目录页URL')
    
    args = parser.parse_args()
    
    # 参数验证
    if not args.book_id and not args.url:
        parser.error("必须提供 --book-id 或 --url 之一")
    
    try:
        result = parse_catalog(book_id=args.book_id, catalog_url=args.url)
        print(f"\n解析成功！")
        print(f"书名: {result['name']}")
        print(f"作者: {result.get('author', '未知')}")
        print(f"卷数: {len(result['volumes'])}")
        total_chapters = sum(len(v['chapters']) for v in result['volumes'])
        print(f"章节数: {total_chapters}")
        needs_resolve_count = sum(
            sum(1 for ch in v['chapters'] if ch.get('needs_resolve'))
            for v in result['volumes']
        )
        if needs_resolve_count > 0:
            print(f"需要解析的异常链接: {needs_resolve_count}")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
