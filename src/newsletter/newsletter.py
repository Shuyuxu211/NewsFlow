import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from src.config.config import settings
from src.storage.storage import NewsStorage
import logging

logger = logging.getLogger(__name__)


class NewsletterGenerator:

    def __init__(self):
        self.storage = NewsStorage()
        self.output_dir = settings.newsletter_settings.get('output_dir', 'output')
        self._ensure_output_directory()

    def _ensure_output_directory(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def generate(self, news_list: List[Dict[str, Any]], date_str: Optional[str] = None) -> Optional[str]:
        if not news_list:
            logger.warning("没有新闻可供生成简报")
            return None

        tz = timezone(timedelta(hours=8))
        if not date_str:
            date_str = datetime.now(tz).strftime('%Y-%m-%d')

        title_template = settings.newsletter_settings.get('title_template', '每日新闻简报 - {date}')
        title = title_template.format(date=date_str)

        categorized = self._categorize_news(news_list)

        now = datetime.now(tz)
        html = self._generate_html(title, date_str, categorized, len(news_list))

        output_path = os.path.join(self.output_dir, f'newsletter_{date_str}.html')
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"简报已生成: {output_path}")
        except Exception as e:
            logger.error(f"保存简报文件时出错: {str(e)}")
            return None

        try:
            self.storage.save_newsletter({
                'date': date_str,
                'title': title,
                'content': html,
                'format': 'html',
                'generated_at': now.isoformat()
            })
        except Exception as e:
            logger.error(f"保存简报到数据库时出错: {str(e)}")

        return output_path

    def _categorize_news(self, news_list: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        categories = {}
        for news in news_list:
            cat = news.get('category', '未分类')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(news)

        return categories

    def _generate_simple_summary(self, news: Dict[str, Any]) -> str:
        summary = (news.get('summary', '') or '').strip()
        if not summary:
            return news.get('title', '无标题')[:50]

        text = summary
        title = news.get('title', '')
        if title and len(title) > 100:
            text = title

        sentences = re.split(r'[。！？；]', text)
        for s in sentences:
            s = s.strip()
            if len(s) > 10:
                result = s + '...' if len(s) > 80 else s
                return result

        return text[:80] + '...'

    def _generate_html(
        self,
        title: str,
        date_str: str,
        categorized: Dict[str, List[Dict[str, Any]]],
        total_count: int
    ) -> str:
        all_news = []
        for cat, items in categorized.items():
            all_news.extend(items)
        all_news.sort(key=lambda x: x.get('published', '') or '', reverse=True)

        items_html = ''
        for news in all_news:
            source = news.get('source', '未知')
            published = news.get('published', '')
            summary = news.get('ai_summary', '') or self._generate_simple_summary(news)
            if len(summary) > 200:
                summary = summary[:200] + '…'
            link = news.get('link', '#')

            items_html += f'''
                <div class="news-item">
                    <div class="avatar">{source[0]}</div>
                    <div class="bubble">
                        <div class="bubble-header">
                            <span class="bubble-name">{source}</span>
                            <span class="bubble-time">{published}</span>
                        </div>
                        <a href="{link}" target="_blank" rel="noopener">{summary}</a>
                    </div>
                </div>'''

        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)

        html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f0f2f5; color: #333; line-height: 1.6; }}
        .container {{ max-width: 480px; margin: 0 auto; padding: 0; background: #f0f2f5; min-height: 100vh; }}
        header {{ background: linear-gradient(135deg, #ff9a9e 0%, #fad0c4 100%); color: #fff; padding: 20px 16px; margin-bottom: 12px; }}
        header h1 {{ font-size: 18px; margin-bottom: 4px; }}
        header .date {{ font-size: 12px; opacity: 0.85; }}
        .news-item {{ display: flex; align-items: flex-start; padding: 8px 12px; gap: 10px; }}
        .avatar {{ width: 36px; height: 36px; border-radius: 50%; background: #6c5ce7; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: bold; flex-shrink: 0; }}
        .bubble {{ background: #fff; border-radius: 0 12px 12px 12px; padding: 10px 14px; max-width: calc(100% - 48px); box-shadow: 0 1px 2px rgba(0,0,0,0.06); }}
        .bubble-name {{ font-size: 12px; color: #6c5ce7; font-weight: 600; }}
        .bubble-time {{ font-size: 11px; color: #aaa; margin-left: 8px; }}
        .bubble-header {{ margin-bottom: 4px; }}
        .bubble a {{ color: #333; text-decoration: none; font-size: 14px; line-height: 1.55; }}
        .bubble a:hover {{ color: #6c5ce7; }}
        footer {{ text-align: center; padding: 16px; font-size: 11px; color: #bbb; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <div class="date">{now.strftime("%Y-%m-%d %H:%M")} (UTC+8) | 共 {total_count} 条</div>
        </header>
        {items_html}
        <footer>由每日新闻流系统自动生成</footer>
    </div>
</body>
</html>'''

        return html
