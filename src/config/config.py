from pydantic_settings import BaseSettings
from typing import List, Dict, Any


class Settings(BaseSettings):
    system_name: str = "每日新闻流"
    system_version: str = "3.0.0"

    database_path: str = "data/news.db"

    collect_hour: int = 6
    collect_minute: int = 0

    ai_provider: str = "openai"
    ai_api_key: str = ""
    ai_api_base: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_translate_enabled: bool = True
    http_proxy: str = ""

    news_sources: List[Dict[str, Any]] = [
        {
            "name": "新华社",
            "url": "http://www.xinhuanet.com/",
            "enabled": True,
            "category": "中文",
            "mode": "scrape",
            "link_patterns": ["/20", "politics", "world", "finance", "tech"],
            "max_articles": 20,
            "priority": 5
        },
        {
            "name": "财联社",
            "url": "https://www.cls.cn/telegraph",
            "enabled": True,
            "category": "财经",
            "mode": "scrape",
            "link_patterns": ["detail", "/telegraph/"],
            "max_articles": 15,
            "priority": 3
        },
        {
            "name": "财经杂志",
            "url": "https://www.caijing.com.cn/",
            "enabled": True,
            "category": "财经",
            "mode": "scrape",
            "link_patterns": ["/20", "article"],
            "max_articles": 15,
            "priority": 3
        },
        {
            "name": "财新网",
            "url": "https://www.caixin.com/",
            "enabled": True,
            "category": "财经",
            "mode": "scrape",
            "link_patterns": ["/20", "article"],
            "max_articles": 15,
            "priority": 2
        },
        {
            "name": "BBC News",
            "url": "http://feeds.bbci.co.uk/news/rss.xml",
            "enabled": True,
            "category": "英文",
            "mode": "rss",
            "priority": 5
        },
        {
            "name": "纽约时报",
            "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            "enabled": True,
            "category": "英文",
            "mode": "rss",
            "priority": 5,
            "max_articles": 20
        },
        {
            "name": "Financial Times",
            "url": "https://www.ft.com/rss/home",
            "enabled": True,
            "category": "英文",
            "mode": "rss",
            "priority": 5,
            "max_articles": 20
        },
        {
            "name": "Bloomberg",
            "url": "https://feeds.bloomberg.com/markets/news.rss",
            "enabled": False,
            "category": "英文",
            "mode": "rss",
            "priority": 2
        },
        {
            "name": "Reuters",
            "url": "https://feeds.reuters.com/reuters/topNews",
            "enabled": True,
            "category": "英文",
            "mode": "rss",
            "exclude_keywords": ["sport", "football", "soccer", "basketball", "tennis", "cricket", "entertainment", "celebrity", "movie", "fashion"],
            "priority": 5
        },
        {
            "name": "半岛电视台",
            "url": "https://www.aljazeera.com/xml/rss/all.xml",
            "enabled": True,
            "category": "英文",
            "mode": "rss",
            "exclude_keywords": ["sport", "football", "soccer", "basketball", "tennis", "cricket", "entertainment", "celebrity", "movie"],
            "priority": 4
        }
    ]

    filter_settings: Dict[str, Any] = {
        "keywords": ["科技", "金融", "国际关系", "政治"],
        "exclude_keywords": ["娱乐", "体育", "八卦"],
        "max_news": 20,
        "dedup_window_hours": 72,
        "event_memory_days": 7
    }

    newsletter_settings: Dict[str, Any] = {
        "output_dir": "output",
        "formats": ["html"],
        "title_template": "每日新闻简报 - {date}"
    }

    category_order: List[str] = ["国际局势", "政策监管", "财经市场", "科技产业", "其他"]

    email_settings: Dict[str, Any] = {
        "smtp_host": "",
        "smtp_port": 465,
        "smtp_user": "",
        "smtp_password": "",
        "sender": "",
        "recipients": "",
        "use_ssl": True
    }

    class Config:
        env_file = "api_config.env"
        case_sensitive = False


settings = Settings()
