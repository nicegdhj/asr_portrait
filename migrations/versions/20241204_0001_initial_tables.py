"""初始化画像数据表

Revision ID: 0001
Revises: 
Create Date: 2024-12-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 创建通话记录增强表
    op.create_table(
        'call_record_enriched',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='主键ID'),
        sa.Column('callid', sa.String(64), nullable=False, comment='原始通话ID'),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False, comment='任务ID'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, comment='用户ID'),
        sa.Column('call_date', sa.Date(), nullable=False, comment='通话日期'),
        # 原始指标
        sa.Column('duration', sa.Integer(), default=0, comment='通话时长(毫秒)'),
        sa.Column('bill', sa.Integer(), default=0, comment='计费时长(毫秒)'),
        sa.Column('rounds', sa.Integer(), default=0, comment='交互轮次'),
        sa.Column('level_name', sa.String(32), nullable=True, comment='意向等级名称'),
        sa.Column('intention_result', sa.String(16), nullable=True, comment='意向标签'),
        sa.Column('hangup_by', sa.SmallInteger(), nullable=True, comment='挂断方: 1=机器人, 2=客户'),
        sa.Column('call_status', sa.String(32), nullable=True, comment='通话状态'),
        sa.Column('fail_reason', sa.SmallInteger(), nullable=True, comment='未接原因状态码'),
        # LLM 增强指标
        sa.Column('sentiment', sa.String(16), nullable=True, comment='情绪'),
        sa.Column('sentiment_score', sa.Float(), nullable=True, comment='情绪得分'),
        sa.Column('complaint_risk', sa.String(16), nullable=True, comment='投诉风险'),
        sa.Column('churn_risk', sa.String(16), nullable=True, comment='流失风险'),
        sa.Column('llm_analyzed_at', sa.DateTime(timezone=True), nullable=True, comment='LLM分析时间'),
        sa.Column('llm_raw_response', sa.String(2000), nullable=True, comment='LLM原始响应'),
        # 时间戳
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('callid'),
        comment='通话记录增强表'
    )
    
    # 创建索引
    op.create_index('idx_enriched_callid', 'call_record_enriched', ['callid'])
    op.create_index('idx_enriched_task_id', 'call_record_enriched', ['task_id'])
    op.create_index('idx_enriched_user_id', 'call_record_enriched', ['user_id'])
    op.create_index('idx_enriched_call_date', 'call_record_enriched', ['call_date'])
    op.create_index('idx_enriched_user_date', 'call_record_enriched', ['user_id', 'call_date'])
    op.create_index('idx_enriched_sentiment', 'call_record_enriched', ['sentiment'])
    
    # 创建用户画像快照表
    op.create_table(
        'user_portrait_snapshot',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='主键ID'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, comment='用户ID'),
        sa.Column('period_type', sa.String(16), nullable=False, comment='周期类型'),
        sa.Column('period_key', sa.String(16), nullable=False, comment='周期编号'),
        sa.Column('period_start', sa.Date(), nullable=False, comment='周期开始日期'),
        sa.Column('period_end', sa.Date(), nullable=False, comment='周期结束日期'),
        # 通话统计
        sa.Column('total_calls', sa.Integer(), default=0, comment='总通话次数'),
        sa.Column('connected_calls', sa.Integer(), default=0, comment='接通次数'),
        sa.Column('connect_rate', sa.Float(), default=0.0, comment='接通率'),
        sa.Column('total_duration', sa.Integer(), default=0, comment='总通话时长(秒)'),
        sa.Column('avg_duration', sa.Float(), default=0.0, comment='平均通话时长(秒)'),
        sa.Column('max_duration', sa.Integer(), default=0, comment='最大通话时长(秒)'),
        sa.Column('min_duration', sa.Integer(), default=0, comment='最小通话时长(秒)'),
        sa.Column('total_rounds', sa.Integer(), default=0, comment='总交互轮次'),
        sa.Column('avg_rounds', sa.Float(), default=0.0, comment='平均交互轮次'),
        # 意向等级分布
        sa.Column('level_a_count', sa.Integer(), default=0, comment='A级意向数'),
        sa.Column('level_b_count', sa.Integer(), default=0, comment='B级意向数'),
        sa.Column('level_c_count', sa.Integer(), default=0, comment='C级意向数'),
        sa.Column('level_d_count', sa.Integer(), default=0, comment='D级意向数'),
        sa.Column('level_e_count', sa.Integer(), default=0, comment='E级意向数'),
        sa.Column('level_f_count', sa.Integer(), default=0, comment='F级意向数'),
        # 挂断分布
        sa.Column('robot_hangup_count', sa.Integer(), default=0, comment='机器人挂断次数'),
        sa.Column('user_hangup_count', sa.Integer(), default=0, comment='客户挂断次数'),
        # 未接原因分布
        sa.Column('fail_reason_dist', postgresql.JSONB(), default={}, comment='未接原因分布'),
        # 情感分析
        sa.Column('positive_count', sa.Integer(), default=0, comment='积极情绪次数'),
        sa.Column('neutral_count', sa.Integer(), default=0, comment='中性情绪次数'),
        sa.Column('negative_count', sa.Integer(), default=0, comment='消极情绪次数'),
        sa.Column('avg_sentiment_score', sa.Float(), default=0.0, comment='平均情绪得分'),
        # 风险分析
        sa.Column('high_complaint_risk', sa.Integer(), default=0, comment='高投诉风险次数'),
        sa.Column('medium_complaint_risk', sa.Integer(), default=0, comment='中投诉风险次数'),
        sa.Column('low_complaint_risk', sa.Integer(), default=0, comment='低投诉风险次数'),
        sa.Column('high_churn_risk', sa.Integer(), default=0, comment='高流失风险次数'),
        sa.Column('medium_churn_risk', sa.Integer(), default=0, comment='中流失风险次数'),
        sa.Column('low_churn_risk', sa.Integer(), default=0, comment='低流失风险次数'),
        # 元数据
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'period_type', 'period_key', name='uq_user_period'),
        comment='用户画像快照表'
    )
    
    # 创建索引
    op.create_index('idx_snapshot_user_id', 'user_portrait_snapshot', ['user_id'])
    op.create_index('idx_snapshot_period', 'user_portrait_snapshot', ['period_type', 'period_key'])
    op.create_index('idx_snapshot_user_period', 'user_portrait_snapshot', ['user_id', 'period_type'])
    op.create_index('idx_snapshot_period_start', 'user_portrait_snapshot', ['period_start'])
    
    # 创建周期注册表
    op.create_table(
        'period_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, comment='主键ID'),
        sa.Column('period_type', sa.String(16), nullable=False, comment='周期类型'),
        sa.Column('period_key', sa.String(16), nullable=False, comment='周期编号'),
        sa.Column('period_start', sa.Date(), nullable=False, comment='周期开始日期'),
        sa.Column('period_end', sa.Date(), nullable=False, comment='周期结束日期'),
        sa.Column('status', sa.String(16), default='pending', comment='状态'),
        sa.Column('total_users', sa.Integer(), nullable=True, comment='涉及用户数'),
        sa.Column('total_records', sa.Integer(), nullable=True, comment='涉及记录数'),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=True, comment='计算完成时间'),
        sa.Column('error_message', sa.String(500), nullable=True, comment='错误信息'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period_type', 'period_key', name='uq_period_type_key'),
        comment='周期注册表'
    )


def downgrade() -> None:
    op.drop_table('period_registry')
    op.drop_table('user_portrait_snapshot')
    op.drop_table('call_record_enriched')

