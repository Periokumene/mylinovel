"""动态页面内容重排序工具

用途：
    处理JavaScript动态加载的章节页面，提取和清理正文内容。
    某些章节页面可能因为动态加载导致段落顺序异常或内容缺失，
    本模块负责从HTML中提取段落并清理无效内容。

核心功能：
    1. 从 #TextContent 中提取所有段落
    2. 过滤无效段落（广告、脚本标记等）
    3. 返回清理后的段落列表

注意：
    本模块不进行段落重排序（重排序需要参考顺序，在实际爬虫中通常不可用）。
    如果页面内容确实乱序，可能需要其他策略或手动处理。
"""

import re
from html.parser import HTMLParser
from typing import List, Tuple, Optional


class ParagraphExtractor(HTMLParser):
    """HTML解析器，用于从 #TextContent 中提取段落"""
    
    def __init__(self):
        super().__init__()
        self.paragraphs: List[Tuple[str, int]] = []
        self.in_text_content = False
        self.current_text = ""
        self.in_p_tag = False
        self.depth = 0
    
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        """处理开始标签"""
        if tag == 'div':
            # 检查是否是 TextContent
            for attr_name, attr_value in attrs:
                if attr_name == 'id' and attr_value == 'TextContent':
                    self.in_text_content = True
                    self.depth += 1
                    return
            if self.in_text_content:
                self.depth += 1
        elif tag == 'p' and self.in_text_content:
            self.in_p_tag = True
            self.current_text = ""
    
    def handle_endtag(self, tag: str):
        """处理结束标签"""
        if tag == 'div' and self.in_text_content:
            self.depth -= 1
            if self.depth == 0:
                self.in_text_content = False
        elif tag == 'p' and self.in_p_tag:
            text = self.current_text.strip()
            if text and _is_valid_paragraph(text):
                self.paragraphs.append((text, len(self.paragraphs)))
            self.in_p_tag = False
            self.current_text = ""
    
    def handle_data(self, data: str):
        """处理文本数据"""
        if self.in_p_tag:
            self.current_text += data


def _is_valid_paragraph(text: str) -> bool:
    """判断是否为有效的段落文本"""
    invalid_patterns = [
        r'^【.*】$',  # 【新成品】
        r'^手工砖块$',
        r'^广告',
        r'google',
        r'adsbygoogle',
        r'^【.*】',  # 其他广告标记
    ]
    
    for pattern in invalid_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False
    
    # 过滤过短的文本
    if len(text) < 3:
        return False
    
    return True


def extract_paragraphs(html_content: str) -> List[str]:
    """
    从HTML内容中提取段落
    
    Args:
        html_content: HTML内容字符串
    
    Returns:
        段落文本列表（按HTML中的出现顺序）
    
    Raises:
        ValueError: 如果无法从 #TextContent 中提取段落
    """
    parser = ParagraphExtractor()
    parser.feed(html_content)
    
    if not parser.paragraphs:
        raise ValueError("无法从 #TextContent 中提取段落")
    
    # 只返回文本，不返回索引
    return [text for text, _ in parser.paragraphs]


def reorder_chapter_content(html_content: str) -> str:
    """
    重新排序动态加载的章节内容（提取和清理）
    
    注意：由于没有参考顺序，本函数只进行提取和清理，不进行重排序。
    如果页面内容确实乱序，可能需要其他策略。
    
    Args:
        html_content: 章节页面的HTML内容
    
    Returns:
        清理后的HTML内容（仅包含段落，格式为 <p>...</p>）
    """
    try:
        paragraphs = extract_paragraphs(html_content)
        
        # 将段落组合成HTML
        html_parts = []
        for para in paragraphs:
            html_parts.append(f"<p>{para}</p>")
        
        return "\n".join(html_parts)
    
    except ValueError as e:
        # 如果提取失败，返回空字符串或原始内容的一部分
        print(f"警告: reorder提取段落失败: {e}")
        return ""


def detect_content_issues(html_content: str) -> Tuple[bool, List[str]]:
    """
    检测内容是否存在问题（乱序、缺失等）
    
    Args:
        html_content: HTML内容
    
    Returns:
        (是否有问题, 问题描述列表)
    """
    issues = []
    
    try:
        paragraphs = extract_paragraphs(html_content)
        
        # 检查段落数量
        if len(paragraphs) < 5:
            issues.append(f"段落数量过少: {len(paragraphs)}")
        
        # 检查是否有重复段落
        seen = set()
        duplicates = []
        for para in paragraphs:
            normalized = para.strip()[:50]  # 使用前50字符作为标识
            if normalized in seen:
                duplicates.append(normalized)
            seen.add(normalized)
        
        if duplicates:
            issues.append(f"发现重复段落: {len(duplicates)} 个")
        
        # 检查段落长度分布
        lengths = [len(p) for p in paragraphs]
        if lengths:
            avg_length = sum(lengths) / len(lengths)
            if avg_length < 20:
                issues.append(f"平均段落长度过短: {avg_length:.1f}")
        
        has_issues = len(issues) > 0
        return has_issues, issues
    
    except Exception as e:
        return True, [f"提取段落时出错: {e}"]
