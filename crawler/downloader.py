"""HTTP 请求下载器

整体爬虫策略中的职责：

- 统一封装所有 HTTP 访问逻辑，避免在各处直接使用 requests。
- 处理：
  - 重试与指数退避；
  - 内容编码与 gzip/deflate/Brotli 解压；
  - 全局限速（避免触发 429 / 反爬）；
  - 随机 User-Agent 等“伪装”逻辑。

本模块是整个爬虫的“节流阀”和“防 ban 中枢”，上层（目录解析器 / 特殊章节解析器 /
章节正文解析器）都只通过 Downloader 来发起请求，而不再自行 sleep 或设置 UA。
"""

import random
import time
from typing import Optional
from urllib.parse import urljoin

import requests

# 一组常见的浏览器 User-Agent，用于随机轮换，降低被针对的概率
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    # Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    # Safari macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]


class Downloader:
    """HTTP下载器，封装requests，处理重试、编码、User-Agent、限速等。"""
    
    def __init__(
        self,
        base_url: str = "https://www.linovelib.com",
        retry_times: int = 3,
        retry_delay: float = 1.0,
        base_interval: float = 1.0,
        interval_jitter: float = 1.0,
    ):
        """
        初始化下载器
        
        Args:
            base_url: 基础URL
            retry_times: 重试次数
            retry_delay: 重试延迟（秒），用于指数退避的基数
            base_interval: 相邻请求的基础间隔时间（秒）
            interval_jitter: 在基础间隔上叠加的随机扰动（秒）
        """
        self.base_url = base_url
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.base_interval = base_interval
        self.interval_jitter = interval_jitter
        # 上一次请求完成时间，用于全局限速
        self._last_request_ts: float = 0.0

        self.session = requests.Session()
        # 这里设置的是“默认”请求头；每次请求时仍会随机选择 UA
        self.session.headers.update(
            {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                # 只使用 gzip/deflate（requests 内置支持）
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )

    def _sleep_for_rate_limit(self) -> None:
        """根据上一次请求时间和基础间隔，控制请求频率，加入随机抖动。"""
        now = time.monotonic()
        # 第一次请求不必等待
        if self._last_request_ts <= 0:
            return
        # 基础间隔 + 随机扰动
        interval = self.base_interval + random.uniform(0, self.interval_jitter)
        elapsed = now - self._last_request_ts
        if elapsed < interval:
            time.sleep(interval - elapsed)
    
    def download(self, url: str, timeout: int = 30) -> str:
        """
        下载网页内容，返回HTML文本
        
        Args:
            url: 要下载的URL（可以是相对路径或完整URL）
            timeout: 超时时间（秒）
        
        Returns:
            HTML文本内容
        
        Raises:
            requests.RequestException: 如果请求失败
        """
        # 如果是相对路径，转换为完整URL
        if not url.startswith('http'):
            url = urljoin(self.base_url, url)
        
        last_exception = None
        for attempt in range(self.retry_times):
            try:
                # 全局限速：请求前先根据上次请求时间 sleep 一下
                self._sleep_for_rate_limit()

                # 每次请求随机一个 User-Agent，尽量伪装成不同的浏览器会话
                headers = self.session.headers.copy()
                headers["User-Agent"] = random.choice(USER_AGENTS)

                response = self.session.get(url, timeout=timeout, stream=False, headers=headers)
                response.raise_for_status()
                
                # 检查Content-Type
                content_type = response.headers.get('Content-Type', '').lower()
                if 'text/html' not in content_type:
                    print(f"警告: Content-Type不是text/html: {content_type}")
                
                # 检查Content-Encoding并处理
                content_encoding = response.headers.get('Content-Encoding', '').lower()
                if content_encoding:
                    if 'br' in content_encoding:
                        # Brotli压缩需要手动处理
                        try:
                            import brotli
                            # 手动解压Brotli
                            decompressed = brotli.decompress(response.content)
                            # 检测编码并解码
                            if response.encoding:
                                text_content = decompressed.decode(response.encoding, errors='replace')
                            else:
                                # 尝试UTF-8
                                text_content = decompressed.decode('utf-8', errors='replace')
                            print(f"已手动解压Brotli内容")
                        except ImportError:
                            print(f"警告: 服务器返回Brotli压缩，但未安装brotli库。尝试重新请求（无压缩）")
                            # 重新请求，不使用压缩
                            headers_no_compression = self.session.headers.copy()
                            headers_no_compression.pop('Accept-Encoding', None)
                            response = self.session.get(url, timeout=timeout, headers=headers_no_compression)
                            response.raise_for_status()
                            text_content = response.text
                        except Exception as e:
                            print(f"警告: Brotli解压失败: {e}，尝试重新请求（无压缩）")
                            # 重新请求，不使用压缩
                            headers_no_compression = self.session.headers.copy()
                            headers_no_compression.pop('Accept-Encoding', None)
                            response = self.session.get(url, timeout=timeout, headers=headers_no_compression)
                            response.raise_for_status()
                            text_content = response.text
                    else:
                        # gzip/deflate由requests自动处理
                        text_content = response.text
                else:
                    # 无压缩，直接使用text
                    text_content = response.text
                
                # 验证内容是否是有效的HTML文本
                if not isinstance(text_content, str):
                    # 如果response.text不是字符串，说明可能有问题
                    # 尝试手动解码
                    text_content = response.content.decode(response.encoding or 'utf-8', errors='replace')
                
                # 验证内容是否以HTML开头
                text_stripped = text_content.strip()
                if not text_stripped.startswith('<!') and not text_stripped.startswith('<html'):
                    # 可能是错误页面或其他内容
                    print(f"警告: 内容可能不是HTML格式，前100字符: {text_content[:100]}")
                
                # 如果还没有设置编码，尝试检测
                if not hasattr(response, '_encoding_set') or response.encoding is None or response.encoding.lower() == 'iso-8859-1':
                    # 尝试从Content-Type或HTML meta标签检测编码
                    if hasattr(response, 'apparent_encoding') and response.apparent_encoding:
                        # 如果检测到新编码且内容不是Brotli解压的，重新解码
                        if 'br' not in content_encoding:
                            try:
                                text_content = response.content.decode(response.apparent_encoding, errors='replace')
                            except:
                                pass  # 如果解码失败，使用已有的text_content
                
                # 记录本次请求完成时间
                self._last_request_ts = time.monotonic()

                return text_content
            except requests.RequestException as e:
                last_exception = e

                # 特判 429（Too Many Requests），适当延长等待时间
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status == 429:
                    # 尝试读取 Retry-After 头；如果没有，就退避一段较长时间
                    retry_after = 0
                    try:
                        retry_after = int(e.response.headers.get("Retry-After", "0"))
                    except Exception:
                        retry_after = 0
                    wait_time = max(retry_after, self.retry_delay * (attempt + 1) * 3)
                    print(f"警告: 收到 429 Too Many Requests，等待 {wait_time:.1f}s 后重试: {url}")
                    time.sleep(wait_time)
                else:
                    # 普通错误按指数退避
                    if attempt < self.retry_times - 1:
                        wait_time = self.retry_delay * (attempt + 1)
                        time.sleep(wait_time)
                    else:
                        raise
        
        # 理论上不会到达这里，但为了类型检查
        raise last_exception
    
    def close(self):
        """关闭session"""
        self.session.close()
