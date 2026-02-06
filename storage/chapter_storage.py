"""章节内容存储系统

功能：
    - 管理章节内容的存储和读取
    - 支持按书籍ID和章节序号存储
    - 支持增量下载（检查章节是否已下载）
"""

import os
from pathlib import Path
from typing import Optional, Tuple


class ChapterStorage:
    """章节内容存储管理器"""
    
    def __init__(self, book_id: str, base_dir: str = "data/chapters"):
        """
        初始化存储管理器
        
        Args:
            book_id: 书籍ID
            base_dir: 基础存储目录
        """
        self.book_id = book_id
        self.base_dir = Path(base_dir)
        self.book_dir = self.base_dir / str(book_id)
        
        # 确保目录存在
        self.book_dir.mkdir(parents=True, exist_ok=True)
    
    def save_chapter(self, chapter_index: int, title: str, content: str) -> None:
        """
        保存章节内容
        
        Args:
            chapter_index: 章节序号（从1开始）
            title: 章节标题
            content: 章节内容（Markdown格式纯文本）
        """
        title_file = self.book_dir / f"{chapter_index}_title.txt"
        content_file = self.book_dir / f"{chapter_index}_content.md"
        
        # 保存标题
        with open(title_file, 'w', encoding='utf-8') as f:
            f.write(title)
        
        # 保存内容
        with open(content_file, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def load_chapter(self, chapter_index: int) -> Optional[Tuple[str, str]]:
        """
        加载章节内容
        
        Args:
            chapter_index: 章节序号
        
        Returns:
            (title, content) 元组，如果章节不存在则返回None
        """
        title_file = self.book_dir / f"{chapter_index}_title.txt"
        content_file = self.book_dir / f"{chapter_index}_content.md"
        
        if not title_file.exists() or not content_file.exists():
            return None
        
        try:
            with open(title_file, 'r', encoding='utf-8') as f:
                title = f.read().strip()
            
            with open(content_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return (title, content)
        except Exception as e:
            print(f"警告: 加载章节 {chapter_index} 失败: {e}")
            return None
    
    def chapter_exists(self, chapter_index: int) -> bool:
        """
        检查章节是否已下载
        
        Args:
            chapter_index: 章节序号
        
        Returns:
            如果章节存在返回True，否则返回False
        """
        title_file = self.book_dir / f"{chapter_index}_title.txt"
        content_file = self.book_dir / f"{chapter_index}_content.md"
        return title_file.exists() and content_file.exists()
    
    def get_downloaded_chapters(self) -> list[int]:
        """
        获取已下载的章节序号列表
        
        Returns:
            章节序号列表（已排序）
        """
        chapters = []
        for file in self.book_dir.glob("*_title.txt"):
            try:
                index = int(file.stem.split('_')[0])
                chapters.append(index)
            except ValueError:
                continue
        
        return sorted(chapters)
