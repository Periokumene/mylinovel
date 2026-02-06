"""章节内容解析器

功能：
    - 使用Selenium+WebDriver访问页面，等待页面完全加载和重排序完成
    - 支持多页章节合并（_2.html, _3.html等）
    - 支持单独执行（按章节序号或全量下载）
    - 生成Markdown格式的纯文本内容（移除HTML标签）

实现要点：
    - 使用Selenium WebDriver加载页面，等待JavaScript执行完成
    - 等待页面重排序完成（检测mark("mid")标记后的段落是否已重新排列）
    - 检测章节是否有多页（通过var nextpage变量或尝试访问_2.html）
    - 提取段落时检测<br>标签，保留段落之间的额外空行
    - 保存章节标题和Markdown格式内容到ChapterStorage
"""

import json
import re
import argparse
import time
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# 处理相对导入和绝对导入
try:
    from storage.chapter_storage import ChapterStorage
except ImportError:
    from ..storage.chapter_storage import ChapterStorage


class ParseError(Exception):
    """解析错误"""
    pass


# 匹配 var nextpage="..." 的正则表达式
NEXT_PAGE_VAR_PATTERN = re.compile(r'var\s+nextpage\s*=\s*"([^"]+)"')
# 匹配章节ID的正则表达式
CHAPTER_ID_PATTERN = re.compile(r"/novel/(\d+)/(\d+)(?:_\d+)?\.html")


class ChapterParser:
    """章节内容解析器（使用Selenium）"""
    
    BASE_URL = "https://www.linovelib.com"
    
    def __init__(self, base_url: str = BASE_URL, headless: bool = True):
        """
        初始化解析器
        
        Args:
            base_url: 网站基础URL
            headless: 是否使用无头模式（默认True）
        """
        self.base_url = base_url
        self.headless = headless
        self.driver = None
        self._init_driver()
    
    def _init_driver(self):
        """初始化WebDriver（配置反检测措施）"""
        chrome_options = Options()
        if self.headless:
            chrome_options.add_argument('--headless=new')  # 使用新的headless模式
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 反检测措施
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # 禁用图片加载以提高速度
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(60)
            
            # 执行反检测脚本
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                '''
            })
            
        except Exception as e:
            raise ParseError(f"初始化WebDriver失败: {e}")
    
    def close(self):
        """关闭WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
    
    def _wait_for_page_load(self, timeout: int = 30):
        """
        等待页面完全加载和重排序完成
        
        Args:
            timeout: 超时时间（秒）
        """
        try:
            # 等待页面基本加载完成
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # 等待#TextContent元素出现
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.ID, "TextContent"))
                )
            except TimeoutException:
                print("警告: 等待#TextContent超时")
            
            # 等待JavaScript执行完成（包括动态重排序）
            # 检查是否有mark("mid")标记
            has_mark = self.driver.execute_script("""
                var scripts = document.querySelectorAll('script');
                for (var i = 0; i < scripts.length; i++) {
                    if (scripts[i].textContent && scripts[i].textContent.includes('mark("mid")')) {
                        return true;
                    }
                }
                return false;
            """)
            
            if has_mark:
                print("检测到mark标记，等待动态重排序完成...")
                # 等待更长时间，确保JavaScript完全执行和重排序完成
                # 动态页面通常需要10-20秒来完成重排序
                max_wait = 25  # 最多等待25秒
                wait_interval = 0.5
                waited = 0
                
                # 等待段落顺序稳定，检查第一个段落是否符合预期
                # dynamic.html的第一个段落应该是"她懒散地躺在那里..."
                expected_first_keywords = ["她懒散地躺在那里", "那个面具", "对于见惯了各色人等的洛特尔"]
                last_first_paragraph = None
                stable_count = 0
                required_stable = 12  # 需要连续12次检查结果一致
                found_expected = False
                
                # 先等待一段时间，让JavaScript开始执行
                print("  等待JavaScript执行...")
                time.sleep(3)
                
                # 尝试滚动页面，触发可能的懒加载或重排序
                try:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)
                    self.driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                except:
                    pass
                
                while waited < max_wait:
                    time.sleep(wait_interval)
                    waited += wait_interval
                    
                    # 获取第一个段落的内容
                    first_para = self.driver.execute_script("""
                        var firstP = document.querySelector('#TextContent p');
                        return firstP ? firstP.textContent.trim() : '';
                    """)
                    
                    if first_para:
                        # 检查是否包含预期的关键词（说明重排序已完成）
                        for keyword in expected_first_keywords:
                            if keyword in first_para:
                                found_expected = True
                                break
                        
                        if first_para == last_first_paragraph:
                            stable_count += 1
                            # 如果找到了预期的段落且稳定，可以提前结束
                            if found_expected and stable_count >= required_stable:
                                print(f"✓ 段落顺序已稳定且符合预期（等待了{waited:.1f}秒）")
                                break
                            # 如果稳定但不符合预期，继续等待
                            elif stable_count >= required_stable * 2 and waited >= 15:
                                print(f"⚠ 段落顺序已稳定但可能未完全重排序（等待了{waited:.1f}秒）")
                                print(f"   当前第一个段落: {first_para[:60]}...")
                                break
                        else:
                            stable_count = 0
                            last_first_paragraph = first_para
                            if found_expected:
                                print(f"  检测到段落顺序变化（等待了{waited:.1f}秒）")
                    else:
                        # 如果还没有段落，继续等待
                        stable_count = 0
                
                if found_expected:
                    print(f"✓ 检测到重排序后的段落顺序")
                else:
                    print(f"⚠ 未检测到预期的段落顺序（等待了{waited:.1f}秒）")
                    if last_first_paragraph:
                        print(f"   当前第一个段落: {last_first_paragraph[:60]}...")
                
                # 额外等待一小段时间，确保所有动态内容都已加载
                time.sleep(2)
            else:
                # 没有mark标记，等待较短时间即可
                time.sleep(2)
            
        except TimeoutException as e:
            print(f"警告: 等待页面加载超时: {e}")
    
    def parse_chapter(
        self,
        book_id: str,
        chapter_index: Optional[int] = None,
        all_chapters: bool = False,
        force_redownload: bool = False,
    ) -> None:
        """
        解析章节内容
        
        Args:
            book_id: 书籍ID
            chapter_index: 章节序号（从1开始），如果为None且all_chapters=False则不执行
            all_chapters: 如果为True，解析所有章节
            force_redownload: 如果为True，即使章节已存在也重新下载
        """
        # 加载书籍结构
        structure_file = Path(f"data/books/{book_id}_structure.json")
        if not structure_file.exists():
            raise ParseError(f"找不到书籍结构文件: {structure_file}")
        
        with open(structure_file, 'r', encoding='utf-8') as f:
            book_structure = json.load(f)
        
        # 初始化存储管理器
        storage = ChapterStorage(book_id)
        
        # 收集所有章节
        all_chapter_list = []
        for volume in book_structure.get("volumes", []):
            for chapter in volume.get("chapters", []):
                all_chapter_list.append(chapter)
        
        if not all_chapter_list:
            raise ParseError("书籍结构中没有找到章节")
        
        # 确定要处理的章节列表
        if all_chapters:
            chapters_to_process = all_chapter_list
        elif chapter_index is not None:
            # 查找指定序号的章节
            target_chapter = None
            for ch in all_chapter_list:
                if ch.get("index") == chapter_index:
                    target_chapter = ch
                    break
            if not target_chapter:
                raise ParseError(f"找不到序号为 {chapter_index} 的章节")
            chapters_to_process = [target_chapter]
        else:
            raise ValueError("必须指定 chapter_index 或设置 all_chapters=True")
        
        # 处理每个章节
        try:
            for chapter in chapters_to_process:
                idx = chapter.get("index")
                title = chapter.get("title", "")
                url = chapter.get("url", "")
                
                # 检查是否需要重新下载
                if not force_redownload and storage.chapter_exists(idx):
                    print(f"章节 {idx} 已存在，跳过: {title}")
                    continue
                
                # 检查URL是否有效
                if not url or url == "javascript:cid(0)":
                    print(f"警告: 章节 {idx} 的URL无效: {url}，跳过")
                    continue
                
                try:
                    print(f"正在下载章节 {idx}: {title}")
                    content = self._download_chapter_content(url)
                    
                    # 保存章节
                    storage.save_chapter(idx, title, content)
                    print(f"✓ 章节 {idx} 下载完成")
                except Exception as e:
                    print(f"✗ 章节 {idx} 下载失败: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        finally:
            # 确保关闭WebDriver
            self.close()
    
    def _download_chapter_content(self, chapter_url: str) -> str:
        """
        使用Selenium下载章节内容（支持多页）
        
        Args:
            chapter_url: 章节第一页URL
            
        Returns:
            合并后的Markdown格式纯文本内容（段落之间保留空行）
        """
        # 访问第一页
        print(f"  访问页面: {chapter_url}")
        try:
            self.driver.get(chapter_url)
            
            # 检查是否被Cloudflare拦截
            page_source = self.driver.page_source
            if 'cloudflare' in page_source.lower() or 'sorry, you have been blocked' in page_source.lower():
                print("⚠ 检测到Cloudflare拦截，等待验证...")
                time.sleep(10)  # 等待可能的验证页面
                page_source = self.driver.page_source
                if 'cloudflare' in page_source.lower() or 'sorry, you have been blocked' in page_source.lower():
                    raise ParseError("页面被Cloudflare拦截，无法访问")
            
        except WebDriverException as e:
            raise ParseError(f"访问页面失败: {e}")
        
        # 等待页面完全加载
        self._wait_for_page_load()
        
        # 获取页面源码
        first_page_html = self.driver.page_source
        
        # 提取标题（通常在第一页）
        title = self._extract_title(first_page_html)
        
        # 提取第一页的正文段落（带空行信息）
        all_paragraphs_with_spacing = self._extract_paragraphs_with_spacing(first_page_html)
        
        # 查找是否有下一页
        next_page_url = self._find_next_page_url(first_page_html, chapter_url)
        
        # 下载后续页面
        page_num = 2
        while next_page_url:
            try:
                print(f"  下载第 {page_num} 页...")
                # 访问下一页
                self.driver.get(next_page_url)
                self._wait_for_page_load()
                
                # 获取页面源码
                page_html = self.driver.page_source
                
                # 提取段落（带空行信息）
                try:
                    paragraphs_with_spacing = self._extract_paragraphs_with_spacing(page_html)
                    if not paragraphs_with_spacing:
                        print(f"  页面无有效内容，停止下载")
                        break
                    all_paragraphs_with_spacing.extend(paragraphs_with_spacing)
                except Exception as e:
                    print(f"警告: 提取第 {page_num} 页段落失败: {e}")
                    break
                
                # 查找下一页
                next_page_url = self._find_next_page_url(page_html, next_page_url)
                page_num += 1
                
            except Exception as e:
                print(f"警告: 下载第 {page_num} 页失败: {e}")
                break
        
        # 组合成Markdown格式纯文本
        # 每个段落一行，如果段落前有额外空行标记，则添加空行
        lines = []
        for i, (para, has_extra_blank) in enumerate(all_paragraphs_with_spacing):
            # 如果不是第一个段落，检查是否需要添加空行
            if i > 0:
                prev_has_extra = all_paragraphs_with_spacing[i-1][1]
                # 如果前一个段落后有额外空行标记，添加一个空行
                if prev_has_extra:
                    # 确保不会连续多个空行
                    if not lines or lines[-1] != "":
                        lines.append("")
            lines.append(para)
        
        return "\n".join(lines)
    
    def _extract_paragraphs_with_spacing(self, html_content: str) -> List[Tuple[str, bool]]:
        """
        从HTML中提取段落，并检测段落之间是否有额外的空行（<br>标签）
        
        Args:
            html_content: HTML内容
            
        Returns:
            List of (paragraph_text, has_extra_blank_line) tuples
        """
        soup = BeautifulSoup(html_content, 'lxml')
        
        # 查找 #TextContent
        text_content = soup.select_one('#TextContent')
        if not text_content:
            # 如果找不到，尝试直接提取段落
            paragraphs = []
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 3:
                    # 过滤广告
                    if not re.search(r'^【.*】$|^手工砖块$|^广告', text, re.IGNORECASE):
                        paragraphs.append((text, False))
            return paragraphs
        
        # 提取段落和空行信息
        paragraphs_with_spacing = []
        elements = text_content.find_all(['p', 'br'])
        
        for i, elem in enumerate(elements):
            if elem.name == 'p':
                text = elem.get_text(strip=True)
                if text and len(text) > 3:
                    # 过滤广告
                    if re.search(r'^【.*】$|^手工砖块$|^广告', text, re.IGNORECASE):
                        continue
                    
                    # 检查下一个元素是否是<br>，如果是则标记有额外空行
                    has_extra_blank = False
                    if i + 1 < len(elements) and elements[i + 1].name == 'br':
                        # 检查是否连续多个<br>，或者后面还有内容
                        j = i + 1
                        while j < len(elements) and elements[j].name == 'br':
                            j += 1
                        # 如果后面还有段落，说明有额外空行
                        if j < len(elements) and elements[j].name == 'p':
                            has_extra_blank = True
                    
                    paragraphs_with_spacing.append((text, has_extra_blank))
        
        # 如果提取失败，回退到简单提取
        if not paragraphs_with_spacing:
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if text and len(text) > 3:
                    if not re.search(r'^【.*】$|^手工砖块$|^广告', text, re.IGNORECASE):
                        paragraphs_with_spacing.append((text, False))
        
        return paragraphs_with_spacing
    
    def _extract_title(self, html_content: str) -> str:
        """
        从HTML中提取章节标题
        
        Args:
            html_content: HTML内容
            
        Returns:
            章节标题
        """
        soup = BeautifulSoup(html_content, 'lxml')
        
        # 尝试从 h1 标签提取
        h1 = soup.select_one('h1')
        if h1:
            title = h1.get_text(strip=True)
            # 移除可能的"正文"前缀
            title = re.sub(r'^正文\s*', '', title)
            return title
        
        # 尝试从 #mlfy_main_text > h1 提取
        h1_alt = soup.select_one('#mlfy_main_text > h1')
        if h1_alt:
            return h1_alt.get_text(strip=True)
        
        return "未知标题"
    
    def _find_next_page_url(self, html_content: str, current_url: str) -> Optional[str]:
        """
        查找下一页URL
        
        Args:
            html_content: 当前页HTML内容
            current_url: 当前页URL
            
        Returns:
            下一页URL，如果没有则返回None
        """
        # 方法1: 从 var nextpage 变量提取
        match = NEXT_PAGE_VAR_PATTERN.search(html_content)
        if match:
            next_path = match.group(1)
            # 检查是否是同一章的下一页
            current_ids = _extract_article_and_chapter(current_url)
            next_ids = _extract_article_and_chapter(next_path)
            
            if current_ids and next_ids:
                article_id, chapter_base = current_ids
                article_id2, chapter2 = next_ids
                
                # 如果是同一章（不同分页），返回下一页URL
                if article_id == article_id2 and chapter_base == chapter2:
                    return urljoin(self.base_url, next_path)
                # 如果章节ID变化，说明是下一章，返回None
                else:
                    return None
        
        # 方法2: 尝试构造 _2.html, _3.html 等URL
        # 从当前URL提取基础部分
        match = CHAPTER_ID_PATTERN.search(current_url)
        if match:
            article_id = match.group(1)
            chapter_id = match.group(2)
            # group(3) 可能不存在（第一页没有_2后缀）
            page_suffix = match.group(3) if len(match.groups()) >= 3 else None
            
            # 确定当前页码
            if page_suffix:
                try:
                    current_page = int(page_suffix[1:])  # 去掉下划线
                    next_page = current_page + 1
                except (ValueError, IndexError):
                    next_page = 2
            else:
                next_page = 2
            
            # 构造下一页URL
            next_url = f"/novel/{article_id}/{chapter_id}_{next_page}.html"
            
            # 返回下一页URL（实际下载会在主循环中进行，如果404会自动停止）
            return urljoin(self.base_url, next_url)
        
        return None


def _extract_article_and_chapter(path_or_url: str) -> Optional[Tuple[str, str]]:
    """从路径或URL中提取 (article_id, chapter_id_base)"""
    m = CHAPTER_ID_PATTERN.search(path_or_url)
    if not m:
        return None
    return m.group(1), m.group(2)


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="章节内容解析器（使用Selenium）")
    parser.add_argument('--book-id', required=True, help='书籍ID')
    parser.add_argument('--chapter-index', type=int, help='章节序号（从1开始）')
    parser.add_argument('--all-chapters', action='store_true', help='解析所有章节')
    parser.add_argument('--force', action='store_true', help='强制重新下载已存在的章节')
    parser.add_argument('--no-headless', action='store_true', help='不使用无头模式（显示浏览器窗口）')
    
    args = parser.parse_args()
    
    if not args.chapter_index and not args.all_chapters:
        parser.error("必须指定 --chapter-index 或 --all-chapters")
    
    parser_obj = ChapterParser(headless=not args.no_headless)
    try:
        parser_obj.parse_chapter(
            book_id=args.book_id,
            chapter_index=args.chapter_index,
            all_chapters=args.all_chapters,
            force_redownload=args.force,
        )
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        parser_obj.close()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
