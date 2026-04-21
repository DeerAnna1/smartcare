"""add registration module tables and health_event registration fields

Revision ID: a3f2d1e8c047
Revises: 9a288366c564
Create Date: 2026-04-20
"""

revision = 'a3f2d1e8c047'
down_revision = 'c1b7c3f4a9d2'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # hospitals
    op.create_table(
        'hospitals',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(256), nullable=False, index=True),
        sa.Column('short_name', sa.String(64), nullable=False, server_default=''),
        sa.Column('city', sa.String(64), nullable=False, server_default=''),
        sa.Column('district', sa.String(64), nullable=False, server_default=''),
        sa.Column('address', sa.Text(), nullable=False, server_default=''),
        sa.Column('phone', sa.String(32), nullable=False, server_default=''),
        sa.Column('level', sa.String(32), nullable=False, server_default='三级甲等'),
        sa.Column('tags', sa.Text(), nullable=False, server_default='[]'),
        sa.Column('platform_code', sa.String(128), nullable=False, server_default=''),
        sa.Column('platform_type', sa.String(32), nullable=False, server_default='seed'),
        sa.Column('booking_url', sa.Text(), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # departments
    op.create_table(
        'departments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('hospital_id', sa.String(36), sa.ForeignKey('hospitals.id'), nullable=False, index=True),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('code', sa.String(64), nullable=False, server_default=''),
        sa.Column('category', sa.String(64), nullable=False, server_default=''),
        sa.Column('description', sa.Text(), nullable=False, server_default=''),
        sa.Column('floor', sa.String(16), nullable=False, server_default=''),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # doctor_schedules
    op.create_table(
        'doctor_schedules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('department_id', sa.String(36), sa.ForeignKey('departments.id'), nullable=False, index=True),
        sa.Column('doctor_name', sa.String(64), nullable=False),
        sa.Column('doctor_title', sa.String(64), nullable=False, server_default=''),
        sa.Column('doctor_bio', sa.Text(), nullable=False, server_default=''),
        sa.Column('schedule_date', sa.String(16), nullable=False, index=True),
        sa.Column('time_slot', sa.String(16), nullable=False),
        sa.Column('period', sa.String(8), nullable=False, server_default='上午'),
        sa.Column('total_quota', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('remaining_quota', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('fee', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('platform_slot_id', sa.String(128), nullable=False, server_default=''),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # registration_orders
    op.create_table(
        'registration_orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('schedule_id', sa.String(36), sa.ForeignKey('doctor_schedules.id'), nullable=False),
        sa.Column('health_event_id', sa.String(36), sa.ForeignKey('health_events.id'), nullable=True),
        sa.Column('patient_name', sa.String(64), nullable=False, server_default=''),
        sa.Column('patient_id_masked', sa.String(32), nullable=False, server_default=''),
        sa.Column('status', sa.String(32), nullable=False, server_default='LOCKED', index=True),
        sa.Column('lock_expire_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('platform_order_id', sa.String(128), nullable=False, server_default=''),
        sa.Column('fee', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('notes', sa.Text(), nullable=False, server_default=''),
        sa.Column('cancel_reason', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # health_events: add registration driver fields
    op.add_column('health_events', sa.Column('recommended_hospital', sa.String(256), nullable=False, server_default=''))
    op.add_column('health_events', sa.Column('urgency_level', sa.String(32), nullable=False, server_default=''))
    op.add_column('health_events', sa.Column('preferred_visit_time', sa.String(128), nullable=False, server_default=''))
    op.add_column('health_events', sa.Column('registration_ready', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('health_events', 'registration_ready')
    op.drop_column('health_events', 'preferred_visit_time')
    op.drop_column('health_events', 'urgency_level')
    op.drop_column('health_events', 'recommended_hospital')
    op.drop_table('registration_orders')
    op.drop_table('doctor_schedules')
    op.drop_table('departments')
    op.drop_table('hospitals')
