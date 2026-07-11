import json
import os
import re
import time
import asyncio
from typing import List, Dict, Any, Optional
from src.config.config import settings
from src.storage.storage import NewsStorage
import logging

# 统一排除词表 — _coarse_filter 和 _keyword_filter 共用
DEFAULT_EXCLUDE_KEYWORDS = [
    # 娱乐/体育/八卦
    '娱乐', '体育', '八卦', '明星', '综艺', '选秀', '球赛', '足球', '篮球',
    # 付费墙标记
    '专享', '解锁', '研选', 'VIP', 'vip', '付费', '订阅', '会员专享',
    # 聚合/复盘/观点类
    'T早报', '早报', '快讯集锦', '收盘', '复盘', '观点文章', '深度分析',
    # 展会/旅游/乡村/农事
    '消博', '博览会', '旅游', '茶山', '振兴', '农事', '乡村', '县域经济',
    # 城市宣传/风光/摄影
    '城市', '之城', '风光', '摄影', '无人机照片',
    # 季节性/节日
    '春日', '春暖', '花开', '踏青', '赏花', '五一', '假期',
    # 校园/教育
    '学校', '大学', '校友', '学长', '教育改革',
    # 新华社类软性内容
    '潮玩', '舞蹈', '夺冠', '奖牌', '金牌', '银牌', '致敬', '献礼',
    # 新媒体/低质内容标记
    'Vlog', 'vlog', '首发', '打卡', '美好生活', '城市介绍', '人物特写',
    '学校宣传', '革命圣地', '历史故事', '文化报道',
    # 特殊排除（原_keyword_filter独有）
    '茶叶', '助手还是', '竞争对手', '得力助手', '如何被', '是得力',
    '观察', '思考', '解读', '分析', '评论',
]

logger = logging.getLogger(__name__)

FILTER_SYSTEM_PROMPT = """你是一个新闻筛选助手，为关注全球局势和市场动态的读者筛选有价值的新闻。

【需要排除的内容——这些不是新闻】
1. 礼节性访问/会见：如"某某会见某某""某某访问某地"，无实质性政策或合作声明
2. 视察调研类：如"领导视察某村/某企业/某工厂"
3. 农事/丰收/乡村振兴：如"春耕""秋收""乡村新貌""县域经济"
4. 城市宣传/旅游推广：如"某地举办文化节""旅游旺季""城市名片"
5. 人物特写/好人好事/劳模表彰
6. 革命历史/红色故事/纪念活动
7. 纯表态性报道：只写"某某表示/强调/指出"但无具体政策、数据、行动
8. 学校招生/开学/毕业典礼
9. 体育比赛/娱乐八卦/明星绯闻
10. 重复通报：同一事件的多个版本只保留最有信息量的一条

【需要保留的内容——这些是真正的新闻】
1. 具体数据：如"GDP增长X%""出口额X亿""降息X个基点"
2. 具体行动/政策：如"出台X法规""制裁X国""批准X项目"
3. 冲突/战争/制裁进展：如"袭击X货船""停火协议破裂"
4. 国际关系实质性变化：如"签署X协议""X国加入X组织"
5. 重大经济数据/市场变化：如"油价涨X%""汇率破X"
6. 监管/立法/政策文件：如"发布X新规""修订X法律"
7. 科技突破：如"发布X芯片""X技术取得突破"
8. 公司重大事件：如"IPO""并购""高管变动""业绩暴雷"
9. 自然灾害/事故：如"地震X级""航班取消"
10. 严肃国际媒体报道的地缘政治/经济/科技新闻

【评分标准】
- 10分：直接改变市场格局的重大事件（战争、制裁、央行大幅降息/加息）
- 8-9分：重大政策/数据发布、地缘风险升级、科技突破
- 6-7分：有信号意义的政策动向、行业趋势变化、中等影响事件
- 4-5分：信息增量有限但有参考价值的事件
- 1-3分：上述排除类内容、无实质信息的报道

【summary要求】
一句话摘要，包含"什么+怎么样+影响"，约30-50字。例如：
- "美伊紧张局势升级，美军袭击伊朗货船，黄金受挫美元走强，市场避险情绪上升"
- "4月16日美联储宣布降息25个基点，美元走弱，科技股受提振"
- "证监会发布创业板第四套上市标准，要求企业营收不低于1亿元且研发投入超8%"

请严格按JSON格式返回：
{
  "results": {
    "0": { "keep": 1, "score": 8, "reason": "...", "summary": "核心事实+具体影响" },
    "1": { "keep": 0, "score": 2, "reason": "礼节性访问，无实质信息" }
  }
}"""


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
    return None


class AIClient:
    _clients: Dict[str, Any] = {}

    def __init__(self):
        self.provider = os.environ.get('AI_PROVIDER', settings.ai_provider)
        self.api_key = os.environ.get('AI_API_KEY', settings.ai_api_key)
        self.api_base = os.environ.get('AI_API_BASE', settings.ai_api_base)
        self.model = os.environ.get('AI_MODEL', settings.ai_model)

        if self.provider == 'deepseek':
            if not self.api_base or self.api_base == 'https://api.openai.com/v1':
                self.api_base = 'https://api.deepseek.com'
            if not self.model or self.model == 'gpt-4o-mini':
                self.model = 'deepseek-v4-flash'
        elif self.provider == 'gemini':
            if not self.api_base or self.api_base == 'https://api.openai.com/v1':
                self.api_base = 'https://generativelanguage.googleapis.com/v1beta/'
            if not self.model or self.model == 'gpt-4o-mini':
                self.model = 'gemini-3.1-flash-lite'
        elif self.provider == 'zhipu':
            if not self.api_base or self.api_base in ('https://api.openai.com/v1', 'https://open.bigmodel.cn/api/m/v1'):
                self.api_base = 'https://open.bigmodel.cn/api/paas/v4/'
            if not self.model or self.model == 'gpt-4o-mini':
                self.model = 'glm-4-flash'
        elif self.provider == 'groq':
            if not self.api_base or self.api_base == 'https://api.openai.com/v1':
                self.api_base = 'https://api.groq.com/openai/v1'
            if not self.model or self.model == 'gpt-4o-mini':
                self.model = 'llama-3.3-70b-versatile'
        elif self.provider == 'qwen':
            if not self.api_base or self.api_base == 'https://api.openai.com/v1':
                self.api_base = 'https://api.siliconflow.cn/v1'
            if not self.model or self.model == 'gpt-4o-mini':
                self.model = 'Qwen/Qwen3-8B'

        if self.provider == 'qwen':
            self.request_delay = 1
            self.max_retries = 3
            self.batch_size = 10
        elif self.provider == 'gemini':
            self.request_delay = 5
            self.max_retries = 5
            self.batch_size = 5
        elif self.provider == 'zhipu':
            self.request_delay = 3
            self.max_retries = 3
            self.batch_size = 10
        elif self.provider == 'groq':
            self.request_delay = 12
            self.max_retries = 3
            self.batch_size = 5
        elif self.provider == 'deepseek':
            self.request_delay = 0.5
            self.max_retries = 3
            self.batch_size = 20
        else:
            self.request_delay = 2
            self.max_retries = 3
            self.batch_size = 15

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 2000, json_mode: bool = False) -> Optional[str]:
        if not self.is_configured():
            return None
        return self._openai_compatible(system_prompt, user_prompt, temperature, max_tokens, json_mode)

    async def chat_async(self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 2000, json_mode: bool = False) -> Optional[str]:
        if not self.is_configured():
            return None
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._openai_compatible,
            system_prompt, user_prompt, temperature, max_tokens, json_mode
        )

    def _get_client(self) -> Any:
        import openai
        import httpx

        key = f"{self.provider}:{self.api_key[:8]}"
        if key not in AIClient._clients:
            if self.provider == 'groq':
                http_client = httpx.Client(
                    timeout=httpx.Timeout(60.0),
                    limits=httpx.Limits(max_connections=1, max_keepalive_connections=1)
                )
            elif self.provider == 'deepseek':
                http_client = httpx.Client(timeout=30.0)
            else:
                http_client = httpx.Client(timeout=60.0)
            AIClient._clients[key] = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                http_client=http_client,
                max_retries=0
            )
        return AIClient._clients[key]

    def _openai_compatible(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, json_mode: bool) -> Optional[str]:
        try:
            client = self._get_client()

            kwargs = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            if self.provider == 'qwen':
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
            elif self.provider == 'deepseek':
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

            if json_mode and self.provider not in ('groq', 'gemini'):
                kwargs["response_format"] = {"type": "json_object"}

            if json_mode and self.provider in ('groq', 'gemini'):
                kwargs["messages"][0]["content"] += "\n\n重要：你必须且只能返回合法的JSON格式，不要包含任何其他文字。"

            for attempt in range(self.max_retries):
                try:
                    start_time = time.time()
                    response = client.chat.completions.create(**kwargs)
                    elapsed = time.time() - start_time
                    logger.info(f"API 响应时间: {elapsed:.2f}秒")
                    content = response.choices[0].message.content
                    if self.provider == 'qwen':
                        if not content:
                            content = getattr(response.choices[0].message, 'reasoning_content', None) or ''
                        content = re.sub(r'<think[\s\S]*?</think\s*>', '', content).strip()
                        if elapsed > 30:
                            logger.warning(f"Qwen 响应时间过长({elapsed:.1f}s)，可能触发了思考模式")
                    if self.provider == 'deepseek' and not content:
                        if json_mode and 'response_format' in kwargs:
                            logger.warning("DeepSeek json_mode 返回空响应，关闭 json_mode 重试")
                            kwargs.pop("response_format", None)
                            kwargs["messages"][0]["content"] += "\n\n你必须严格按JSON格式返回：{\"results\":{...}}"
                            time.sleep(0.5)
                            json_mode = False
                            continue
                        if attempt < self.max_retries - 1:
                            logger.warning(f"DeepSeek 返回空响应 (attempt {attempt+1})，1秒后重试")
                            time.sleep(1)
                            continue
                        logger.error("DeepSeek 多次返回空响应，批次丢弃")
                        return None
                    return content
                except Exception as e:
                    error_str = str(e)
                    is_payload_too_large = '413' in error_str or 'too large' in error_str.lower()
                    is_rate_limit = (
                        '429' in error_str
                        or 'rate' in error_str.lower()
                        or 'quota' in error_str.lower()
                        or 'resource_exhausted' in error_str.lower()
                        or 'too many' in error_str.lower()
                    )
                    is_retryable = (
                        'timed out' in error_str.lower()
                        or 'connection' in error_str.lower()
                        or 'timeout' in error_str.lower()
                    )
                    is_fatal = (
                        '403' in error_str
                        or '401' in error_str
                        or 'invalid' in error_str.lower()
                    )
                    logger.warning(f"API 调用异常 (attempt {attempt+1}): {error_str[:150]}")

                    if is_payload_too_large or is_fatal:
                        logger.error(f"不可重试错误({error_str[:50]})，直接失败")
                        return None

                    if is_rate_limit or is_retryable:
                        wait = self.request_delay * (2 ** attempt)
                        if wait > 60:
                            wait = 60
                        reason = "限流" if is_rate_limit else "超时/连接错误"
                        logger.warning(f"API {reason}，等待 {wait} 秒后重试 ({attempt+1}/{self.max_retries})")
                        time.sleep(wait)
                        continue
                    else:
                        logger.error(f"API 调用出错: {error_str[:200]}")
                        raise

            logger.error(f"API 调用失败，已重试 {self.max_retries} 次")
            return None

        except ImportError:
            logger.error("openai 库未安装，请运行: uv pip install openai")
            return None
        except Exception as e:
            logger.error(f"AI API 调用失败 ({self.provider}): {str(e)[:200]}")
            return None


class AIFilter:
    def __init__(self):
        self.storage = NewsStorage()
        self.client = AIClient()
        self.source_priorities = self._build_source_priorities()

    def _build_source_priorities(self) -> Dict[str, int]:
        priorities = {}
        for source in settings.news_sources:
            priorities[source['name']] = source.get('priority', 1)
        return priorities

    def _generate_event_fingerprint(self, news: Dict[str, Any]) -> str:
        title = news.get('title', '')
        summary = (news.get('ai_summary', '') or news.get('summary', '') or '')[:200]
        text = f"{title} {summary}"

        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text)

        entity_patterns = [
            r'伊朗|以色列|美国|中国|日本|俄罗斯|乌克兰|欧盟|北约|东盟|印尼|泰国|韩国|朝鲜',
            r'革命卫队|美联储|央行|证监会|国防部|外交部|白宫|克里姆林宫',
            r'霍尔木兹海峡|南海|台海|红海|波罗的海',
            r'比特币|美元|黄金|原油|纳斯达克|恒生|A股|日经',
        ]
        action_patterns = [
            r'扣押|袭击|制裁|加息|降息|发布|宣布|签署|批准|退出|加入|起诉|调查'
        ]

        entities = []
        for pattern in entity_patterns:
            entities.extend(re.findall(pattern, text))
        
        actions = []
        for pattern in action_patterns:
            actions.extend(re.findall(pattern, text))

        # Combine key tokens into a stable fingerprint string for deduplication
        fingerprint_parts = words[:4] + entities[:3] + actions[:2]
        return "|".join(fingerprint_parts)

    def _filter_by_date(self, news_list: List[Dict[str, Any]], hours: int = 24) -> List[Dict[str, Any]]:
        from datetime import datetime, timezone, timedelta
        import dateutil.parser

        tz_cn = timezone(timedelta(hours=8))
        now = datetime.now(tz_cn)
        cutoff = now.timestamp() - (hours * 3600)

        filtered = []
        removed_details = []
        for news in news_list:
            pub = news.get('published', '')
            if not pub:
                removed_details.append(f"无日期: {news.get('title', '?')[:30]}")
                continue
            try:
                dt = dateutil.parser.parse(str(pub))
                if dt.tzinfo is None:
                    cat = news.get('category', '')
                    if cat == '英文':
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.replace(tzinfo=tz_cn)
                age_hours = (now.timestamp() - dt.timestamp()) / 3600
                if dt.timestamp() >= cutoff:
                    filtered.append(news)
                else:
                    removed_details.append(f"超{age_hours:.0f}h: {news.get('title', '?')[:30]}")
            except Exception as e:
                logger.warning(f"日期解析失败: {pub} - {e}, 保留该新闻")
                filtered.append(news)

        if removed_details:
            logger.info(f"日期过滤移除 {len(removed_details)} 条: {removed_details[:5]}")
        logger.info(f"日期过滤: {len(news_list)} -> {len(filtered)} 条 (保留{hours}小时内)")
        return filtered

    def filter_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not news_list:
            return []

        news_list = self._filter_by_date(news_list)

        rules = self._load_filter_rules()

        if not self.client.is_configured():
            logger.warning("未配置 AI API Key，使用关键词筛选模式")
            return self._keyword_filter(news_list, rules)

        return self._two_round_filter(news_list, rules)

    async def filter_news_async(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not news_list:
            return []

        news_list = self._filter_by_date(news_list)

        rules = self._load_filter_rules()

        if not self.client.is_configured():
            logger.warning("未配置 AI API Key，使用关键词筛选模式")
            return self._keyword_filter(news_list, rules)

        return await self._two_round_filter_async(news_list, rules)

    def _load_filter_rules(self) -> Dict[str, Any]:
        rules = {
            'include': [],
            'exclude': [],
            'max_news': settings.filter_settings.get('max_news', 20)
        }

        try:
            import sqlite3
            with sqlite3.connect(self.storage.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM filter_rules ORDER BY priority DESC')
                for row in cursor.fetchall():
                    rule = {
                        'id': row['id'],
                        'name': row['name'],
                        'type': row['type'],
                        'value': row['value'],
                        'priority': row['priority']
                    }
                    if row['type'] == 'include':
                        rules['include'].append(rule)
                    elif row['type'] == 'exclude':
                        rules['exclude'].append(rule)

            if not rules['include'] and not rules['exclude']:
                rules['include'] = [
                    {'name': kw, 'type': 'include', 'value': kw, 'priority': 1}
                    for kw in settings.filter_settings.get('keywords', [])
                ]
                rules['exclude'] = [
                    {'name': kw, 'type': 'exclude', 'value': kw, 'priority': 1}
                    for kw in settings.filter_settings.get('exclude_keywords', [])
                ]

        except Exception as e:
            logger.error(f"加载筛选规则时出错: {str(e)}")
            rules['include'] = [
                {'name': kw, 'type': 'include', 'value': kw, 'priority': 1}
                for kw in settings.filter_settings.get('keywords', [])
            ]
            rules['exclude'] = [
                {'name': kw, 'type': 'exclude', 'value': kw, 'priority': 1}
                for kw in settings.filter_settings.get('exclude_keywords', [])
            ]

        return rules

    def _keyword_filter(self, news_list: List[Dict[str, Any]], rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        keyword_exclude = DEFAULT_EXCLUDE_KEYWORDS

        filtered = []

        for news in news_list:
            title = news.get('title', '')
            summary = news.get('summary', '') or ''
            text = f"{title} {summary}".lower()

            excluded = False
            for rule in rules.get('exclude', []):
                if rule['value'].lower() in text:
                    excluded = True
                    break
            if excluded:
                continue

            for kw in keyword_exclude:
                if kw.lower() in text:
                    excluded = True
                    break
            if excluded:
                continue

            score = 0
            for rule in rules.get('include', []):
                if rule['value'].lower() in text:
                    score += rule.get('priority', 1)

            if score > 0:
                news['relevance_score'] = score
                if not news.get('ai_summary'):
                    news['ai_summary'] = self._generate_simple_summary(news)
                filtered.append(news)

        filtered.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        max_news = rules.get('max_news', 20)

        if len(filtered) < 5:
            logger.warning(f"关键词筛选结果不足({len(filtered)}条)，放宽条件补充")
            existing = {id(n) for n in filtered}
            for news in news_list:
                if id(news) in existing:
                    continue
                news['relevance_score'] = 1
                if not news.get('ai_summary'):
                    news['ai_summary'] = self._generate_simple_summary(news)
                filtered.append(news)
                existing.add(id(news))
                if len(filtered) >= max_news:
                    break

        filtered.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        result = self._ensure_source_diversity(filtered, max_news)

        # 国内源保底：关键词降级模式也确保财经源不低于 2 条（排除新华社）
        domestic_sources = {'财联社', '财经杂志', '财新网'}
        min_domestic = min(2, max_news // 10)  # 至少 2 条
        if len(result) < max_news:
            domestic_in_result = [n for n in result if n.get('source') in domestic_sources]
            if len(domestic_in_result) < min_domestic:
                logger.info(f"关键词筛选财经源不足({len(domestic_in_result)}条 < {min_domestic})，补充")
                existing_ids = {n.get('id') or n.get('link') for n in result}
                for n in news_list:
                    if n.get('source') not in domestic_sources:
                        continue
                    if (n.get('id') or n.get('link')) in existing_ids:
                        continue
                    n['relevance_score'] = n.get('relevance_score', 1)
                    if not n.get('ai_summary'):
                        n['ai_summary'] = self._generate_simple_summary(n)
                    n['filter_reason'] = '（财经源保底补充）'
                    result.append(n)
                    existing_ids.add(n.get('id') or n.get('link'))
                    domestic_in_result.append(n)
                    if len(domestic_in_result) >= min_domestic:
                        break
                logger.info(f"财经源补充后: {len(domestic_in_result)} 条")

        return result

    def _generate_simple_summary(self, news: Dict[str, Any]) -> str:
        summary = (news.get('summary', '') or '').strip()
        if not summary:
            return news.get('title', '')[:50]

        # 先用句号/感叹号/问号分割，再用中文逗号/分号分割
        # 对齐 newsletter._generate_simple_summary() 的分割逻辑
        for sep in ['。', '！', '？', '；', '，']:
            parts = summary.split(sep)
            for part in parts:
                part = part.strip()
                if len(part) > 8:
                    if len(part) > 60:
                        return part[:60] + '...'
                    return part

        return summary[:60] + '...'

    def _two_round_filter(self, news_list: List[Dict[str, Any]], rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        max_news = rules.get('max_news', 20)

        logger.info(f"第一轮粗筛: {len(news_list)} 条新闻")
        coarse_filtered = self._coarse_filter(news_list, rules)
        logger.info(f"粗筛后: {len(coarse_filtered)} 条新闻")

        logger.info(f"第二轮AI精筛: {len(coarse_filtered)} 条新闻")
        ai_filtered = self._ai_semantic_filter(coarse_filtered)
        logger.info(f"AI精筛后: {len(ai_filtered)} 条新闻")

        fill_threshold = max(max_news // 2, 8)
        if len(ai_filtered) < fill_threshold:
            logger.warning(f"AI筛选结果不足({len(ai_filtered)}条 < {fill_threshold})，从粗筛结果补充")
            existing_ids = {n.get('id') or n.get('link') for n in ai_filtered}
            for n in coarse_filtered:
                if (n.get('id') or n.get('link')) not in existing_ids:
                    if not n.get('ai_summary'):
                        n['ai_summary'] = self._generate_simple_summary(n)
                    n['filter_reason'] = '（AI筛选不足，粗筛补充）'
                    n['relevance_score'] = n.get('relevance_score', 5)
                    ai_filtered.append(n)
                    existing_ids.add(n.get('id') or n.get('link'))
                if len(ai_filtered) >= max_news:
                    break

        logger.info(f"第三轮去重: {len(ai_filtered)} 条新闻")
        if self.client.provider in ('groq', 'qwen'):
            deduplicated = self._event_deduplicate(ai_filtered)
            deduplicated = self._title_deduplicate(deduplicated)
        else:
            deduplicated = self._deduplicate_similar(ai_filtered)
            deduplicated = self._event_deduplicate(deduplicated)
        logger.info(f"去重后: {len(deduplicated)} 条新闻")

        result = self._categorize_by_topic(deduplicated)
        logger.info(f"分类配额后: {len(result)} 条新闻")

        # 国内源保底：仅针对财经类源（排除新华社），确保有少量中文财经内容
        domestic_sources = {'财联社', '财经杂志', '财新网'}
        min_domestic = min(2, max_news // 8)  # max_news=20 → 2条
        if len(result) < max_news and coarse_filtered:
            domestic_in_result = [n for n in result if n.get('source') in domestic_sources]
            if len(domestic_in_result) < min_domestic:
                logger.info(f"财经源不足({len(domestic_in_result)}条 < {min_domestic})，从粗筛结果补充")
                existing_ids = {n.get('id') or n.get('link') for n in result}
                for n in coarse_filtered:
                    if n.get('source') not in domestic_sources:
                        continue
                    if (n.get('id') or n.get('link')) in existing_ids:
                        continue
                    if not n.get('ai_summary'):
                        n['ai_summary'] = self._generate_simple_summary(n)
                    n['filter_reason'] = '（财经源保底补充）'
                    n['relevance_score'] = n.get('relevance_score', 5)
                    n['topic'] = '其他'
                    result.append(n)
                    existing_ids.add(n.get('id') or n.get('link'))
                    domestic_in_result.append(n)
                    if len(domestic_in_result) >= min_domestic:
                        break
                logger.info(f"财经源补充后: {len(domestic_in_result)} 条, 共{len(result)}条")

        return result

    async def _two_round_filter_async(self, news_list: List[Dict[str, Any]], rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        max_news = rules.get('max_news', 20)

        logger.info(f"第一轮粗筛: {len(news_list)} 条新闻")
        coarse_filtered = self._coarse_filter(news_list, rules)
        logger.info(f"粗筛后: {len(coarse_filtered)} 条新闻")

        logger.info(f"第二轮AI精筛: {len(coarse_filtered)} 条新闻")
        ai_filtered = await self._ai_semantic_filter_async(coarse_filtered)
        logger.info(f"AI精筛后: {len(ai_filtered)} 条新闻")

        fill_threshold = max(max_news // 2, 8)
        if len(ai_filtered) < fill_threshold:
            logger.warning(f"AI筛选结果不足({len(ai_filtered)}条 < {fill_threshold})，从粗筛结果补充")
            existing_ids = {n.get('id') or n.get('link') for n in ai_filtered}
            for n in coarse_filtered:
                if (n.get('id') or n.get('link')) not in existing_ids:
                    if not n.get('ai_summary'):
                        n['ai_summary'] = self._generate_simple_summary(n)
                    n['filter_reason'] = '（AI筛选不足，粗筛补充）'
                    n['relevance_score'] = n.get('relevance_score', 5)
                    ai_filtered.append(n)
                    existing_ids.add(n.get('id') or n.get('link'))
                if len(ai_filtered) >= max_news:
                    break

        logger.info(f"第三轮去重: {len(ai_filtered)} 条新闻")
        if self.client.provider in ('groq', 'qwen'):
            deduplicated = self._event_deduplicate(ai_filtered)
            deduplicated = self._title_deduplicate(deduplicated)
        else:
            deduplicated = await self._deduplicate_similar_async(ai_filtered)
            deduplicated = self._event_deduplicate(deduplicated)
        logger.info(f"去重后: {len(deduplicated)} 条新闻")

        result = self._categorize_by_topic(deduplicated)
        logger.info(f"分类配额后: {len(result)} 条新闻")

        # 国内源保底：仅针对财经类源（排除新华社），确保有少量中文财经内容
        domestic_sources = {'财联社', '财经杂志', '财新网'}
        min_domestic = min(2, max_news // 8)  # max_news=20 → 2条
        if len(result) < max_news and coarse_filtered:
            domestic_in_result = [n for n in result if n.get('source') in domestic_sources]
            if len(domestic_in_result) < min_domestic:
                logger.info(f"财经源不足({len(domestic_in_result)}条 < {min_domestic})，从粗筛结果补充")
                existing_ids = {n.get('id') or n.get('link') for n in result}
                for n in coarse_filtered:
                    if n.get('source') not in domestic_sources:
                        continue
                    if (n.get('id') or n.get('link')) in existing_ids:
                        continue
                    if not n.get('ai_summary'):
                        n['ai_summary'] = self._generate_simple_summary(n)
                    n['filter_reason'] = '（财经源保底补充）'
                    n['relevance_score'] = n.get('relevance_score', 5)
                    n['topic'] = '其他'
                    result.append(n)
                    existing_ids.add(n.get('id') or n.get('link'))
                    domestic_in_result.append(n)
                    if len(domestic_in_result) >= min_domestic:
                        break
                logger.info(f"财经源补充后: {len(domestic_in_result)} 条, 共{len(result)}条")

        return result

    def _deduplicate_similar(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(news_list) <= 1:
            return news_list

        news_items = []
        for i, news in enumerate(news_list):
            title = news.get('title', '')
            summary = news.get('ai_summary', '') or (news.get('summary', '') or '')[:100]
            score = news.get('relevance_score', 5)
            news_items.append(f"[{i}] 标题: {title}\n摘要: {summary[:80]}\n评分: {score}")

        news_text = "\n\n".join(news_items)

        prompt = f"""请识别以下新闻中的重复/相似新闻，保留最重要的那条。

判断标准：
- 同一事件的不同报道（谈判、访问、会议等）只保留1条
- 保留评分最高的
- 如果评分相同，保留信息最完整的
- 相似度>90%的应视为重复（宽松阈值，仅剔除完全重复报道，避免过度裁减）

请以JSON格式返回：
{{
  "keep_indices": [0, 3, 5, 8, 10],
  "removed": [1, 2, 4, 6, 7, 9]
}}

新闻列表：

{news_text}"""

        result_text = self.client.chat(
            system_prompt="你是一个新闻去重助手，只返回JSON格式结果。",
            user_prompt=prompt,
            json_mode=True
        )

        if not result_text:
            logger.warning("AI去重返回空结果，使用标题相似度去重")
            return self._title_deduplicate(news_list)

        result = _extract_json(result_text)
        if not result:
            logger.warning("AI去重结果解析失败，使用标题相似度去重")
            return self._title_deduplicate(news_list)

        keep_indices = result.get('keep_indices', [])
        if not keep_indices:
            logger.warning("AI去重返回空keep_indices，使用标题相似度去重")
            return self._title_deduplicate(news_list)

        logger.info(f"去重: 从{len(news_list)}条中移除{len(news_list)-len(keep_indices)}条重复")
        return [news_list[i] for i in keep_indices if i < len(news_list)]

    async def _deduplicate_similar_async(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(news_list) <= 1:
            return news_list

        news_items = []
        for i, news in enumerate(news_list):
            title = news.get('title', '')
            summary = news.get('ai_summary', '') or (news.get('summary', '') or '')[:100]
            score = news.get('relevance_score', 5)
            news_items.append(f"[{i}] 标题: {title}\n摘要: {summary[:80]}\n评分: {score}")

        news_text = "\n\n".join(news_items)

        prompt = f"""请识别以下新闻中的重复/相似新闻，保留最重要的那条。

判断标准：
- 同一事件的不同报道（谈判、访问、会议等）只保留1条
- 保留评分最高的
- 如果评分相同，保留信息最完整的
- 相似度>90%的应视为重复（宽松阈值，仅剔除完全重复报道，避免过度裁减）

请以JSON格式返回：
{{
  "keep_indices": [0, 3, 5, 8, 10],
  "removed": [1, 2, 4, 6, 7, 9]
}}

新闻列表：

{news_text}"""

        result_text = await self.client.chat_async(
            system_prompt="你是一个新闻去重助手，只返回格式结果。",
            user_prompt=prompt,
            json_mode=True
        )

        if not result_text:
            logger.warning("AI去重返回空结果，使用标题相似度去重")
            return self._title_deduplicate(news_list)

        result = _extract_json(result_text)
        if not result:
            logger.warning("AI去重结果解析失败，使用标题相似度去重")
            return self._title_deduplicate(news_list)

        keep_indices = result.get('keep_indices', [])
        if not keep_indices:
            logger.warning("AI去重返回空keep_indices，使用标题相似度去重")
            return self._title_deduplicate(news_list)

        logger.info(f"去重: 从{len(news_list)}条中移除{len(news_list)-len(keep_indices)}条重复")
        return [news_list[i] for i in keep_indices if i < len(news_list)]

    def _title_deduplicate(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(news_list) <= 1:
            return news_list

        def _tokenize(text: str) -> set:
            import re
            return set(re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+|\d+', text.lower()))

        seen_tokens = []
        result = []
        for news in news_list:
            title = news.get('title', '').strip()
            title_tokens = _tokenize(title)
            if len(title_tokens) < 2:
                result.append(news)
                continue
            is_dup = False
            for existing_tokens in seen_tokens:
                intersection = len(title_tokens & existing_tokens)
                union = len(title_tokens | existing_tokens)
                if union > 0 and intersection / union > 0.6:
                    is_dup = True
                    break
            if not is_dup:
                seen_tokens.append(title_tokens)
                result.append(news)
            else:
                logger.info(f"标题去重移除: {title[:40]}")

        logger.info(f"标题去重: {len(news_list)} -> {len(result)} 条")
        return result

    def _event_deduplicate(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        dedup_window_hours = settings.filter_settings.get('dedup_window_hours', 72)

        recent_events = self.storage.get_recent_events(days=dedup_window_hours // 24)
        logger.info(f"加载历史事件记忆: {len(recent_events)} 条")

        seen_events = {}
        result = []
        today_events_saved = []

        for news in news_list:
            fingerprint = self._generate_event_fingerprint(news)
            if not fingerprint or len(fingerprint) < 3:
                result.append(news)
                continue

            source = news.get('source', '')
            source_priority = self.source_priorities.get(source, 1)
            score = news.get('relevance_score', 5)

            if fingerprint in recent_events:
                kept_event = recent_events[fingerprint]
                kept_priority = self.source_priorities.get(kept_event['source'], 1)

                if source_priority > kept_priority:
                    logger.info(f"跨天去重-替换: [{kept_event['source']}:{kept_event['title'][:20]}] -> [{source}:{news.get('title', '')[:20]}]")
                    result = [n for n in result if n.get('source') != kept_event['source'] or n.get('title', '')[:20] != kept_event['title'][:20]]
                    result.append(news)
                    recent_events[fingerprint] = {
                        'source': source, 'title': news.get('title', ''),
                        'link': news.get('link', ''), 'event_date': news.get('published', '')[:10],
                        'last_seen': news.get('published', '')
                    }
                    today_events_saved.append((fingerprint, source, news.get('title', ''), news.get('link', ''), news.get('published', '')[:10]))
                else:
                    logger.info(f"跨天去重-跳过: [{source}:{news.get('title', '')[:20]}] (已被 {kept_event['source']} 报道)")
                    continue
            elif fingerprint in seen_events:
                existing = seen_events[fingerprint]
                if source_priority > existing['priority'] or (source_priority == existing['priority'] and score > existing['score']):
                    logger.info(f"同源去重-替换: [{existing['source']}:{existing['title'][:20]}] -> [{source}:{news.get('title', '')[:20]}]")
                    result = [n for n in result if n.get('title') != existing['title']]
                    result.append(news)
                    seen_events[fingerprint] = {'source': source, 'title': news.get('title', ''), 'priority': source_priority, 'score': score}
                    today_events_saved.append((fingerprint, source, news.get('title', ''), news.get('link', ''), news.get('published', '')[:10]))
                else:
                    logger.info(f"同源去重-跳过: [{source}:{news.get('title', '')[:20]}]")
                    continue
            else:
                seen_events[fingerprint] = {'source': source, 'title': news.get('title', ''), 'priority': source_priority, 'score': score}
                result.append(news)
                today_events_saved.append((fingerprint, source, news.get('title', ''), news.get('link', ''), news.get('published', '')[:10]))

        for fp, src, ttl, link, evt_date in today_events_saved:
            if len(fp) >= 3:
                self.storage.save_event_fingerprint(fp, src, ttl, link, evt_date)

        self.storage.clean_old_events(days=14)

        logger.info(f"事件去重: {len(news_list)} -> {len(result)} 条")
        return result

    def _coarse_filter(self, news_list: List[Dict[str, Any]], rules: Dict[str, Any]) -> List[Dict[str, Any]]:
        filtered = []
        exclude_keywords = [r['value'].lower() for r in rules.get('exclude', [])]
        all_exclude = list(set(exclude_keywords + DEFAULT_EXCLUDE_KEYWORDS))

        for news in news_list:
            title = news.get('title', '')
            summary = news.get('summary', '') or ''
            text = f"{title} {summary}".lower()

            excluded = False
            for kw in all_exclude:
                if kw.lower() in text:
                    excluded = True
                    break
            if excluded:
                continue

            if not title or len(title) <= 5:
                continue

            filtered.append(news)

        return filtered

    def _ai_semantic_filter(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        max_news = self._load_filter_rules().get('max_news', 20)
        batch_size = self.client.batch_size
        all_results = []
        failed_batches = 0

        for i in range(0, len(news_list), batch_size):
            batch = news_list[i:i + batch_size]
            logger.info(f"AI筛选批次 {i//batch_size + 1}/{(len(news_list)-1)//batch_size + 1}: {len(batch)} 条")
            batch_results = self._ai_filter_batch(batch)
            if len(batch_results) == 0:
                failed_batches += 1
            all_results.extend(batch_results)
            if i + batch_size < len(news_list):
                logger.info(f"批次间等待 {self.client.request_delay} 秒...")
                time.sleep(self.client.request_delay)

        if len(all_results) < 5:
            logger.warning(f"AI筛选有效结果不足({len(all_results)}条)，降级为关键词筛选")
            return self._keyword_filter(news_list, self._load_filter_rules())

        all_results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return all_results[:max_news]

    async def _ai_semantic_filter_async(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        max_news = self._load_filter_rules().get('max_news', 20)
        batch_size = self.client.batch_size
        all_results = []
        failed_batches = 0

        for i in range(0, len(news_list), batch_size):
            batch = news_list[i:i + batch_size]
            logger.info(f"AI筛选批次 {i//batch_size + 1}/{(len(news_list)-1)//batch_size + 1}: {len(batch)} 条")
            batch_results = await self._ai_filter_batch_async(batch)
            if len(batch_results) == 0:
                failed_batches += 1
            all_results.extend(batch_results)
            if i + batch_size < len(news_list):
                logger.info(f"批次间等待 {self.client.request_delay} 秒...")
                await asyncio.sleep(self.client.request_delay)

        if len(all_results) < 5:
            logger.warning(f"AI筛选有效结果不足({len(all_results)}条)，降级为关键词筛选")
            return self._keyword_filter(news_list, self._load_filter_rules())

        all_results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return all_results[:max_news]

    def _ai_filter_batch(self, news_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        news_items = []
        for i, news in enumerate(news_batch):
            title = news.get('title', '')
            summary = (news.get('summary', '') or '')[:300]
            source = news.get('source', '')
            category = news.get('category', '')
            news_items.append(f"[{i}] 标题: {title}\n来源: {source} | 分类: {category}\n摘要: {summary}")

        news_text = "\n\n".join(news_items)

        prompt = f"""请对以下新闻进行筛选和评分，并生成简洁摘要。

评分标准：
- 8-10分：重大政策变化、行业格局性影响、地缘风险重大进展
- 5-7分：有一定市场影响、政策信号意义、行业趋势变化
- 3-4分：信息增量有限、影响面较窄
- 1-2分：对决策无帮助、纯社会新闻、礼节性报道

请以JSON格式返回，summary字段必须是中文摘要（核心事实+具体影响，包含时间/数据/人物等关键要素，如：4月16日美联储宣布降息25个基点，美元走弱，科技股受提振）：
{{
  "results": {{
    "0": {{ "keep": 1, "score": 8, "reason": "证监会发布新规直接影响市场交易规则", "summary": "证监会发布创业板第四套上市标准新规，要求企业营收不低于1亿元且研发投入占比超8%" }},
    "1": {{ "keep": 0, "score": 2, "reason": "纯礼节性会见，无实质政策信息" }}
  }}
}}

keep=1 表示保留，keep=0 表示排除。只保留 score>=5 的新闻。

新闻列表：

{news_text}"""

        # 首次调用（json_mode=True）
        result_text = self.client.chat(
            system_prompt=FILTER_SYSTEM_PROMPT,
            user_prompt=prompt,
            json_mode=True
        )

        # 重试：空结果或解析失败时关闭 json_mode 重试
        if not result_text:
            logger.warning("AI筛选批次返回空结果，关闭 json_mode 重试")
            result_text = self.client.chat(
                system_prompt=FILTER_SYSTEM_PROMPT,
                user_prompt=prompt + "\n请务必以JSON格式返回，不要包含任何其他内容。",
                json_mode=False
            )

        result = _extract_json(result_text) if result_text else None
        if not result:
            logger.warning(f"AI筛选结果解析失败（重试后），原始响应: {(result_text or '空')[:200]}")
            return []

        filtered = []
        results = result.get('results', {})
        if not results:
            logger.warning(f"AI筛选结果无results字段（重试后），原始响应: {result_text[:200]}")
            return []

        logger.info(f"AI筛选批次结果: {len(results)}条评分, 保留{sum(1 for v in results.values() if v.get('keep',0)==1 and v.get('score',0)>=5)}条")

        for i, news in enumerate(news_batch):
            item_result = results.get(str(i), {})
            score = item_result.get('score', 0)
            if item_result.get('keep', 0) == 1 and score >= 5:
                news['relevance_score'] = score
                news['filter_reason'] = item_result.get('reason', '')
                ai_summary = item_result.get('summary', '')
                if ai_summary:
                    news['ai_summary'] = ai_summary
                else:
                    news['ai_summary'] = self._generate_simple_summary(news)
                filtered.append(news)

        return filtered

    async def _ai_filter_batch_async(self, news_batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        news_items = []
        for i, news in enumerate(news_batch):
            title = news.get('title', '')
            summary = (news.get('summary', '') or '')[:300]
            source = news.get('source', '')
            category = news.get('category', '')
            news_items.append(f"[{i}] 标题: {title}\n来源: {source} | 分类: {category}\n摘要: {summary}")

        news_text = "\n\n".join(news_items)

        prompt = f"""请对以下新闻进行筛选和评分，并生成简洁摘要。

评分标准：
- 8-10分：重大政策变化、行业格局性影响、地缘风险重大进展
- 5-7分：有一定市场影响、政策信号意义、行业趋势变化
- 3-4分：信息增量有限、影响面较窄
- 1-2分：对决策无帮助、纯社会新闻、礼节性报道

请以JSON格式返回，summary字段必须是中文摘要（核心事实+具体影响，包含时间/数据/人物等关键要素，如：4月16日美联储宣布降息25个基点，美元走弱，科技股受提振）：
{{
  "results": {{
    "0": {{ "keep": 1, "score": 8, "reason": "证监会发布新规直接影响市场交易规则", "summary": "证监会发布创业板第四套上市标准新规，要求企业营收不低于1亿元且研发投入占比超8%" }},
    "1": {{ "keep": 0, "score": 2, "reason": "纯礼节性会见，无实质政策信息" }}
  }}
}}

keep=1 表示保留，keep=0 表示排除。只保留 score>=5 的新闻。

新闻列表：

{news_text}"""

        result_text = await self.client.chat_async(
            system_prompt=FILTER_SYSTEM_PROMPT,
            user_prompt=prompt,
            json_mode=True
        )

        if not result_text:
            logger.warning("AI筛选批次返回空结果，关闭 json_mode 重试")
            result_text = await self.client.chat_async(
                system_prompt=FILTER_SYSTEM_PROMPT,
                user_prompt=prompt + "\n请务必以JSON格式返回，不要包含任何其他内容。",
                json_mode=False
            )

        result = _extract_json(result_text) if result_text else None
        if not result:
            logger.warning(f"AI筛选结果解析失败（重试后），原始响应: {(result_text or '空')[:200]}")
            return []

        filtered = []
        results = result.get('results', {})
        if not results:
            logger.warning(f"AI筛选结果无results字段（重试后），原始响应: {(result_text or '')[:200]}")
            return []

        logger.info(f"AI筛选批次结果: {len(results)}条评分, 保留{sum(1 for v in results.values() if v.get('keep',0)==1 and v.get('score',0)>=5)}条")

        for i, news in enumerate(news_batch):
            item_result = results.get(str(i), {})
            score = item_result.get('score', 0)
            if item_result.get('keep', 0) == 1 and score >= 5:
                news['relevance_score'] = score
                news['filter_reason'] = item_result.get('reason', '')
                ai_summary = item_result.get('summary', '')
                if ai_summary:
                    news['ai_summary'] = ai_summary
                else:
                    news['ai_summary'] = self._generate_simple_summary(news)
                filtered.append(news)

        return filtered

    def _categorize_by_topic(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        topic_keywords = {
            '国际局势': ['战争', '冲突', '制裁', '外交', '北约', '联合国', '停火', '边境', '军事', '袭击', '导弹', '货船',
                         '伊朗', '俄罗斯', '乌克兰', '中东', '以色列', '台海', '南海', '美军', '北约', '联合国',
                         'war', 'conflict', 'military', 'sanction', 'attack', 'iran', 'russia', 'ukraine', 'middle east', 'strike'],
            '政策监管': ['政策', '监管', '证监会', '央行', '降息', '加息', '利率', '法规', '立法', '审批', '审查', '新规',
                         '关税', '贸易', '海关', '出口', '进口', '美联储', 'fed', 'regulation', 'policy', 'rate', 'sanction',
                         'tariff', 'trade', 'customs'],
            '财经市场': ['股市', '上涨', '下跌', '指数', '期货', '油价', '油价', '汇率', '美元', '黄金', '债券', '通胀',
                         'ipo', '财报', '业绩', '并购', '收购', '涨停', '跌停', '成交量', '市值', '基金',
                         'stock', 'market', 'oil price', 'dollar', 'gold', 'inflation', 'earnings', 'fed', 'rate cut'],
            '科技产业': ['芯片', '半导体', 'ai', '人工智能', '科技', '创新', '发布', '突破', '华为', '英伟达', '苹果',
                         '自动驾驶', '电动车', '新能源', '电池', '航天', '发射',
                         'chip', 'ai', 'tech', 'apple', 'nvidia', 'tesla', 'spacex', 'satellite', 'electric vehicle'],
        }
        market_impact_topics = {'政策监管', '财经市场', '国际局势'}
        max_news = self._load_filter_rules().get('max_news', 20)

        for news in news_list:
            text = (news.get('title', '') + ' ' + (news.get('ai_summary', '') or news.get('summary', '') or '')).lower()
            news['topic'] = '其他'
            for topic, keywords in topic_keywords.items():
                if any(kw.lower() in text for kw in keywords):
                    news['topic'] = topic
                    break

        priority_1 = [n for n in news_list if n.get('topic') in market_impact_topics and n.get('relevance_score', 0) >= 5]
        priority_1.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        priority_2 = [n for n in news_list if n.get('topic') not in market_impact_topics or n.get('relevance_score', 0) < 5]
        priority_2.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        result = priority_1[:max_news]
        remaining = max_news - len(result)
        if remaining > 0:
            result.extend(priority_2[:remaining])

        category_groups: Dict[str, List[Dict[str, Any]]] = {}
        for news in result:
            topic = news.get('topic', '其他')
            if topic not in category_groups:
                category_groups[topic] = []
            category_groups[topic].append(news)

        ordered_result = []
        for topic in settings.category_order:
            if topic in category_groups:
                ordered_result.extend(category_groups[topic])

        return ordered_result

    def _ensure_source_diversity(self, news_list: List[Dict[str, Any]], max_news: int) -> List[Dict[str, Any]]:
        result = []
        source_counts: Dict[str, int] = {}
        per_source_max = max(max_news // 3, 3)

        for news in news_list:
            source = news.get('source', '未知')
            if source_counts.get(source, 0) < per_source_max:
                result.append(news)
                source_counts[source] = source_counts.get(source, 0) + 1
            if len(result) >= max_news:
                break

        return result


class AITranslator:
    def __init__(self):
        self.client = AIClient()

    def is_available(self) -> bool:
        return self.client.is_configured() and settings.ai_translate_enabled

    def translate_news(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.is_available():
            return news_list

        foreign_news = [n for n in news_list if n.get('category', '') == '英文' and not n.get('translated')]
        if not foreign_news:
            logger.info("无需翻译的新闻")
            return news_list

        logger.info(f"批量翻译 {len(foreign_news)} 条英文新闻")
        try:
            self._translate_batch_text(foreign_news)
        except Exception as e:
            logger.error(f"翻译过程出错: {e}")
        return news_list

    async def translate_news_async(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.is_available():
            return news_list

        foreign_news = [n for n in news_list if n.get('category', '') == '英文' and not n.get('translated')]
        if not foreign_news:
            logger.info("无需翻译的新闻")
            return news_list

        logger.info(f"批量翻译 {len(foreign_news)} 条英文新闻")
        try:
            await self._translate_batch_text_async(foreign_news)
        except Exception as e:
            logger.error(f"翻译过程出错: {e}")
        return news_list

    def _translate_batch_text(self, news_batch: List[Dict[str, Any]]) -> None:
        batch_size = 5
        for start in range(0, len(news_batch), batch_size):
            batch = news_batch[start:start + batch_size]
            logger.info(f"翻译批次 {start//batch_size + 1}/{(len(news_batch) + batch_size - 1)//batch_size}: {len(batch)} 条")
            items = []
            for i, news in enumerate(batch):
                title = news.get('title', '')
                summary = (news.get('summary', '') or '')[:300]
                items.append(f"[{i}] Title: {title}\nSummary: {summary}")

            text = "\n\n".join(items)

            prompt = f"""Translate the following English news into Simplified Chinese. For each item, return EXACTLY two lines:
Line 1: Chinese title (concise, include key entities like country names, organizations)
Line 2: Chinese summary (one sentence, 30-80 chars, MUST include: who did what + specific impact/data/casualties. Do NOT drop key facts like country names, death tolls, or causal relationships)
Separate each item with a blank line.

{text}"""

            result_text = self.client.chat(
                system_prompt="You are a professional English-to-Chinese news translator. Preserve ALL key facts: who, what, where, casualties, numbers, impacts. Never produce vague summaries that lose the core event.",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=1500,
                json_mode=False
            )

            if not result_text:
                logger.warning(f"翻译批次返回空结果，共 {len(batch)} 条新闻未翻译")
                continue

            blocks = [b.strip() for b in result_text.strip().split('\n\n') if b.strip()]
            expected = len(batch)
            actual = len(blocks)
            if actual < expected:
                logger.warning(f"翻译解析块数量不匹配: 期望 {expected} 块, 实际 {actual} 块, 将逐条回退重试缺失项")

            for i, news in enumerate(batch):
                if i < len(blocks):
                    lines = [l.strip() for l in blocks[i].split('\n') if l.strip()]
                    if len(lines) >= 2:
                        news['title_original'] = news['title']
                        news['title'] = lines[0]
                        if not news.get('ai_summary'):
                            news['summary_original'] = news.get('summary', '')
                            news['summary'] = lines[1]
                        news['translated'] = 1
                    elif len(lines) == 1:
                        news['title_original'] = news['title']
                        news['title'] = lines[0]
                        news['translated'] = 1
                    else:
                        logger.warning(f"翻译解析失败: 块 {i} 无有效行，来源={news.get('source')}, 标题={news.get('title', '')[:60]}")
                        self._translate_single_fallback(news)
                else:
                    logger.warning(f"翻译解析失败: 块 {i} 缺失，来源={news.get('source')}, 标题={news.get('title', '')[:60]}")
                    self._translate_single_fallback(news)

    def _translate_single_fallback(self, news: Dict[str, Any]) -> None:
        title = news.get('title', '')
        summary = (news.get('summary', '') or '')[:300]
        if not news.get('ai_summary'):
            prompt = f"""Translate the following English news into Simplified Chinese. Return EXACTLY two lines:
Line 1: Chinese title (concise, include key entities)
Line 2: Chinese summary (one sentence, 30-80 chars, include who did what + specific impact)

Title: {title}
Summary: {summary}"""
        else:
            prompt = f"""Translate the following English news title into Simplified Chinese. Return ONLY the Chinese title, one line.

Title: {title}"""

        result_text = self.client.chat(
            system_prompt="You are a professional English-to-Chinese news translator. Preserve ALL key facts.",
            user_prompt=prompt,
            temperature=0.3,
            max_tokens=500,
            json_mode=False
        )

        if not result_text:
            logger.warning(f"逐条翻译回退失败(API返回空): {title[:60]}")
            return

        lines = [l.strip() for l in result_text.strip().split('\n') if l.strip()]
        if not lines:
            logger.warning(f"逐条翻译回退失败(无有效行): {title[:60]}")
            return

        news['title_original'] = news['title']
        news['title'] = lines[0]
        if not news.get('ai_summary') and len(lines) >= 2:
            news['summary_original'] = news.get('summary', '')
            news['summary'] = lines[1]
        news['translated'] = 1
        logger.info(f"逐条翻译回退成功: {title[:60]} -> {lines[0][:60]}")

    async def _translate_batch_text_async(self, news_batch: List[Dict[str, Any]]) -> None:
        batch_size = 5
        for start in range(0, len(news_batch), batch_size):
            batch = news_batch[start:start + batch_size]
            logger.info(f"翻译批次 {start//batch_size + 1}/{(len(news_batch) + batch_size - 1)//batch_size}: {len(batch)} 条")
            items = []
            for i, news in enumerate(batch):
                title = news.get('title', '')
                summary = (news.get('summary', '') or '')[:300]
                items.append(f"[{i}] Title: {title}\nSummary: {summary}")

            text = "\n\n".join(items)

            prompt = f"""Translate the following English news into Simplified Chinese. For each item, return EXACTLY two lines:
Line 1: Chinese title (concise, include key entities like country names, organizations)
Line 2: Chinese summary (one sentence, 30-80 chars, MUST include: who did what + specific impact/data/casualties. Do NOT drop key facts like country names, death tolls, or causal relationships)
Separate each item with a blank line.

{text}"""

            result_text = await self.client.chat_async(
                system_prompt="You are a professional English-to-Chinese news translator. Preserve ALL key facts: who, what, where, casualties, numbers, impacts. Never produce vague summaries that lose the core event.",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=1500,
                json_mode=False
            )

            if not result_text:
                logger.warning(f"翻译批次返回空结果，共 {len(batch)} 条新闻未翻译")
                continue

            blocks = [b.strip() for b in result_text.strip().split('\n\n') if b.strip()]
            expected = len(batch)
            actual = len(blocks)
            if actual < expected:
                logger.warning(f"翻译解析块数量不匹配: 期望 {expected} 块, 实际 {actual} 块, 将逐条回退重试缺失项")

            for i, news in enumerate(batch):
                if i < len(blocks):
                    lines = [l.strip() for l in blocks[i].split('\n') if l.strip()]
                    if len(lines) >= 2:
                        news['title_original'] = news['title']
                        news['title'] = lines[0]
                        if not news.get('ai_summary'):
                            news['summary_original'] = news.get('summary', '')
                            news['summary'] = lines[1]
                        news['translated'] = 1
                    elif len(lines) == 1:
                        news['title_original'] = news['title']
                        news['title'] = lines[0]
                        news['translated'] = 1
                    else:
                        logger.warning(f"翻译解析失败: 块 {i} 无有效行，来源={news.get('source')}, 标题={news.get('title', '')[:60]}")
                        self._translate_single_fallback(news)
                else:
                    logger.warning(f"翻译解析失败: 块 {i} 缺失，来源={news.get('source')}, 标题={news.get('title', '')[:60]}")
                    self._translate_single_fallback(news)
