import feedparser
import requests
from bs4 import BeautifulSoup
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from src.config.config import settings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NewsCollector:

    def __init__(self):
        self.news_sources = settings.news_sources
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        self.proxies = None
        if settings.http_proxy:
            self.proxies = {
                'http': settings.http_proxy,
                'https': settings.http_proxy,
            }
            logger.info(f"使用代理: {settings.http_proxy}")

    def collect_news(self) -> List[Dict[str, Any]]:
        all_news = []
        enabled_sources = [s for s in self.news_sources if s.get('enabled', False)]

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for source in enabled_sources:
                mode = source.get('mode', 'rss')
                if mode == 'scrape':
                    future = executor.submit(self._collect_by_scraping, source)
                else:
                    future = executor.submit(self._collect_by_rss, source)
                futures[future] = source

            for future in as_completed(futures):
                source = futures[future]
                try:
                    news = future.result()
                    all_news.extend(news)
                    logger.info(f"成功采集 {source['name']} 的 {len(news)} 条新闻")
                except Exception as e:
                    logger.error(f"采集 {source['name']} 时出错: {str(e)}")

        unique_news = self._deduplicate_news(all_news)
        logger.info(f"去重后剩余 {len(unique_news)} 条新闻")
        return unique_news

    def _collect_by_rss(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        news_list = []
        try:
            try:
                response = requests.get(source['url'], headers=self.headers, timeout=20, allow_redirects=True, proxies=self.proxies)
                if response.status_code == 200:
                    try:
                        response.encoding = response.apparent_encoding
                    except Exception:
                        pass
                    feed = feedparser.parse(response.text)
                else:
                    feed = feedparser.parse(source['url'])
            except Exception:
                feed = feedparser.parse(source['url'])

            if feed.bozo:
                logger.warning(f"解析 {source['name']} 的 RSS 时出错: {feed.bozo_exception}")
                try:
                    response = requests.get(source['url'], headers=self.headers, timeout=15, allow_redirects=True, proxies=self.proxies)
                    if response.status_code == 200:
                        try:
                            response.encoding = response.apparent_encoding
                        except Exception:
                            pass
                        feed = feedparser.parse(response.text)
                        if not feed.bozo:
                            logger.info(f"使用备用方法成功解析 {source['name']} 的 RSS")
                except Exception as e:
                    logger.error(f"备用方法解析 {source['name']} 的 RSS 时出错: {str(e)}")

            for entry in feed.entries:
                news = self._parse_rss_entry(entry, source)
                if news:
                    source_exclude = source.get('exclude_keywords', [])
                    if source_exclude:
                        text = f"{news['title']} {news['summary']}".lower()
                        if any(kw.lower() in text for kw in source_exclude):
                            continue
                    if not news['summary'] or len(news['summary']) < 100:
                        _, full_content = self._fetch_full_content(news['link'])
                        if full_content:
                            news['summary'] = full_content
                    news_list.append(news)
        except Exception as e:
            logger.error(f"RSS 采集 {source['name']} 时出错: {str(e)}")

        return news_list

    def _collect_by_scraping(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        news_list = []
        try:
            url = source['url']
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True, proxies=self.proxies)
            if response.status_code != 200:
                logger.warning(f"抓取 {source['name']} 首页失败: HTTP {response.status_code}")
                return news_list

            try:
                response.encoding = response.apparent_encoding
            except Exception:
                pass

            soup = BeautifulSoup(response.text, 'html.parser')

            article_link_patterns = source.get('link_patterns', ['/20', 'article', 'detail', 'content'])
            max_articles = source.get('max_articles', 20)

            seen_urls = set()
            for a in soup.find_all('a', href=True):
                href = a['href']
                title = a.get_text(strip=True)

                if not title or len(title) < 8 or len(title) > 100:
                    continue

                if not any(pattern in href for pattern in article_link_patterns):
                    continue

                full_url = urljoin(url, href)
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                if len(news_list) >= max_articles:
                    break

                page_title, summary = self._fetch_full_content(full_url)
                if not summary or len(summary) < 50:
                    continue

                title = page_title if page_title and len(page_title) >= 8 else title

                content_hash = self._generate_hash(title + full_url)
                now = datetime.now(timezone(timedelta(hours=8)))
                news = {
                    'title': title,
                    'summary': summary,
                    'link': full_url,
                    'source': source['name'],
                    'published': now.isoformat(),
                    'collected_at': now.isoformat(),
                    'category': source.get('category', '未分类'),
                    'content_hash': content_hash
                }
                news_list.append(news)

        except Exception as e:
            logger.error(f"网页抓取 {source['name']} 时出错: {str(e)}")

        return news_list

    def _parse_rss_entry(self, entry: Dict[str, Any], source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            title = entry.get('title', '').strip()
            link = entry.get('link', '')
            published = entry.get('published', '') or entry.get('pubDate', '')
            summary = entry.get('summary', '').strip() or entry.get('description', '').strip()

            published_date = None
            tz_cn = timezone(timedelta(hours=8))
            if published:
                try:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    elif hasattr(entry, 'pubdate_parsed') and entry.pubdate_parsed:
                        published_date = datetime(*entry.pubdate_parsed[:6], tzinfo=timezone.utc)
                    else:
                        import dateutil.parser
                        published_date = dateutil.parser.parse(published)
                except Exception:
                    published_date = datetime.now(tz_cn)
            else:
                published_date = datetime.now(tz_cn)

            content = ''
            if 'content' in entry:
                content = ' '.join([c.get('value', '') for c in entry.content])
            elif 'content:encoded' in entry:
                content = entry['content:encoded']

            summary = self._clean_html(summary)
            content = self._clean_html(content)

            if not summary and content:
                summary = content

            is_google_news_junk = (
                'news.google.com' in link and (
                    not summary or summary.startswith('http') or len(summary) < 30 or 'CBMi' in summary
                )
            )

            if is_google_news_junk or not summary or len(summary) < 50:
                fetch_url = link
                if 'news.google.com' in link:
                    try:
                        r = requests.get(link, headers=self.headers, timeout=10, allow_redirects=True, proxies=self.proxies)
                        fetch_url = r.url
                    except Exception:
                        pass
                page_title, full_content = self._fetch_full_content(fetch_url)
                if full_content:
                    summary = full_content
                    if page_title and len(page_title) >= 8:
                        title = page_title
                    if fetch_url != link:
                        link = fetch_url

            content_hash = self._generate_hash(title + link)

            news = {
                'title': title,
                'summary': summary,
                'link': link,
                'source': source['name'],
                'published': published_date.isoformat() if hasattr(published_date, 'isoformat') else str(published_date),
                'collected_at': datetime.now(tz_cn).isoformat(),
                'category': source.get('category', '未分类'),
                'content_hash': content_hash
            }

            if not title or not link:
                return None

            return news

        except Exception as e:
            logger.error(f"解析新闻条目时出错: {str(e)}")
            return None

    def _fetch_full_content(self, url: str) -> tuple:
        try:
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True, proxies=self.proxies)
            if response.status_code != 200:
                return ('', '')

            try:
                response.encoding = response.apparent_encoding
            except Exception:
                pass

            soup = BeautifulSoup(response.text, 'html.parser')

            page_title = ''
            title_tag = soup.find('title')
            if title_tag and title_tag.get_text(strip=True):
                page_title = title_tag.get_text(strip=True)
            else:
                h1 = soup.find('h1')
                if h1 and h1.get_text(strip=True):
                    page_title = h1.get_text(strip=True)

            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside',
                             'iframe', 'noscript', 'form', 'button', 'input',
                             'div[class*="comment"]', 'div[class*="share"]',
                             'div[class*="recommend"]', 'div[class*="related"]',
                             'div[class*="sidebar"]', 'div[class*="ad"]',
                             'div[class*="banner"]', 'div[class*="popup"]',
                             'div[class*="modal"]', 'div[class*="tag"]',
                             'span[class*="tag"]', 'div[class*="breadcrumb"]',
                             'div[class*="copyright"]', 'div[class*="source"]',
                             'div[class*="author"]', 'div[class*="editor"]',
                             'div[class*="keyword"]', 'div[class*="hot"]',
                             'div[class*="more"]', 'div[class*="list"]']):
                tag.decompose()

            selectors = [
                'article',
                'div[class*="content"]',
                'div[class*="article"]',
                'div[class*="detail"]',
                'div[class*="text"]',
                'div[class*="body"]',
                'div[id*="content"]',
                'div[id*="article"]',
                'main',
            ]

            for selector in selectors:
                content_element = soup.select_one(selector)
                if content_element:
                    paragraphs = content_element.find_all(['p'])
                    if paragraphs:
                        texts = []
                        for p in paragraphs[:6]:
                            t = p.get_text(strip=True)
                            if len(t) > 20 and not self._is_noise(t):
                                texts.append(t)
                        if texts:
                            return (page_title, ' '.join(texts)[:800])
                    text = content_element.get_text(separator=' ', strip=True)
                    if len(text) > 100:
                        return (page_title, self._clean_extracted_text(text)[:800])

            paragraphs = soup.find_all(['p'])
            if paragraphs:
                texts = []
                for p in paragraphs[:6]:
                    t = p.get_text(strip=True)
                    if len(t) > 20 and not self._is_noise(t):
                        texts.append(t)
                if texts:
                    return (page_title, ' '.join(texts)[:800])

            return (page_title, '')
        except Exception as e:
            logger.error(f"获取网页内容时出错: {str(e)}")
            return ('', '')

    def _is_noise(self, text: str) -> bool:
        noise_patterns = [
            '相关报道', '相关推荐', '相关新闻', '相关文章',
            '点击查看', '点击下载', '扫码下载', '扫码关注',
            '责任编辑', '编辑：', '记者：', '来源：',
            '延伸阅读', '热门推荐', '猜你喜欢',
            '【财新周刊】', '【财新网】',
        ]
        text_lower = text.strip()
        for pattern in noise_patterns:
            if text_lower.startswith(pattern):
                return True
        if text_lower.startswith('【') and '】' in text_lower[:20]:
            return True
        return False

    def _clean_extracted_text(self, text: str) -> str:
        import re
        text = re.sub(r'相关报道.*', '', text)
        text = re.sub(r'相关推荐.*', '', text)
        text = re.sub(r'相关新闻.*', '', text)
        text = re.sub(r'延伸阅读.*', '', text)
        text = re.sub(r'热门推荐.*', '', text)
        text = re.sub(r'责任编辑.*', '', text)
        text = re.sub(r'【[^】]*】', '', text)
        text = re.sub(r'专享[^，。]*[，。]', '', text)
        text = re.sub(r'解锁直达.*', '', text)
        text = re.sub(r'单篇付费.*', '', text)
        text = re.sub(r'精粹专家视角.*', '', text)
        text = re.sub(r'点击[^，。]*[，。]', '', text)
        text = re.sub(r'扫描[^，。]*[，。]', '', text)
        text = re.sub(r'下载[^，。]*[，。]', '', text)
        text = re.sub(r'关注[^，。]*[，。]', '', text)
        text = re.sub(r'分享到.*', '', text)
        text = re.sub(r'版权所有.*', '', text)
        text = re.sub(r'未经授权.*', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _clean_html(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'a', 'img', 'div[class*="related"]',
                             'div[class*="recommend"]', 'div[class*="share"]']):
                tag.decompose()
            text = soup.get_text(separator=' ', strip=True)
            text = self._clean_extracted_text(text)
            return text
        except Exception:
            return html

    def _generate_hash(self, text: str) -> str:
        return hashlib.md5(text.encode('utf-8')).hexdigest()

    def _deduplicate_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen_hashes = set()
        unique_news = []

        for news in news_list:
            if news['content_hash'] not in seen_hashes:
                seen_hashes.add(news['content_hash'])
                unique_news.append(news)

        return unique_news


if __name__ == "__main__":
    collector = NewsCollector()
    news = collector.collect_news()
    print(f"采集到 {len(news)} 条新闻")
    for i, item in enumerate(news[:5]):
        print(f"\n{i+1}. {item['title']}")
        print(f"   来源: {item['source']}")
        print(f"   链接: {item['link']}")
        print(f"   发布时间: {item['published']}")
        print(f"   摘要: {item['summary'][:100]}...")
