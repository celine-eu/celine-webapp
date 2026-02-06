"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-02-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sub', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sub')
    )
    op.create_index(op.f('ix_users_sub'), 'users', ['sub'], unique=True)
    
    # Policy acceptance table
    op.create_table(
        'policy_acceptance',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('policy_version', sa.String(length=50), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_from_ip', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policy_acceptance_user_id'), 'policy_acceptance', ['user_id'], unique=False)
    
    # Settings table
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('simple_mode', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('font_scale', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('email_notifications', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    op.create_index(op.f('ix_settings_user_id'), 'settings', ['user_id'], unique=True)
    
    # Notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    
    # WebPush subscriptions table
    op.create_table(
        'webpush_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('endpoint', sa.String(length=500), nullable=False),
        sa.Column('subscription_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_webpush_subscriptions_user_id'), 'webpush_subscriptions', ['user_id'], unique=False)
    
    # Smart meter associations table
    op.create_table(
        'smart_meter_associations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('meter_id', sa.String(length=100), nullable=False),
        sa.Column('associated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_smart_meter_associations_user_id'), 'smart_meter_associations', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_smart_meter_associations_user_id'), table_name='smart_meter_associations')
    op.drop_table('smart_meter_associations')
    op.drop_index(op.f('ix_webpush_subscriptions_user_id'), table_name='webpush_subscriptions')
    op.drop_table('webpush_subscriptions')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_settings_user_id'), table_name='settings')
    op.drop_table('settings')
    op.drop_index(op.f('ix_policy_acceptance_user_id'), table_name='policy_acceptance')
    op.drop_table('policy_acceptance')
    op.drop_index(op.f('ix_users_sub'), table_name='users')
    op.drop_table('users')
