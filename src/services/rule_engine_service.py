"""
规则引擎服务 - 基于规则的满意度/情绪/风险分析

不使用大模型，纯基于关键词和规则进行分析
"""

import re
from dataclasses import dataclass
from typing import Optional, Literal
from loguru import logger


# ===========================================
# 关键词库配置
# ===========================================

# 投诉风险关键词
COMPLAINT_KEYWORDS = {
    'high': [
        # 投诉相关
        '投诉', '举报', '工信部', '消费者协会', '12315', '曝光', '315',
        # 欺骗相关
        '骗人', '骗子', '欺诈', '诈骗', '坑人', '骗钱', '黑心',
        # 强烈负面
        '垃圾', '太差', '差劲', '恶心', '烂', '废物', '坑爹', '狗屎',
        # 升级投诉
        '找领导', '找经理', '上级', '总部', '你们领导', '负责人',
        # 法律相关
        '起诉', '律师', '法律', '赔偿', '法院', '告你们',
        # 媒体相关
        '曝光', '记者', '新闻', '媒体',
    ],
    'medium': [
        # 不满意表达
        '不满意', '很差', '太差', '问题', '故障', '没解决', '解决不了',
        # 收费问题
        '太慢', '太贵', '乱收费', '多扣', '扣费', '多收', '收费不合理',
        # 服务态度
        '态度差', '服务差', '不专业', '敷衍', '推诿', '踢皮球',
        # 重复问题
        '催了好几次', '一直没', '拖', '多少次了', '等了很久', '说话不算',
        # 失望表达
        '失望', '无语', '受不了', '忍不了',
    ],
}

# 流失风险关键词
CHURN_KEYWORDS = {
    'high': [
        # 明确取消意向
        '不用了', '取消', '退订', '销户', '注销', '不要了', '退了吧',
        # 转网意向
        '换运营商', '换电信', '换联通', '换移动', '携号转网', '转网',
        # 套餐变更
        '换套餐', '降档', '降套餐', '最低套餐', '取消套餐',
        # 停机销户
        '不续费', '停机', '停用', '不交费', '欠费停机',
    ],
    'medium': [
        # 考虑中
        '考虑', '再说', '看看', '比较一下', '对比', '犹豫',
        # 价格敏感
        '太贵', '划不来', '不值', '性价比', '便宜点',
        # 使用减少
        '很少用', '用不上', '没必要', '不常用', '用得少',
        # 竞品对比
        '别家', '其他', '朋友用的', '隔壁', '竞争对手',
        # 减少消费
        '少打点', '少用', '降费',
    ],
}

# 满意度 - ASR 标签映射
SATISFACTION_ASR_TAGS = {
    'satisfied': ['满分', 'Q7-满分', 'Q9-满分', 'Q5-满分', 'Q6-满分', 'Q10-满分', 
                  '非常满意', '很满意', '十分满意'],
    'unsatisfied': ['非满分', 'Q7-非满分', 'Q9-非满分', 'Q5-非满分', '不满意', 
                    '非常不满意', '很不满意'],
    'neutral': ['一般', 'Q8', 'default', '还可以'],
}

# 满意度 - 用户打分识别 (正则表达式)
SCORE_PATTERNS = {
    'satisfied': [
        r'10分', r'十分', r'9分', r'九分', r'满分',
    ],
    'neutral': [
        r'8分', r'八分', r'7分', r'七分', r'6分', r'六分',
    ],
    'unsatisfied': [
        r'[0-5]分', r'零分', r'一分', r'两分', r'三分', r'四分', r'五分',
    ],
}

# 满意度 - 关键词兜底
SATISFACTION_KEYWORDS = {
    'satisfied': [
        '满意', '很好', '不错', '可以', '好的', '挺好', '没问题', '谢谢',
        '感谢', '辛苦了', '解决了', '处理好了', '修好了', '正常了',
        '专业', '态度好', '服务好', '效率高',
    ],
    'unsatisfied': [
        '不满意', '不好', '差', '不行', '有问题', '没解决', '还是不行',
        '太慢', '太差', '失望', '没用', '白打',
    ],
    'neutral': [
        '一般', '还行', '凑合', '马马虎虎', '还好', '普通', '就那样',
    ],
}

# 情绪关键词
EMOTION_KEYWORDS = {
    'positive': [
        # 积极词汇
        '好', '谢谢', '感谢', '满意', '不错', '可以', '行', '嗯', '好的',
        '解决了', '修好了', '正常了', '快', '方便', '专业', '耐心',
        '辛苦', '帮忙', '感激', '棒', '赞', '厉害', '优秀',
        # 配合态度
        '好的好的', '没问题', '知道了谢谢', '明白', '清楚',
    ],
    'negative': [
        # 负面词汇
        '不好', '差', '烦', '急', '气', '怒', '投诉', '问题', '故障',
        '没用', '骗', '坑', '垃圾', '恶心', '讨厌', '烂', '废',
        '慢', '贵', '差劲', '失望', '无语', '搞什么', '什么玩意',
        # 负面情绪
        '烦死了', '受不了', '忍不了', '太过分', '算了吧', '不想说了',
        '别打了', '不要打了', '挂了', '不听', '不接受',
    ],
    'neutral': [
        '哦', '嗯', '知道了', '好吧', '行吧', '再说', '看看',
        '那行', '可以', '好', '是的',
    ],
}


@dataclass
class AnalysisResult:
    """单通电话分析结果"""
    
    satisfaction: Optional[str] = None  # satisfied/neutral/unsatisfied
    satisfaction_source: Optional[str] = None  # asr_tag/score/keyword
    emotion: Optional[str] = None  # positive/neutral/negative
    complaint_risk: str = 'low'  # high/medium/low
    churn_risk: str = 'low'  # high/medium/low
    willingness: Optional[str] = None  # 深度/一般/较低
    risk_level: Optional[str] = None  # 综合风险: churn/complaint/medium/none


def get_risk_level(complaint_risk: str, churn_risk: str) -> str:
    """
    根据投诉风险和流失风险计算综合风险等级
    
    优先级：流失风险高 > 投诉风险高 > 一般 > 无风险
    
    Args:
        complaint_risk: 投诉风险 high/medium/low
        churn_risk: 流失风险 high/medium/low
        
    Returns:
        综合风险等级: churn(流失风险)/complaint(投诉风险)/medium(一般)/none(无风险)
    """
    # 高风险优先
    if churn_risk == 'high':
        return 'churn'
    if complaint_risk == 'high':
        return 'complaint'
    
    # 任一有 medium 风险
    if complaint_risk == 'medium' or churn_risk == 'medium':
        return 'medium'
    
    # 都是 low，无风险
    return 'none'


class RuleEngineService:
    """
    规则引擎服务
    
    基于关键词和规则进行满意度/情绪/风险分析
    """
    
    def analyze_call(
        self,
        user_text: str,
        asr_labels: Optional[list[str]] = None,
        duration: int = 0,
        rounds: int = 0,
    ) -> AnalysisResult:
        """
        分析单通电话
        
        Args:
            user_text: 用户说话内容（ASR 识别文本拼接）
            asr_labels: ASR 标签列表（如 Q7-满分）
            duration: 通话时长（秒）
            rounds: 交互轮次
            
        Returns:
            分析结果
        """
        result = AnalysisResult()
        
        # 1. 满意度分析（ASR标签 > 用户打分 > 关键词）
        satisfaction, source = self._analyze_satisfaction(user_text, asr_labels)
        result.satisfaction = satisfaction
        result.satisfaction_source = source
        
        # 2. 情绪分析（纯规则引擎）
        result.emotion = self._analyze_emotion(user_text)
        
        # 3. 投诉风险分析
        result.complaint_risk = self._analyze_complaint_risk(user_text)
        
        # 4. 流失风险分析
        result.churn_risk = self._analyze_churn_risk(user_text)
        
        # 5. 沟通意愿判断
        result.willingness = self._analyze_willingness(duration, rounds)
        
        # 6. 综合风险等级
        result.risk_level = get_risk_level(result.complaint_risk, result.churn_risk)
        
        return result
    
    def _analyze_satisfaction(
        self,
        user_text: str,
        asr_labels: Optional[list[str]] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        分析满意度
        
        优先级：ASR 标签 > 用户原话打分 > 关键词匹配
        
        Returns:
            (满意度, 来源)
        """
        # 1. 优先检查 ASR 标签
        if asr_labels:
            for label in asr_labels:
                label_lower = label.lower() if label else ''
                for satisfaction, tags in SATISFACTION_ASR_TAGS.items():
                    for tag in tags:
                        if tag.lower() in label_lower or label_lower in tag.lower():
                            return satisfaction, 'asr_tag'
        
        if not user_text:
            return None, None
        
        # 2. 检查用户原话打分
        for satisfaction, patterns in SCORE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, user_text):
                    return satisfaction, 'score'
        
        # 3. 关键词匹配兜底
        # 先检查不满意（避免"不满意"被"满意"误匹配）
        for keyword in SATISFACTION_KEYWORDS['unsatisfied']:
            if keyword in user_text:
                return 'unsatisfied', 'keyword'
        
        for keyword in SATISFACTION_KEYWORDS['satisfied']:
            if keyword in user_text:
                return 'satisfied', 'keyword'
        
        for keyword in SATISFACTION_KEYWORDS['neutral']:
            if keyword in user_text:
                return 'neutral', 'keyword'
        
        return None, None
    
    def _analyze_emotion(self, user_text: str) -> str:
        """
        分析情绪
        
        Returns:
            positive/neutral/negative
        """
        if not user_text:
            return 'neutral'
        
        positive_count = 0
        negative_count = 0
        
        # 统计正负面关键词命中数
        for keyword in EMOTION_KEYWORDS['positive']:
            if keyword in user_text:
                positive_count += 1
        
        for keyword in EMOTION_KEYWORDS['negative']:
            if keyword in user_text:
                negative_count += 1
        
        # 负面优先（只要有负面词汇就倾向负面）
        if negative_count > 0:
            return 'negative'
        elif positive_count > 0:
            return 'positive'
        
        return 'neutral'
    
    def _analyze_complaint_risk(self, user_text: str) -> str:
        """
        分析投诉风险
        
        Returns:
            high/medium/low
        """
        if not user_text:
            return 'low'
        
        # 高风险关键词检测
        for keyword in COMPLAINT_KEYWORDS['high']:
            if keyword in user_text:
                return 'high'
        
        # 中风险关键词检测
        medium_count = 0
        for keyword in COMPLAINT_KEYWORDS['medium']:
            if keyword in user_text:
                medium_count += 1
        
        # 多个中风险关键词也升级为高风险
        if medium_count >= 3:
            return 'high'
        elif medium_count >= 1:
            return 'medium'
        
        return 'low'
    
    def _analyze_churn_risk(self, user_text: str) -> str:
        """
        分析流失风险
        
        Returns:
            high/medium/low
        """
        if not user_text:
            return 'low'
        
        # 高风险关键词检测
        for keyword in CHURN_KEYWORDS['high']:
            if keyword in user_text:
                return 'high'
        
        # 中风险关键词检测
        medium_count = 0
        for keyword in CHURN_KEYWORDS['medium']:
            if keyword in user_text:
                medium_count += 1
        
        # 多个中风险关键词也升级为高风险
        if medium_count >= 3:
            return 'high'
        elif medium_count >= 1:
            return 'medium'
        
        return 'low'
    
    def _analyze_willingness(self, duration: int, rounds: int) -> str:
        """
        分析沟通意愿
        
        基于通话时长和交互轮次判断
        
        Args:
            duration: 通话时长（秒）
            rounds: 交互轮次
            
        Returns:
            深度/一般/较低
        """
        # 深度：平均时长 > 60秒 或 轮次 > 5
        if duration > 60 or rounds > 5:
            return '深度'
        
        # 较低：时长 < 20秒 且 轮次 < 3
        if duration < 20 and rounds < 3:
            return '较低'
        
        return '一般'
    
    def aggregate_multi_calls(
        self,
        call_results: list[dict],
    ) -> dict:
        """
        多通电话综合规则
        
        Args:
            call_results: 每通电话的分析结果列表
                [
                    {
                        'satisfaction': 'satisfied',
                        'emotion': 'positive',
                        'complaint_risk': 'low',
                        'churn_risk': 'low',
                        'duration': 120,
                        'rounds': 8,
                        'call_date': datetime,
                    },
                    ...
                ]
        
        Returns:
            综合结果
        """
        if not call_results:
            return {
                'satisfaction': None,
                'emotion': 'neutral',
                'complaint_risk': 'low',
                'churn_risk': 'low',
                'willingness': '一般',
            }
        
        # 按时间排序（最新在最后）
        sorted_calls = sorted(
            call_results,
            key=lambda x: x.get('call_date') or '',
        )
        
        # 1. 满意度：取最后一次有效评分
        satisfaction = None
        for call in reversed(sorted_calls):
            if call.get('satisfaction'):
                satisfaction = call['satisfaction']
                break
        
        # 2. 情绪：负面优先
        emotions = [c.get('emotion') for c in sorted_calls if c.get('emotion')]
        if 'negative' in emotions:
            emotion = 'negative'
        elif 'positive' in emotions:
            emotion = 'positive'
        else:
            emotion = 'neutral'
        
        # 3. 投诉风险：高优先
        complaint_risks = [c.get('complaint_risk', 'low') for c in sorted_calls]
        if 'high' in complaint_risks:
            complaint_risk = 'high'
        elif 'medium' in complaint_risks:
            complaint_risk = 'medium'
        else:
            complaint_risk = 'low'
        
        # 4. 流失风险：高优先
        churn_risks = [c.get('churn_risk', 'low') for c in sorted_calls]
        if 'high' in churn_risks:
            churn_risk = 'high'
        elif 'medium' in churn_risks:
            churn_risk = 'medium'
        else:
            churn_risk = 'low'
        
        # 5. 沟通意愿：基于平均时长和平均轮次
        total_duration = sum(c.get('duration', 0) for c in sorted_calls)
        total_rounds = sum(c.get('rounds', 0) for c in sorted_calls)
        avg_duration = total_duration / len(sorted_calls) if sorted_calls else 0
        avg_rounds = total_rounds / len(sorted_calls) if sorted_calls else 0
        willingness = self._analyze_willingness(int(avg_duration), int(avg_rounds))
        
        # 6. 综合风险等级
        risk_level = get_risk_level(complaint_risk, churn_risk)
        
        return {
            'satisfaction': satisfaction,
            'emotion': emotion,
            'complaint_risk': complaint_risk,
            'churn_risk': churn_risk,
            'willingness': willingness,
            'risk_level': risk_level,
        }


# 全局服务实例
rule_engine = RuleEngineService()
